"""Abstract payment gateway base class and response models.

Defines the interface that all payment gateway implementations must
satisfy.  Response models use Pydantic v2 for validation and
serialization.

Architecture::

    Order Flow / Channel Handler
             ↓
    payment_factory.get_gateway()
             ↓
       PaymentGateway (abstract)
             ↓
    [jazzcash | easypaisa | safepay | nayapay | bank_transfer | dummy]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════


class PaymentLinkResponse(BaseModel):
    """Returned by ``generate_payment_link()`` on success.

    Attributes:
        link_url: Customer-facing payment URL (or instruction text
            for bank transfer).
        gateway_order_id: The gateway's own reference for this payment
            request.
        expires_at: When the payment link becomes invalid.
        metadata: Extra gateway-specific data (QR URL, deeplink, etc.).
    """

    link_url: str
    gateway_order_id: str
    expires_at: datetime
    metadata: dict = Field(default_factory=dict)


class PaymentCallbackResult(BaseModel):
    """Returned by ``process_callback()`` after parsing a webhook payload.

    Attributes:
        is_successful: Whether the payment completed successfully.
        amount_paisas: Confirmed payment amount in paisas.
        gateway_transaction_id: The gateway's transaction identifier.
        failure_reason: Human-readable failure description (None on success).
        raw_payload: Full webhook payload for audit logging.
    """

    is_successful: bool
    amount_paisas: int
    gateway_transaction_id: str
    failure_reason: Optional[str] = None
    raw_payload: dict = Field(default_factory=dict)


class PaymentStatusResult(BaseModel):
    """Returned by ``get_payment_status()`` polling method.

    Attributes:
        status: Canonical status string (pending / completed /
            failed / expired / refunded / cancelled).
        gateway_transaction_id: The gateway's transaction identifier.
        amount_paisas: Transaction amount.
        paid_at: When payment was confirmed (None if not paid).
        raw_response: Full gateway response for debugging.
    """

    status: str
    gateway_transaction_id: str
    amount_paisas: int = 0
    paid_at: Optional[datetime] = None
    raw_response: dict = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# ABSTRACT BASE CLASS
# ═══════════════════════════════════════════════════════════════════


class PaymentGateway(ABC):
    """Abstract base class for all payment gateway implementations.

    Every concrete gateway must implement all abstract methods.  The
    ``PaymentFactory`` relies on this interface to treat all gateways
    uniformly.

    Implementations must:
    - Never store secrets in instance attributes (read from settings).
    - Always verify webhook signatures before processing callbacks.
    - Log all operations via structured Loguru calls.
    - Raise ``PaymentGatewayError`` on expected failures.
    - Raise ``PaymentSignatureError`` on signature mismatches.
    """

    # ── Payment Initiation ──────────────────────────────────────────

    @abstractmethod
    async def generate_payment_link(
        self,
        amount_paisas: int,
        reference_id: str,
        description: str,
        payer_phone: str,
    ) -> PaymentLinkResponse:
        """Generate a payment URL / instruction for the customer.

        Args:
            amount_paisas: Amount in paisas (PKR × 100).
            reference_id: Internal transaction reference (unique).
            description: Human-readable payment description.
            payer_phone: Customer WhatsApp number (E.164).

        Returns:
            PaymentLinkResponse with the customer-facing link.

        Raises:
            PaymentGatewayError: If the gateway rejects the request.
        """

    # ── Webhook Processing ──────────────────────────────────────────

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify the cryptographic signature of an incoming webhook.

        MUST be called before ``process_callback()``.

        Args:
            payload_bytes: Raw request body bytes.
            headers: HTTP request headers.

        Returns:
            True if the signature is valid.
        """

    @abstractmethod
    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Parse a verified webhook payload into a typed result.

        Call only after ``verify_webhook_signature()`` returns True.

        Args:
            payload_dict: Parsed JSON payload from the gateway.

        Returns:
            PaymentCallbackResult with payment outcome.

        Raises:
            PaymentGatewayError: If the payload cannot be parsed.
        """

    # ── Status Polling ──────────────────────────────────────────────

    @abstractmethod
    async def get_payment_status(
        self,
        gateway_transaction_id: str,
    ) -> PaymentStatusResult:
        """Poll the gateway for current payment status.

        Used for reconciliation and when webhooks are delayed.

        Args:
            gateway_transaction_id: The gateway's own transaction ID.

        Returns:
            PaymentStatusResult with current status.

        Raises:
            PaymentGatewayError: If the gateway is unreachable.
        """

    # ── Cancellation ────────────────────────────────────────────────

    @abstractmethod
    async def cancel_payment(
        self,
        gateway_transaction_id: str,
    ) -> bool:
        """Attempt to cancel or void a pending payment.

        Args:
            gateway_transaction_id: The gateway's transaction ID.

        Returns:
            True if cancellation succeeded, False if not supported
            or payment already completed.

        Raises:
            PaymentGatewayError: On gateway communication failure.
        """

    # ── Identity ────────────────────────────────────────────────────

    @abstractmethod
    def get_gateway_name(self) -> str:
        """Return the canonical gateway identifier string.

        Returns:
            Gateway name matching ``GatewayType`` enum value
            (e.g. ``"jazzcash"``, ``"dummy"``).
        """

    @abstractmethod
    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return gateway capabilities and limits.

        Returns:
            Dict with keys like ``supported_currencies``,
            ``min_amount_paisas``, ``max_amount_paisas``,
            ``supports_refunds``, ``supports_cancellation``, etc.
        """

    # ── Health Check ────────────────────────────────────────────────

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify that the gateway is reachable and operational.

        Returns:
            True if the gateway responds within acceptable latency.
        """
