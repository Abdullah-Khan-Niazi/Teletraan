"""Pydantic models for the orders, order_items, and order_status_history tables.

Maps migrations 009, 010, and 011 to typed Pydantic v2 models.
Three model groups:

* **Order / OrderCreate / OrderUpdate** — the ``orders`` table.
* **OrderItem / OrderItemCreate** — the ``order_items`` table (immutable).
* **OrderStatusHistory / OrderStatusHistoryCreate** — the
  ``order_status_history`` table (immutable append-only).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import (
    InputMethod,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    StatusChangeActor,
)


# ═══════════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════════


class Order(BaseModel):
    """Full order row returned from DB.

    Attributes:
        id: Primary key UUID.
        order_number: Human-readable unique order number.
        distributor_id: FK to distributors — tenant boundary.
        customer_id: FK to customers who placed the order.
        status: Current order lifecycle state.
        subtotal_paisas: Sum of line totals before discounts in paisas.
        discount_paisas: Total discount applied in paisas.
        delivery_charges_paisas: Delivery fee in paisas.
        total_paisas: Final total in paisas.
        payment_status: Payment lifecycle state.
        payment_method: How the customer will pay.
        delivery_address: Delivery address text.
        delivery_zone_id: FK to delivery_zones.
        estimated_delivery_at: Estimated delivery timestamp.
        dispatched_at: Timestamp when dispatched.
        delivered_at: Timestamp when delivered.
        notes: Customer-facing notes.
        internal_notes: Distributor-only notes.
        discount_requests: List of discount-request objects.
        discount_approval_status: Aggregate discount approval state.
        source: Where the order originated.
        is_quick_reorder: Whether this is a quick-reorder copy.
        source_order_id: FK to original order for quick reorders.
        whatsapp_logged_at: When order was sent to WhatsApp group.
        excel_logged_at: When order was written to Excel.
        order_context_snapshot: Frozen order context at confirmation.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    order_number: str
    distributor_id: UUID
    customer_id: UUID
    status: OrderStatus = OrderStatus.PENDING
    subtotal_paisas: int = 0
    discount_paisas: int = 0
    delivery_charges_paisas: int = 0
    total_paisas: int = 0
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    payment_method: Optional[PaymentMethod] = None
    delivery_address: Optional[str] = None
    delivery_zone_id: Optional[UUID] = None
    estimated_delivery_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None
    discount_requests: list = Field(default_factory=list)
    discount_approval_status: str = "not_requested"
    source: OrderSource = OrderSource.WHATSAPP
    is_quick_reorder: bool = False
    source_order_id: Optional[UUID] = None
    whatsapp_logged_at: Optional[datetime] = None
    excel_logged_at: Optional[datetime] = None
    order_context_snapshot: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    """Fields for creating a new order.

    Attributes:
        order_number: Unique human-readable order number.
        distributor_id: FK to distributors.
        customer_id: FK to customers.
        status: Initial order state.
        subtotal_paisas: Subtotal in paisas.
        discount_paisas: Discount in paisas.
        delivery_charges_paisas: Delivery fee in paisas.
        total_paisas: Total in paisas.
        payment_status: Initial payment state.
        payment_method: Payment method.
        delivery_address: Delivery address.
        delivery_zone_id: FK to delivery_zones.
        estimated_delivery_at: Estimated delivery timestamp.
        notes: Customer-facing notes.
        internal_notes: Distributor-only notes.
        discount_requests: Discount-request objects.
        discount_approval_status: Discount approval state.
        source: Order origination source.
        is_quick_reorder: Quick reorder flag.
        source_order_id: FK to original order.
        order_context_snapshot: Frozen context snapshot.
        metadata: Arbitrary metadata.
    """

    order_number: str
    distributor_id: UUID
    customer_id: UUID
    status: OrderStatus = OrderStatus.PENDING
    subtotal_paisas: int = 0
    discount_paisas: int = 0
    delivery_charges_paisas: int = 0
    total_paisas: int = 0
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    payment_method: Optional[PaymentMethod] = None
    delivery_address: Optional[str] = None
    delivery_zone_id: Optional[UUID] = None
    estimated_delivery_at: Optional[datetime] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None
    discount_requests: list = Field(default_factory=list)
    discount_approval_status: str = "not_requested"
    source: OrderSource = OrderSource.WHATSAPP
    is_quick_reorder: bool = False
    source_order_id: Optional[UUID] = None
    order_context_snapshot: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class OrderUpdate(BaseModel):
    """Fields for updating an order (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        status: Updated order state.
        subtotal_paisas: Updated subtotal in paisas.
        discount_paisas: Updated discount in paisas.
        delivery_charges_paisas: Updated delivery fee in paisas.
        total_paisas: Updated total in paisas.
        payment_status: Updated payment state.
        payment_method: Updated payment method.
        delivery_address: Updated delivery address.
        delivery_zone_id: Updated delivery zone.
        estimated_delivery_at: Updated estimated delivery.
        dispatched_at: Updated dispatch timestamp.
        delivered_at: Updated delivery timestamp.
        notes: Updated notes.
        internal_notes: Updated internal notes.
        discount_requests: Updated discount requests.
        discount_approval_status: Updated discount approval state.
        is_quick_reorder: Updated quick reorder flag.
        whatsapp_logged_at: Updated WhatsApp log timestamp.
        excel_logged_at: Updated Excel log timestamp.
        order_context_snapshot: Updated context snapshot.
        metadata: Updated metadata dict.
    """

    status: Optional[OrderStatus] = None
    subtotal_paisas: Optional[int] = None
    discount_paisas: Optional[int] = None
    delivery_charges_paisas: Optional[int] = None
    total_paisas: Optional[int] = None
    payment_status: Optional[PaymentStatus] = None
    payment_method: Optional[PaymentMethod] = None
    delivery_address: Optional[str] = None
    delivery_zone_id: Optional[UUID] = None
    estimated_delivery_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None
    discount_requests: Optional[list] = None
    discount_approval_status: Optional[str] = None
    is_quick_reorder: Optional[bool] = None
    whatsapp_logged_at: Optional[datetime] = None
    excel_logged_at: Optional[datetime] = None
    order_context_snapshot: Optional[dict] = None
    metadata: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════
