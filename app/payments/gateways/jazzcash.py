"""JazzCash payment gateway implementation.

JazzCash uses HMAC-SHA256 integrity hashes for both payment initiation
and webhook callback verification.  All request parameters are sorted
alphabetically and concatenated with the integrity salt before hashing.

Settings required:
- ``jazzcash_merchant_id``
- ``jazzcash_password``
- ``jazzcash_integrity_salt``
- ``jazzcash_api_url``
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import PaymentGatewayError, PaymentSignatureError
from app.payments.base import (
    PaymentCallbackResult,
    PaymentGateway,
    PaymentLinkResponse,
    PaymentStatusResult,
)


class JazzCashGateway(PaymentGateway):
    """JazzCash payment gateway for mobile wallet payments in Pakistan.

    All amounts are in paisas.  JazzCash expects amounts as strings in
    their API, so conversion is handled internally.
    """

    def _get_credentials(self) -> tuple[str, str, str, str]:
        """Return (merchant_id, password, integrity_salt, api_url).

        Raises:
            PaymentGatewayError: If any required credential is missing.
        """
        settings = get_settings()
        merchant_id = settings.jazzcash_merchant_id
        password = settings.jazzcash_password
        salt = settings.jazzcash_integrity_salt
        api_url = settings.jazzcash_api_url

        if not all([merchant_id, password, salt, api_url]):
            raise PaymentGatewayError(
                "JazzCash credentials not configured",
                operation="get_credentials",
            )
        return merchant_id, password, salt, api_url  # type: ignore[return-value]

    def _compute_integrity_hash(
        self,
        params: dict[str, str],
        salt: str,
    ) -> str:
        """Compute HMAC-SHA256 integrity hash for JazzCash.

        Parameters are sorted by key, concatenated with ``&``, and
        then HMAC-SHA256 is computed with the integrity salt.

        Args:
            params: Request parameters (all values as strings).
            salt: JazzCash integrity salt.

        Returns:
            Hex-encoded HMAC-SHA256 hash.
        """
        sorted_values = "&".join(
            str(v) for _, v in sorted(params.items()) if v
        )
        message = salt + "&" + sorted_values
        return hmac.new(
            salt.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ── PaymentGateway implementation ───────────────────────────────

    async def generate_payment_link(
        self,
        amount_paisas: int,
        reference_id: str,
        description: str,
        payer_phone: str,
    ) -> PaymentLinkResponse:
        """Initiate a JazzCash payment request.

        Args:
            amount_paisas: Payment amount in paisas.
            reference_id: Internal transaction reference.
            description: Payment description.
            payer_phone: Customer phone (E.164 or local).

        Returns:
            PaymentLinkResponse with redirect URL.

        Raises:
            PaymentGatewayError: If the API request fails.
        """
        merchant_id, password, salt, api_url = self._get_credentials()
        settings = get_settings()
        callback_base = settings.payment_callback_base_url or "http://localhost:8000"

        now = datetime.now(tz=timezone.utc)
        expiry = now + timedelta(minutes=settings.payment_link_expiry_minutes)
        expiry_str = expiry.strftime("%Y%m%d%H%M%S")

        # JazzCash expects amount in rupees as string (2 decimal places)
        amount_rupees = f"{amount_paisas / 100:.2f}"

        params = {
            "pp_Version": "1.1",
            "pp_TxnType": "MWALLET",
            "pp_Language": "EN",
            "pp_MerchantID": merchant_id,
            "pp_Password": password,
            "pp_TxnRefNo": reference_id,
            "pp_Amount": str(amount_paisas),
            "pp_TxnCurrency": "PKR",
            "pp_TxnDateTime": now.strftime("%Y%m%d%H%M%S"),
            "pp_TxnExpiryDateTime": expiry_str,
            "pp_BillReference": reference_id,
            "pp_Description": description[:50],
            "pp_MobileNumber": payer_phone.replace("+", ""),
            "pp_ReturnURL": f"{callback_base}/api/payments/jazzcash/callback",
        }

        integrity_hash = self._compute_integrity_hash(params, salt)
        params["pp_SecureHash"] = integrity_hash

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/ApplicationAPI/API/2.0/Purchase/DoMWalletTransaction",
                    data=params,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "payment.jazzcash.api_error",
                error=str(exc),
                reference_id=reference_id,
            )
            raise PaymentGatewayError(
                f"JazzCash API request failed: {exc}",
                operation="generate_payment_link",
            ) from exc

        response_code = data.get("pp_ResponseCode", "")
        if response_code != "000":
            logger.warning(
                "payment.jazzcash.init_failed",
                response_code=response_code,
                message=data.get("pp_ResponseMessage", ""),
            )
            raise PaymentGatewayError(
                f"JazzCash payment init failed: {data.get('pp_ResponseMessage', 'Unknown')}",
                operation="generate_payment_link",
            )

        gateway_order_id = data.get("pp_TxnRefNo", reference_id)
        payment_url = data.get("pp_PaymentURL", "")

        # If no direct payment URL, construct one from return params
        if not payment_url:
            payment_url = (
                f"{api_url}/CustomerPortal/transactionmanagement/"
                f"merchantform/?{urlencode({'pp_TxnRefNo': gateway_order_id})}"
            )

        logger.info(
            "payment.jazzcash.link_generated",
            gateway_order_id=gateway_order_id,
            amount_paisas=amount_paisas,
        )

        return PaymentLinkResponse(
            link_url=payment_url,
            gateway_order_id=gateway_order_id,
            expires_at=expiry,
            metadata={
                "gateway": "jazzcash",
                "response_code": response_code,
                "raw_response": data,
            },
        )

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify JazzCash callback signature via HMAC-SHA256.

        Args:
            payload_bytes: Raw POST body.
            headers: HTTP request headers.

        Returns:
            True if signature is valid.
        """
        _, _, salt, _ = self._get_credentials()

        try:
            # JazzCash sends form-encoded or JSON callback
            import json

            try:
                payload = json.loads(payload_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                from urllib.parse import parse_qs

                raw = parse_qs(payload_bytes.decode("utf-8"))
                payload = {k: v[0] if len(v) == 1 else v for k, v in raw.items()}

            received_hash = payload.pop("pp_SecureHash", "")
            if not received_hash:
                logger.warning("payment.jazzcash.missing_signature")
                return False

            computed = self._compute_integrity_hash(
                {k: str(v) for k, v in payload.items()},
                salt,
            )
            is_valid = hmac.compare_digest(computed.lower(), received_hash.lower())

            if not is_valid:
                logger.warning("payment.jazzcash.signature_mismatch")

            return is_valid

        except Exception as exc:
            logger.error(
                "payment.jazzcash.signature_verification_error",
                error=str(exc),
            )
            return False

    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Process a JazzCash callback payload.

        Args:
            payload_dict: Parsed callback parameters.

        Returns:
            PaymentCallbackResult with payment outcome.
        """
        response_code = payload_dict.get("pp_ResponseCode", "")
        is_successful = response_code == "000"
        amount_str = payload_dict.get("pp_Amount", "0")
        gateway_txn_id = payload_dict.get("pp_TxnRefNo", "")

        try:
            amount_paisas = int(amount_str)
        except (ValueError, TypeError):
            amount_paisas = 0

        failure_reason = None
        if not is_successful:
            failure_reason = payload_dict.get(
                "pp_ResponseMessage", f"JazzCash error: {response_code}"
            )

        logger.info(
            "payment.jazzcash.callback_processed",
            is_successful=is_successful,
            gateway_txn_id=gateway_txn_id,
            amount_paisas=amount_paisas,
        )

        return PaymentCallbackResult(
            is_successful=is_successful,
            amount_paisas=amount_paisas,
            gateway_transaction_id=gateway_txn_id,
            failure_reason=failure_reason,
            raw_payload=payload_dict,
        )

    async def get_payment_status(
        self,
        gateway_transaction_id: str,
    ) -> PaymentStatusResult:
        """Query JazzCash for payment status.

        Args:
            gateway_transaction_id: The JazzCash transaction reference.

        Returns:
            PaymentStatusResult with current state.

        Raises:
            PaymentGatewayError: If the status query fails.
        """
        merchant_id, password, salt, api_url = self._get_credentials()

        params = {
            "pp_MerchantID": merchant_id,
            "pp_Password": password,
            "pp_TxnRefNo": gateway_transaction_id,
        }
        params["pp_SecureHash"] = self._compute_integrity_hash(params, salt)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/ApplicationAPI/API/PaymentInquiry/Inquire",
                    data=params,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(
                f"JazzCash status query failed: {exc}",
                operation="get_payment_status",
            ) from exc

        code = data.get("pp_ResponseCode", "")
        status_map = {
            "000": "completed",
            "124": "pending",
            "157": "expired",
        }
        status = status_map.get(code, "failed")

        paid_at = None
        if status == "completed":
            paid_at = datetime.now(tz=timezone.utc)

        return PaymentStatusResult(
            status=status,
            gateway_transaction_id=gateway_transaction_id,
            amount_paisas=int(data.get("pp_Amount", 0)),
            paid_at=paid_at,
            raw_response=data,
        )

    async def cancel_payment(
        self,
        gateway_transaction_id: str,
    ) -> bool:
        """JazzCash does not support programmatic cancellation.

        Args:
            gateway_transaction_id: Unused.

        Returns:
            Always False — cancellation not supported.
        """
        logger.info(
            "payment.jazzcash.cancel_not_supported",
            gateway_txn_id=gateway_transaction_id,
        )
        return False

    def get_gateway_name(self) -> str:
        """Return ``'jazzcash'``."""
        return "jazzcash"

    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return JazzCash gateway capabilities."""
        settings = get_settings()
        return {
            "supported_currencies": ["PKR"],
            "min_amount_paisas": 100,
            "max_amount_paisas": 5_000_000,
            "supports_refunds": False,
            "supports_cancellation": False,
            "link_expiry_minutes": settings.payment_link_expiry_minutes,
            "production_allowed": True,
            "auth_method": "HMAC-SHA256",
        }

    async def health_check(self) -> bool:
        """Check JazzCash API reachability.

        Returns:
            True if the API responds to a basic request.
        """
        try:
            _, _, _, api_url = self._get_credentials()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api_url)
                return response.status_code < 500
        except Exception:
            return False
