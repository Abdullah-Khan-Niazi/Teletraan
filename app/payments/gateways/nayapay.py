"""NayaPay payment gateway implementation.

NayaPay uses API key authentication for requests and HMAC-SHA256
request signing for both outgoing requests and incoming webhook
verification.

Settings required:
- ``nayapay_merchant_id``
- ``nayapay_api_key``
- ``nayapay_secret``
- ``nayapay_api_url``
"""

from __future__ import annotations

import hashlib
import hmac
import json
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


class NayaPayGateway(PaymentGateway):
    """NayaPay payment gateway for QR and link-based payments.

    NayaPay is a Pakistani fintech offering QR-based and direct
    payment link functionality.  Webhook verification uses
    HMAC-SHA256 with the merchant secret.
    """

    def _get_credentials(self) -> tuple[str, str, str, str]:
        """Return (merchant_id, api_key, secret, api_url).

        Raises:
            PaymentGatewayError: If any required credential is missing.
        """
        settings = get_settings()
        merchant_id = settings.nayapay_merchant_id
        api_key = settings.nayapay_api_key
        secret = settings.nayapay_secret
        api_url = settings.nayapay_api_url

        if not all([merchant_id, api_key, secret, api_url]):
            raise PaymentGatewayError(
                "NayaPay credentials not configured",
                operation="get_credentials",
            )
        return merchant_id, api_key, secret, api_url  # type: ignore[return-value]

    def _sign_request(self, payload_json: str, secret: str) -> str:
        """Compute HMAC-SHA256 signature for an outgoing request.

        Args:
            payload_json: JSON-serialized request body.
            secret: NayaPay merchant secret.

        Returns:
            Hex-encoded HMAC-SHA256 signature.
        """
        return hmac.new(
            secret.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(
        self,
        api_key: str,
        secret: str,
        payload_json: str,
    ) -> dict[str, str]:
        """Build authentication headers for NayaPay API.

        Args:
            api_key: NayaPay API key.
            secret: NayaPay merchant secret.
            payload_json: JSON body for request signing.

        Returns:
            Headers dict with API key and signature.
        """
        signature = self._sign_request(payload_json, secret)
        return {
            "X-Api-Key": api_key,
            "X-Signature": signature,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── PaymentGateway implementation ───────────────────────────────

    async def generate_payment_link(
        self,
        amount_paisas: int,
        reference_id: str,
        description: str,
        payer_phone: str,
    ) -> PaymentLinkResponse:
        """Create a NayaPay payment request.

        Args:
            amount_paisas: Payment amount in paisas.
            reference_id: Internal transaction reference.
            description: Payment description.
            payer_phone: Customer phone.

        Returns:
            PaymentLinkResponse with payment URL / QR code.

        Raises:
            PaymentGatewayError: If the API request fails.
        """
        merchant_id, api_key, secret, api_url = self._get_credentials()
        settings = get_settings()
        callback_base = settings.payment_callback_base_url or "http://localhost:8000"

        expiry = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.payment_link_expiry_minutes
        )

        # NayaPay expects amount in rupees (2 decimal places)
        amount_rupees = round(amount_paisas / 100, 2)

        payload = {
            "merchantId": merchant_id,
            "orderId": reference_id,
            "amount": amount_rupees,
            "currency": "PKR",
            "description": description[:200],
            "callbackUrl": f"{callback_base}/api/payments/nayapay/callback",
            "customerPhone": payer_phone.replace("+", ""),
            "expiresAt": expiry.isoformat(),
        }

        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        headers = self._auth_headers(api_key, secret, payload_json)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/api/v1/payments/create",
                    headers=headers,
                    content=payload_json,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "payment.nayapay.api_error",
                error=str(exc),
                reference_id=reference_id,
            )
            raise PaymentGatewayError(
                f"NayaPay API request failed: {exc}",
                operation="generate_payment_link",
            ) from exc

        result = data.get("data", data)
        gateway_order_id = result.get("paymentId", reference_id)
        payment_url = result.get(
            "paymentUrl",
            result.get("qrCodeUrl", ""),
        )

        if not payment_url:
            payment_url = result.get("deepLink", "")

        logger.info(
            "payment.nayapay.link_generated",
            gateway_order_id=gateway_order_id,
            amount_paisas=amount_paisas,
        )

        return PaymentLinkResponse(
            link_url=payment_url,
            gateway_order_id=gateway_order_id,
            expires_at=expiry,
            metadata={
                "gateway": "nayapay",
                "qr_code_url": result.get("qrCodeUrl"),
                "deep_link": result.get("deepLink"),
            },
        )

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify NayaPay webhook HMAC-SHA256 signature.

        NayaPay sends the signature in ``X-Signature`` header.

        Args:
            payload_bytes: Raw POST body.
            headers: HTTP request headers.

        Returns:
            True if signature matches.
        """
        _, _, secret, _ = self._get_credentials()

        signature = headers.get(
            "x-signature",
            headers.get("X-Signature", ""),
        )
        if not signature:
            logger.warning("payment.nayapay.missing_signature")
            return False

        computed = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(computed.lower(), signature.lower())
        if not is_valid:
            logger.warning("payment.nayapay.signature_mismatch")

        return is_valid

    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Process a NayaPay webhook callback.

        Args:
            payload_dict: Parsed webhook JSON payload.

        Returns:
            PaymentCallbackResult with payment outcome.
        """
        status = payload_dict.get("status", "")
        is_successful = status.lower() in ("completed", "paid", "success")

        amount = payload_dict.get("amount", 0)
        try:
            # NayaPay returns amount in rupees — convert to paisas
            amount_paisas = int(float(str(amount)) * 100)
        except (ValueError, TypeError):
            amount_paisas = 0

        gateway_txn_id = payload_dict.get(
            "paymentId",
            payload_dict.get("transactionId", ""),
        )

        failure_reason = None
        if not is_successful:
            failure_reason = payload_dict.get(
                "message",
                payload_dict.get("reason", f"NayaPay status: {status}"),
            )

        logger.info(
            "payment.nayapay.callback_processed",
            is_successful=is_successful,
            gateway_txn_id=gateway_txn_id,
        )

        return PaymentCallbackResult(
            is_successful=is_successful,
            amount_paisas=amount_paisas,
            gateway_transaction_id=str(gateway_txn_id),
            failure_reason=failure_reason,
            raw_payload=payload_dict,
        )

    async def get_payment_status(
        self,
        gateway_transaction_id: str,
    ) -> PaymentStatusResult:
        """Query NayaPay for payment status.

        Args:
            gateway_transaction_id: NayaPay payment ID.

        Returns:
            PaymentStatusResult with current state.

        Raises:
            PaymentGatewayError: If the query fails.
        """
        merchant_id, api_key, secret, api_url = self._get_credentials()

        query_payload = json.dumps(
            {"paymentId": gateway_transaction_id},
            separators=(",", ":"),
            sort_keys=True,
        )
        headers = self._auth_headers(api_key, secret, query_payload)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{api_url}/api/v1/payments/{gateway_transaction_id}",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(
                f"NayaPay status query failed: {exc}",
                operation="get_payment_status",
            ) from exc

        result = data.get("data", data)
        raw_status = result.get("status", "unknown").lower()

        status_map = {
            "completed": "completed",
            "paid": "completed",
            "pending": "pending",
            "created": "pending",
            "expired": "expired",
            "cancelled": "cancelled",
            "failed": "failed",
        }
        status = status_map.get(raw_status, "pending")

        paid_at = None
        if status == "completed":
            ts = result.get("completedAt")
            if ts:
                try:
                    paid_at = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    paid_at = datetime.now(tz=timezone.utc)
            else:
                paid_at = datetime.now(tz=timezone.utc)

        amount = result.get("amount", 0)
        try:
            amount_paisas = int(float(str(amount)) * 100)
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
        """Cancel a pending NayaPay payment.

        Args:
            gateway_transaction_id: NayaPay payment ID.

        Returns:
            True if cancellation succeeded.
        """
        merchant_id, api_key, secret, api_url = self._get_credentials()

        cancel_payload = json.dumps(
            {"paymentId": gateway_transaction_id, "reason": "merchant_cancel"},
            separators=(",", ":"),
            sort_keys=True,
        )
        headers = self._auth_headers(api_key, secret, cancel_payload)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/api/v1/payments/{gateway_transaction_id}/cancel",
                    headers=headers,
                    content=cancel_payload,
                )
                if response.status_code in (200, 204):
                    logger.info(
                        "payment.nayapay.cancelled",
                        gateway_txn_id=gateway_transaction_id,
                    )
                    return True
                return False
        except httpx.HTTPError as exc:
            logger.error(
                "payment.nayapay.cancel_error",
                error=str(exc),
            )
            return False

    def get_gateway_name(self) -> str:
        """Return ``'nayapay'``."""
        return "nayapay"

    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return NayaPay gateway capabilities."""
        settings = get_settings()
        return {
            "supported_currencies": ["PKR"],
            "min_amount_paisas": 100,
            "max_amount_paisas": 10_000_000,
            "supports_refunds": True,
            "supports_cancellation": True,
            "link_expiry_minutes": settings.payment_link_expiry_minutes,
            "production_allowed": True,
            "auth_method": "API key + HMAC-SHA256 signing",
            "supports_qr": True,
        }

    async def health_check(self) -> bool:
        """Check NayaPay API reachability.

        Returns:
            True if the API responds.
        """
        try:
            _, api_key, secret, api_url = self._get_credentials()
            ping = json.dumps({"ping": True}, separators=(",", ":"))
            headers = self._auth_headers(api_key, secret, ping)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{api_url}/api/v1/health",
                    headers=headers,
                )
                return response.status_code < 500
        except Exception:
            return False
