"""Pydantic models for the payments table.

Maps the ``payments`` table defined in migration 012 to typed
Pydantic v2 models.  Three variants:

* **Payment** — full row returned from the database.
* **PaymentCreate** — fields required (or optional) for INSERT.
* **PaymentUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import GatewayPaymentStatus, GatewayType, PaymentType


class Payment(BaseModel):
    """Full payment row returned from DB.

    Attributes:
        id: Primary key UUID.
        transaction_reference: Unique reference string.
        payment_type: What the payment is for.
        distributor_id: FK to distributors (nullable for B2B payments).
        order_id: FK to orders (nullable for subscription payments).
        customer_id: FK to customers (nullable for subscription payments).
        gateway: Payment gateway identifier.
        gateway_transaction_id: ID returned by the gateway.
        gateway_order_id: Order ID on the gateway side.
        amount_paisas: Payment amount in paisas.
        currency: ISO 4217 currency code.
        status: Gateway-level payment state.
        payment_link: URL for customer payment page.
        payment_link_expires_at: When the payment link expires.
        paid_at: When payment was confirmed.
        gateway_response: Raw gateway callback/response JSON.
        failure_reason: Human-readable failure description.
        refund_amount_paisas: Refunded amount in paisas.
        refunded_at: When refund was processed.
        screenshot_storage_path: Path to manual payment screenshot.
        manual_confirmed_at: When manual payment was confirmed.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    transaction_reference: str
    payment_type: PaymentType
    distributor_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    gateway: GatewayType
    gateway_transaction_id: Optional[str] = None
    gateway_order_id: Optional[str] = None
    amount_paisas: int
    currency: str = "PKR"
    status: GatewayPaymentStatus = GatewayPaymentStatus.PENDING
    payment_link: Optional[str] = None
    payment_link_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    gateway_response: dict = Field(default_factory=dict)
    failure_reason: Optional[str] = None
    refund_amount_paisas: int = 0
    refunded_at: Optional[datetime] = None
    screenshot_storage_path: Optional[str] = None
    manual_confirmed_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):
    """Fields for creating a new payment record.

    Attributes:
        transaction_reference: Unique reference string.
        payment_type: What the payment is for.
        distributor_id: FK to distributors.
        order_id: FK to orders.
        customer_id: FK to customers.
        gateway: Payment gateway identifier.
        gateway_transaction_id: Gateway's transaction ID.
        gateway_order_id: Gateway's order ID.
        amount_paisas: Payment amount in paisas.
        currency: ISO 4217 currency code.
        status: Initial payment state.
        payment_link: Customer payment URL.
        payment_link_expires_at: Payment link expiry.
        metadata: Arbitrary metadata.
    """

    transaction_reference: str
    payment_type: PaymentType
    distributor_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    gateway: GatewayType
    gateway_transaction_id: Optional[str] = None
    gateway_order_id: Optional[str] = None
    amount_paisas: int
    currency: str = "PKR"
    status: GatewayPaymentStatus = GatewayPaymentStatus.PENDING
    payment_link: Optional[str] = None
    payment_link_expires_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)


class PaymentUpdate(BaseModel):
    """Fields for updating a payment (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        gateway_transaction_id: Updated gateway transaction ID.
        gateway_order_id: Updated gateway order ID.
        status: Updated payment state.
        payment_link: Updated payment URL.
        payment_link_expires_at: Updated link expiry.
        paid_at: Updated confirmation timestamp.
        gateway_response: Updated gateway response JSON.
        failure_reason: Updated failure description.
        refund_amount_paisas: Updated refund amount in paisas.
        refunded_at: Updated refund timestamp.
        screenshot_storage_path: Updated screenshot path.
        manual_confirmed_at: Updated manual confirmation timestamp.
        metadata: Updated metadata dict.
    """

    gateway_transaction_id: Optional[str] = None
    gateway_order_id: Optional[str] = None
    status: Optional[GatewayPaymentStatus] = None
    payment_link: Optional[str] = None
    payment_link_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    gateway_response: Optional[dict] = None
    failure_reason: Optional[str] = None
    refund_amount_paisas: Optional[int] = None
    refunded_at: Optional[datetime] = None
    screenshot_storage_path: Optional[str] = None
    manual_confirmed_at: Optional[datetime] = None
    metadata: Optional[dict] = None