# ORDER ITEMS
# ═══════════════════════════════════════════════════════════════════


class OrderItem(BaseModel):
    """Full order_item row returned from DB.

    Order items are immutable after creation — no update model.

    Attributes:
        id: Primary key UUID.
        order_id: FK to orders.
        distributor_id: FK to distributors — tenant boundary.
        catalog_id: FK to catalog (None for unlisted items).
        medicine_name_raw: Raw customer input before normalisation.
        medicine_name: Normalised medicine name.
        unit: Sale unit (strip, bottle, etc.).
        quantity_ordered: Number of units ordered.
        quantity_fulfilled: Number of units actually fulfilled.
        price_per_unit_paisas: Price per unit in paisas.
        line_total_paisas: Total for this line in paisas.
        discount_paisas: Discount on this line in paisas.
        bonus_units_given: Free bonus units awarded.
        is_out_of_stock_order: Ordered despite being OOS.
        is_unlisted_item: Item not found in catalog.
        input_method: How the item was supplied (text/voice/button).
        fuzzy_match_score: Confidence of the fuzzy match (0-100).
        notes: Item-level notes.
        created_at: Row creation timestamp.
    """

    id: UUID
    order_id: UUID
    distributor_id: UUID
    catalog_id: Optional[UUID] = None
    medicine_name_raw: Optional[str] = None
    medicine_name: str
    unit: Optional[str] = None
    quantity_ordered: int
    quantity_fulfilled: int = 0
    price_per_unit_paisas: int
    line_total_paisas: int
    discount_paisas: int = 0
    bonus_units_given: int = 0
    is_out_of_stock_order: bool = False
    is_unlisted_item: bool = False
    input_method: Optional[InputMethod] = None
    fuzzy_match_score: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderItemCreate(BaseModel):
    """Fields for creating a new order item.

    Attributes:
        order_id: FK to orders.
        distributor_id: FK to distributors.
        catalog_id: FK to catalog (None for unlisted).
        medicine_name_raw: Raw customer input.
        medicine_name: Normalised medicine name.
        unit: Sale unit.
        quantity_ordered: Units ordered.
        quantity_fulfilled: Units fulfilled.
        price_per_unit_paisas: Price per unit in paisas.
        line_total_paisas: Line total in paisas.
        discount_paisas: Line discount in paisas.
        bonus_units_given: Bonus units.
        is_out_of_stock_order: OOS order flag.
        is_unlisted_item: Unlisted item flag.
        input_method: Input method.
        fuzzy_match_score: Match confidence.
        notes: Item-level notes.
    """

    order_id: UUID
    distributor_id: UUID
    catalog_id: Optional[UUID] = None
    medicine_name_raw: Optional[str] = None
    medicine_name: str
    unit: Optional[str] = None
    quantity_ordered: int
    quantity_fulfilled: int = 0
    price_per_unit_paisas: int
    line_total_paisas: int
    discount_paisas: int = 0
    bonus_units_given: int = 0
    is_out_of_stock_order: bool = False
    is_unlisted_item: bool = False
    input_method: Optional[InputMethod] = None
    fuzzy_match_score: Optional[float] = None
    notes: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# ORDER STATUS HISTORY
# ═══════════════════════════════════════════════════════════════════


class OrderStatusHistory(BaseModel):
    """Full order_status_history row returned from DB.

    Append-only audit table — no update model.

    Attributes:
        id: Primary key UUID.
        order_id: FK to orders.
        distributor_id: FK to distributors — tenant boundary.
        from_status: Previous status (None for initial creation).
        to_status: New status.
        changed_by: Who triggered the transition.
        notes: Transition notes.
        created_at: Row creation timestamp.
    """

    id: UUID
    order_id: UUID
    distributor_id: UUID
    from_status: Optional[str] = None
    to_status: str
    changed_by: Optional[StatusChangeActor] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderStatusHistoryCreate(BaseModel):
    """Fields for creating a new order status history entry.

    Attributes:
        order_id: FK to orders.
        distributor_id: FK to distributors.
        from_status: Previous status.
        to_status: New status.
        changed_by: Who triggered the transition.
        notes: Transition notes.
    """

    order_id: UUID
    distributor_id: UUID
    from_status: Optional[str] = None
    to_status: str
    changed_by: Optional[StatusChangeActor] = None
    notes: Optional[str] = None
