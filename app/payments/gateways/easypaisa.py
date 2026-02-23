"""EasyPaisa payment gateway implementation.

EasyPaisa uses SHA256 hash verification for payment initiation and
callback authentication.  The hash is computed from a specific
concatenation of fields plus the store hash key.

Settings required:
- ``easypaisa_store_id``
- ``easypaisa_hash_key``
- ``easypaisa_api_url``
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import PaymentGatewayError
from app.payments.base import (
    PaymentCallbackResult,
    PaymentGateway,
    PaymentLinkResponse,
    PaymentStatusResult,
)


class EasyPaisaGateway(PaymentGateway):
    """EasyPaisa mobile wallet / bank account gateway for Pakistan.

    All amounts are in paisas.  EasyPaisa expects amounts as rupees
    with 2 decimal places in their API.
    """

    def _get_credentials(self) -> tuple[str, str, str]:
        """Return (store_id, hash_key, api_url).

        Raises:
            PaymentGatewayError: If any required credential is missing.
        """
        settings = get_settings()
        store_id = settings.easypaisa_store_id
        hash_key = settings.easypaisa_hash_key
        api_url = settings.easypaisa_api_url

        if not all([store_id, hash_key, api_url]):
            raise PaymentGatewayError(
                "EasyPaisa credentials not configured",
                operation="get_credentials",
            )
        return store_id, hash_key, api_url  # type: ignore[return-value]

    def _compute_hash(
        self,
        store_id: str,
        amount: str,
        order_id: str,
        hash_key: str,
    ) -> str:
        """Compute SHA256 hash for EasyPaisa request authentication.

        Format: SHA256(amount + order_id + store_id + hash_key)

        Args:
            store_id: EasyPaisa store identifier.
            amount: Amount as rupee string (e.g. "1500.00").
            order_id: Transaction reference.
            hash_key: EasyPaisa hash key.

        Returns:
            Hex-encoded SHA256 hash.
        """
        raw = f"{amount}{order_id}{store_id}{hash_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── PaymentGateway implementation ───────────────────────────────

    async def generate_payment_link(
        self,
        amount_paisas: int,
        reference_id: str,
        description: str,
        payer_phone: str,
    ) -> PaymentLinkResponse:
        """Initiate an EasyPaisa payment request.

        Args:
            amount_paisas: Payment amount in paisas.
            reference_id: Internal transaction reference.
            description: Payment description.
            payer_phone: Customer phone.

        Returns:
            PaymentLinkResponse with payment URL.

        Raises:
            PaymentGatewayError: If the API request fails.
        """
        store_id, hash_key, api_url = self._get_credentials()
        settings = get_settings()
        callback_base = settings.payment_callback_base_url or "http://localhost:8000"

        amount_rupees = f"{amount_paisas / 100:.2f}"
        expiry = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.payment_link_expiry_minutes
        )
        expiry_str = expiry.strftime("%Y%m%d %H%M%S")

        request_hash = self._compute_hash(
            store_id, amount_rupees, reference_id, hash_key
        )

        payload = {
            "storeId": store_id,
            "amount": amount_rupees,
            "postBackURL": f"{callback_base}/api/payments/easypaisa/callback",
            "orderRefNum": reference_id,
            "expiryDate": expiry_str,
            "merchantHashedReq": request_hash,
            "autoRedirect": "0",
            "paymentMethod": "MA_PAYMENT_METHOD",
            "mobileNum": payer_phone.replace("+", ""),
            "emailAddr": "",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/easypay/Index.jsf",
                    data=payload,
                )
                response.raise_for_status()

                # EasyPaisa typically redirects; the final URL is the
                # payment page.  The API may return JSON or HTML.
                payment_url = str(response.url) if response.is_redirect else ""

                # Some EasyPaisa integrations return a JSON with URL
                try:
                    data = response.json()
                    payment_url = data.get("paymentUrl", payment_url)
                    gateway_order_id = data.get(
                        "transactionRefNumber", reference_id
                    )
                except Exception:
                    gateway_order_id = reference_id
                    if not payment_url:
                        payment_url = f"{api_url}/easypay/Index.jsf"

        except httpx.HTTPError as exc:
            logger.error(
                "payment.easypaisa.api_error",
                error=str(exc),
                reference_id=reference_id,
            )
            raise PaymentGatewayError(
                f"EasyPaisa API request failed: {exc}",
                operation="generate_payment_link",
            ) from exc

        logger.info(
            "payment.easypaisa.link_generated",
            gateway_order_id=gateway_order_id,
            amount_paisas=amount_paisas,
        )

        return PaymentLinkResponse(
            link_url=payment_url,
            gateway_order_id=gateway_order_id,
            expires_at=expiry,
            metadata={
                "gateway": "easypaisa",
                "store_id": store_id,
            },
        )

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify EasyPaisa callback hash.

        EasyPaisa sends a ``hash`` field in the callback payload.

        Args:
            payload_bytes: Raw POST body.
            headers: HTTP headers (unused for EasyPaisa).

        Returns:
            True if signature is valid.
        """
        store_id, hash_key, _ = self._get_credentials()

        try:
            import json

            try:
                payload = json.loads(payload_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                from urllib.parse import parse_qs

                raw = parse_qs(payload_bytes.decode("utf-8"))
                payload = {k: v[0] if len(v) == 1 else v for k, v in raw.items()}

            received_hash = payload.get("hash", "") or payload.get(
                "merchantHashedReq", ""
            )
            if not received_hash:
                logger.warning("payment.easypaisa.missing_signature")
                return False

            amount = payload.get("amount", payload.get("transactionAmount", ""))
            order_ref = payload.get("orderRefNum", payload.get("orderRefNumber", ""))

            computed = self._compute_hash(store_id, str(amount), str(order_ref), hash_key)
            is_valid = computed.lower() == received_hash.lower()

            if not is_valid:
                logger.warning("payment.easypaisa.signature_mismatch")

            return is_valid

        except Exception as exc:
            logger.error(
                "payment.easypaisa.signature_verification_error",
                error=str(exc),
            )
            return False

    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Process an EasyPaisa callback payload.

        Args:
            payload_dict: Parsed callback data.

        Returns:
            PaymentCallbackResult with payment outcome.
        """
        response_code = payload_dict.get("responseCode", "")
        is_successful = response_code in ("0000", "0001")

        amount_str = payload_dict.get(
            "transactionAmount",
            payload_dict.get("amount", "0"),
        )
        try:
            # EasyPaisa returns amount in rupees — convert to paisas
            amount_paisas = int(float(str(amount_str)) * 100)
        except (ValueError, TypeError):
            amount_paisas = 0

        gateway_txn_id = payload_dict.get(
            "transactionRefNumber",
            payload_dict.get("orderRefNum", ""),
        )

        failure_reason = None
        if not is_successful:
            failure_reason = payload_dict.get(
                "responseDesc",
                f"EasyPaisa error: {response_code}",
            )

        logger.info(
            "payment.easypaisa.callback_processed",
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
        """Query EasyPaisa for payment status.

        Args:
            gateway_transaction_id: Transaction reference.

        Returns:
            PaymentStatusResult with current state.

        Raises:
            PaymentGatewayError: If the status query fails.
        """
        store_id, hash_key, api_url = self._get_credentials()

        payload = {
            "storeId": store_id,
            "orderId": gateway_transaction_id,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/easypay/Confirm.jsf",
                    data=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(
                f"EasyPaisa status query failed: {exc}",
                operation="get_payment_status",
            ) from exc

        code = data.get("responseCode", "")
        status_map = {
            "0000": "completed",
            "0001": "completed",
            "0002": "pending",
        }
        status = status_map.get(code, "failed")

        paid_at = None
        if status == "completed":
            paid_at = datetime.now(tz=timezone.utc)

        amount_str = data.get("transactionAmount", "0")
        try:
            amount_paisas = int(float(str(amount_str)) * 100)
        except (ValueError, TypeError):
            amount_paisas = 0

        return PaymentStatusResult(
            status=status,
            gateway_transaction_id=gateway_transaction_id,
            amount_paisas=amount_paisas,
            paid_at=paid_at,
            raw_response=data,
        )

    async def cancel_payment(
        self,
        gateway_transaction_id: str,
    ) -> bool:
        """EasyPaisa does not support programmatic cancellation.

        Args:
            gateway_transaction_id: Unused.

        Returns:
            Always False.
        """
        logger.info(
            "payment.easypaisa.cancel_not_supported",
            gateway_txn_id=gateway_transaction_id,
        )
        return False

    def get_gateway_name(self) -> str:
        """Return ``'easypaisa'``."""
        return "easypaisa"

    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return EasyPaisa gateway capabilities."""
        settings = get_settings()
        return {
            "supported_currencies": ["PKR"],
            "min_amount_paisas": 100,
            "max_amount_paisas": 5_000_000,
            "supports_refunds": False,
            "supports_cancellation": False,
            "link_expiry_minutes": settings.payment_link_expiry_minutes,
            "production_allowed": True,
            "auth_method": "SHA256",
        }

    async def health_check(self) -> bool:
        """Check EasyPaisa API reachability.

        Returns:
            True if the API responds.
        """
        try:
            _, _, api_url = self._get_credentials()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api_url)
                return response.status_code < 500
        except Exception:
            return False
