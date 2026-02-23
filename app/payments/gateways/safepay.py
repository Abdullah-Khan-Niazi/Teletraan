"""SafePay payment gateway implementation.

SafePay uses Bearer tokens for API authentication and HMAC-SHA256
with a separate webhook secret for callback signature verification.

Settings required:
- ``safepay_api_key``
- ``safepay_secret_key``
- ``safepay_api_url``
- ``safepay_webhook_secret``
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


class SafePayGateway(PaymentGateway):
    """SafePay payment gateway — modern REST API with HMAC webhooks.

    SafePay provides a clean REST API for payment initiation and
    separate HMAC-SHA256 webhook verification via a dedicated secret.
    """

    def _get_credentials(self) -> tuple[str, str, str, str]:
        """Return (api_key, secret_key, api_url, webhook_secret).

        Raises:
            PaymentGatewayError: If any required credential is missing.
        """
        settings = get_settings()
        api_key = settings.safepay_api_key
        secret_key = settings.safepay_secret_key
        api_url = settings.safepay_api_url
        webhook_secret = settings.safepay_webhook_secret

        if not all([api_key, secret_key, webhook_secret]):
            raise PaymentGatewayError(
                "SafePay credentials not configured",
                operation="get_credentials",
            )
        return api_key, secret_key, api_url, webhook_secret  # type: ignore[return-value]

    def _auth_headers(self, api_key: str, secret_key: str) -> dict[str, str]:
        """Build authorization headers for SafePay API.

        Args:
            api_key: SafePay API key.
            secret_key: SafePay secret key.

        Returns:
            Headers dict with Bearer token and content type.
        """
        import base64

        token = base64.b64encode(
            f"{api_key}:{secret_key}".encode()
        ).decode()
        return {
            "Authorization": f"Bearer {token}",
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
        """Create a SafePay checkout session.

        Args:
            amount_paisas: Payment amount in paisas.
            reference_id: Internal transaction reference.
            description: Payment description.
            payer_phone: Customer phone.

        Returns:
            PaymentLinkResponse with checkout URL.

        Raises:
            PaymentGatewayError: If the API request fails.
        """
        api_key, secret_key, api_url, _ = self._get_credentials()
        settings = get_settings()
        callback_base = settings.payment_callback_base_url or "http://localhost:8000"

        expiry = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.payment_link_expiry_minutes
        )

        payload = {
            "amount": amount_paisas,
            "currency": "PKR",
            "order_id": reference_id,
            "source": "custom",
            "redirect_url": f"{callback_base}/api/payments/safepay/callback",
            "cancel_url": f"{callback_base}/api/payments/safepay/cancel",
            "webhooks": True,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/order/payments/v3/",
                    headers=self._auth_headers(api_key, secret_key),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "payment.safepay.api_error",
                error=str(exc),
                reference_id=reference_id,
            )
            raise PaymentGatewayError(
                f"SafePay API request failed: {exc}",
                operation="generate_payment_link",
            ) from exc

        # SafePay returns a token/tracker and checkout URL
        checkout_data = data.get("data", data)
        tracker = checkout_data.get("tracker", {})
        gateway_order_id = tracker.get("token", reference_id)
        checkout_url = checkout_data.get(
            "checkout_url",
            f"{api_url}/checkout/pay?token={gateway_order_id}",
        )

        logger.info(
            "payment.safepay.link_generated",
            gateway_order_id=gateway_order_id,
            amount_paisas=amount_paisas,
        )

        return PaymentLinkResponse(
            link_url=checkout_url,
            gateway_order_id=gateway_order_id,
            expires_at=expiry,
            metadata={
                "gateway": "safepay",
                "tracker": tracker,
            },
        )

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify SafePay HMAC-SHA256 webhook signature.

        SafePay sends the signature in the ``X-Safepay-Signature``
        header as ``sha256=<hex>``.

        Args:
            payload_bytes: Raw POST body.
            headers: HTTP request headers.

        Returns:
            True if signature matches.
        """
        _, _, _, webhook_secret = self._get_credentials()

        signature = headers.get(
            "x-safepay-signature",
            headers.get("X-Safepay-Signature", ""),
        )
        if not signature or not signature.startswith("sha256="):
            logger.warning("payment.safepay.missing_signature")
            return False

        expected = "sha256=" + hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature)
        if not is_valid:
            logger.warning("payment.safepay.signature_mismatch")

        return is_valid

    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Process a SafePay webhook callback.

        Args:
            payload_dict: Parsed webhook JSON payload.

        Returns:
            PaymentCallbackResult with payment outcome.
        """
        event_type = payload_dict.get("type", "")
        data = payload_dict.get("data", payload_dict)

        is_successful = event_type in (
            "payment:created",
            "payment.completed",
        )

        amount = data.get("amount", data.get("net", 0))
        try:
            amount_paisas = int(amount)
        except (ValueError, TypeError):
            amount_paisas = 0

        gateway_txn_id = data.get(
            "tracker",
            data.get("token", data.get("reference_code", "")),
        )
        if isinstance(gateway_txn_id, dict):
            gateway_txn_id = gateway_txn_id.get("token", "")

        failure_reason = None
        if not is_successful:
            failure_reason = data.get(
                "message",
                f"SafePay event: {event_type}",
            )

        logger.info(
            "payment.safepay.callback_processed",
            is_successful=is_successful,
            gateway_txn_id=gateway_txn_id,
            event_type=event_type,
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
        """Query SafePay for payment/tracker status.

        Args:
            gateway_transaction_id: SafePay tracker token.

        Returns:
            PaymentStatusResult with current state.

        Raises:
            PaymentGatewayError: If the query fails.
        """
        api_key, secret_key, api_url, _ = self._get_credentials()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{api_url}/order/payments/v3/{gateway_transaction_id}",
                    headers=self._auth_headers(api_key, secret_key),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(
                f"SafePay status query failed: {exc}",
                operation="get_payment_status",
            ) from exc

        tracker_data = data.get("data", data)
        state = tracker_data.get("state", "unknown")

        status_map = {
            "tracker:created": "pending",
            "tracker:received": "completed",
            "tracker:cancelled": "cancelled",
            "tracker:expired": "expired",
        }
        status = status_map.get(state, "pending")

        paid_at = None
        if status == "completed":
            paid_at = datetime.now(tz=timezone.utc)

        return PaymentStatusResult(
            status=status,
            gateway_transaction_id=gateway_transaction_id,
            amount_paisas=int(tracker_data.get("amount", 0)),
            paid_at=paid_at,
            raw_response=data,
        )

    async def cancel_payment(
        self,
        gateway_transaction_id: str,
    ) -> bool:
        """Cancel a pending SafePay tracker.

        Args:
            gateway_transaction_id: SafePay tracker token.

        Returns:
            True if cancellation succeeded.
        """
        api_key, secret_key, api_url, _ = self._get_credentials()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{api_url}/order/payments/v3/{gateway_transaction_id}",
                    headers=self._auth_headers(api_key, secret_key),
                )
                if response.status_code in (200, 204):
                    logger.info(
                        "payment.safepay.cancelled",
                        gateway_txn_id=gateway_transaction_id,
                    )
                    return True
                return False
        except httpx.HTTPError as exc:
            logger.error(
                "payment.safepay.cancel_error",
                error=str(exc),
            )
            return False

    def get_gateway_name(self) -> str:
        """Return ``'safepay'``."""
        return "safepay"

    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return SafePay gateway capabilities."""
        settings = get_settings()
        return {
            "supported_currencies": ["PKR", "USD"],
            "min_amount_paisas": 100,
            "max_amount_paisas": 50_000_000,
            "supports_refunds": True,
            "supports_cancellation": True,
            "link_expiry_minutes": settings.payment_link_expiry_minutes,
            "production_allowed": True,
            "auth_method": "Bearer + HMAC-SHA256 webhooks",
        }

    async def health_check(self) -> bool:
        """Check SafePay API reachability.

        Returns:
            True if the API responds.
        """
        try:
            api_key, secret_key, api_url, _ = self._get_credentials()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{api_url}/order/payments/v3/",
                    headers=self._auth_headers(api_key, secret_key),
                )
                return response.status_code < 500
        except Exception:
            return False
