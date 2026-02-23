"""Dummy payment gateway — development and testing only.

Behaviour:
- Auto-confirms payments after ``DUMMY_GATEWAY_CONFIRM_DELAY_SECONDS``.
- Amounts ending in ``99`` paisas → auto-fail (failure simulation).
- Payment links expire after 15 minutes.
- **COMPLETELY BLOCKED when ``APP_ENV == production``.**  The factory
  enforces this, but the gateway itself also guards.

All operations are in-memory — no external API calls.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import PaymentGatewayError
from app.payments.base import (
    PaymentCallbackResult,
    PaymentGateway,
    PaymentLinkResponse,
    PaymentStatusResult,
)


# ── In-memory payment store ─────────────────────────────────────────
# Maps gateway_order_id → payment record dict.  Only used for dev/test.
_DUMMY_PAYMENTS: dict[str, dict[str, Any]] = {}

_LINK_EXPIRY_MINUTES = 15


class DummyGateway(PaymentGateway):
    """In-memory payment gateway for development and automated tests.

    Simulates the full payment lifecycle without any external
    dependencies.  Useful for end-to-end testing of the order flow.
    """

    def _guard_production(self) -> None:
        """Raise if running in production environment."""
        settings = get_settings()
        if settings.app_env == "production":
            raise PaymentGatewayError(
                "Dummy gateway is blocked in production",
                operation="guard_production",
            )

    # ── PaymentGateway implementation ───────────────────────────────

    async def generate_payment_link(
        self,
        amount_paisas: int,
        reference_id: str,
        description: str,
        payer_phone: str,
    ) -> PaymentLinkResponse:
        """Generate a fake payment link.

        Amounts ending in ``99`` paisas will auto-fail when the
        callback is processed.

        Args:
            amount_paisas: Amount in paisas.
            reference_id: Internal transaction reference.
            description: Human-readable description.
            payer_phone: Customer phone (E.164).

        Returns:
            PaymentLinkResponse with a local dummy URL.

        Raises:
            PaymentGatewayError: If called in production.
        """
        self._guard_production()

        gateway_order_id = f"DUMMY-{uuid4().hex[:12].upper()}"
        settings = get_settings()
        callback_base = settings.payment_callback_base_url or "http://localhost:8000"
        link_url = (
            f"{callback_base}/api/payments/dummy/callback"
            f"?order_id={gateway_order_id}&ref={reference_id}"
        )

        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            minutes=_LINK_EXPIRY_MINUTES
        )

        # Store in memory
        _DUMMY_PAYMENTS[gateway_order_id] = {
            "reference_id": reference_id,
            "amount_paisas": amount_paisas,
            "payer_phone": payer_phone,
            "description": description,
            "status": "pending",
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": expires_at,
            "will_fail": amount_paisas % 100 == 99,
        }

        logger.info(
            "payment.dummy.link_generated",
            gateway_order_id=gateway_order_id,
            amount_paisas=amount_paisas,
            will_fail=amount_paisas % 100 == 99,
        )

        # Schedule auto-confirm if enabled
        if settings.dummy_gateway_auto_confirm:
            asyncio.get_event_loop().call_later(
                settings.dummy_gateway_confirm_delay_seconds,
                lambda goid=gateway_order_id: asyncio.ensure_future(
                    self._auto_confirm(goid)
                ),
            )

        return PaymentLinkResponse(
            link_url=link_url,
            gateway_order_id=gateway_order_id,
            expires_at=expires_at,
            metadata={
                "gateway": "dummy",
                "auto_confirm": settings.dummy_gateway_auto_confirm,
                "will_fail": amount_paisas % 100 == 99,
            },
        )

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Dummy signature verification — always returns True.

        The dummy gateway has no real signature mechanism.

        Args:
            payload_bytes: Raw request body.
            headers: HTTP headers.

        Returns:
            Always True.
        """
        return True

    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Process a dummy callback payload.

        The payload must contain ``order_id`` (gateway_order_id).

        Args:
            payload_dict: Parsed callback data.

        Returns:
            PaymentCallbackResult with success/failure outcome.

        Raises:
            PaymentGatewayError: If the order_id is unknown.
        """
        self._guard_production()

        gateway_order_id = payload_dict.get("order_id", "")
        record = _DUMMY_PAYMENTS.get(gateway_order_id)

        if record is None:
            raise PaymentGatewayError(
                f"Unknown dummy payment: {gateway_order_id}",
                operation="process_callback",
            )

        # Check if expired
        now = datetime.now(tz=timezone.utc)
        if now > record["expires_at"]:
            record["status"] = "expired"
            return PaymentCallbackResult(
                is_successful=False,
                amount_paisas=record["amount_paisas"],
                gateway_transaction_id=gateway_order_id,
                failure_reason="Payment link expired",
                raw_payload=payload_dict,
            )

        # Check for simulated failure (amount ending in 99)
        if record["will_fail"]:
            record["status"] = "failed"
            logger.info(
                "payment.dummy.simulated_failure",
                gateway_order_id=gateway_order_id,
            )
            return PaymentCallbackResult(
                is_successful=False,
                amount_paisas=record["amount_paisas"],
                gateway_transaction_id=gateway_order_id,
                failure_reason="Simulated payment failure (amount ends in 99 paisas)",
                raw_payload=payload_dict,
            )

        # Successful payment
        record["status"] = "completed"
        record["paid_at"] = now

        logger.info(
            "payment.dummy.completed",
            gateway_order_id=gateway_order_id,
            amount_paisas=record["amount_paisas"],
        )

        return PaymentCallbackResult(
            is_successful=True,
            amount_paisas=record["amount_paisas"],
            gateway_transaction_id=gateway_order_id,
            raw_payload=payload_dict,
        )

    async def get_payment_status(
        self,
        gateway_transaction_id: str,
    ) -> PaymentStatusResult:
        """Look up current status of a dummy payment.

        Args:
            gateway_transaction_id: The DUMMY-xxx order ID.

        Returns:
            PaymentStatusResult with current state.

        Raises:
            PaymentGatewayError: If the order ID is unknown.
        """
        self._guard_production()

        record = _DUMMY_PAYMENTS.get(gateway_transaction_id)
        if record is None:
            raise PaymentGatewayError(
                f"Unknown dummy payment: {gateway_transaction_id}",
                operation="get_payment_status",
            )

        return PaymentStatusResult(
            status=record["status"],
            gateway_transaction_id=gateway_transaction_id,
            amount_paisas=record["amount_paisas"],
            paid_at=record.get("paid_at"),
            raw_response=record,
        )

    async def cancel_payment(
        self,
        gateway_transaction_id: str,
    ) -> bool:
        """Cancel a pending dummy payment.

        Args:
            gateway_transaction_id: The DUMMY-xxx order ID.

        Returns:
            True if cancelled, False if already completed or unknown.
        """
        self._guard_production()

        record = _DUMMY_PAYMENTS.get(gateway_transaction_id)
        if record is None or record["status"] != "pending":
            return False

        record["status"] = "cancelled"
        logger.info(
            "payment.dummy.cancelled",
            gateway_order_id=gateway_transaction_id,
        )
        return True

    def get_gateway_name(self) -> str:
        """Return ``'dummy'``."""
        return "dummy"

    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return dummy gateway capabilities."""
        return {
            "supported_currencies": ["PKR"],
            "min_amount_paisas": 100,
            "max_amount_paisas": 100_000_000,
            "supports_refunds": False,
            "supports_cancellation": True,
            "link_expiry_minutes": _LINK_EXPIRY_MINUTES,
            "production_allowed": False,
        }

    async def health_check(self) -> bool:
        """Dummy gateway is always healthy (unless production)."""
        settings = get_settings()
        return settings.app_env != "production"

    # ── Internal helpers ────────────────────────────────────────────

    async def _auto_confirm(self, gateway_order_id: str) -> None:
        """Auto-confirm a pending payment after the configured delay.

        Called via asyncio.call_later() when auto_confirm is enabled.

        Args:
            gateway_order_id: The DUMMY-xxx order ID.
        """
        record = _DUMMY_PAYMENTS.get(gateway_order_id)
        if record is None or record["status"] != "pending":
            return

        result = await self.process_callback({"order_id": gateway_order_id})
        logger.info(
            "payment.dummy.auto_confirmed",
            gateway_order_id=gateway_order_id,
            is_successful=result.is_successful,
        )


def clear_dummy_payments() -> None:
    """Clear all in-memory dummy payment records.

    Used by test fixtures to reset state between tests.
    """
    _DUMMY_PAYMENTS.clear()
