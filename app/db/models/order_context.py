"""Pydantic v2 model for the sessions.pending_order_draft JSONB column.

This is the COMPLETE specification of what must be stored in
``sessions.pending_order_draft`` for every order in progress.  Every
field is required unless marked Optional.  The context must be
sufficient to **fully reconstruct the order conversation state after a
complete process restart**.  Update on every state transition — never
leave stale.

Location reference:
- Schema spec: ``.github/prompts/07_order_context_schema.prompt.md``
- Context CRUD: ``app/orders/context_manager.py``
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.constants import (
    AIConfidence,
    AmbiguityType,
    DiscountRequestStatus,
    DiscountRequestType,
    InputMethod,
    OrderFlowStep,
)


# ═══════════════════════════════════════════════════════════════════
# SUB-MODELS
# ═══════════════════════════════════════════════════════════════════


class ItemDiscountRequest(BaseModel):
    """Discount request on an individual line item."""

    request_type: DiscountRequestType
    requested_value: str  # e.g. '2+1', '10%', 'PKR 50'
    status: DiscountRequestStatus = DiscountRequestStatus.PENDING


class OrderItemDraft(BaseModel):
    """Single item in the order draft.

    Items are never deleted — set ``cancelled=True`` for audit trail.
    """

    line_id: UUID = Field(default_factory=uuid4)
    catalog_id: Optional[UUID] = None
    medicine_name_raw: str
    medicine_name_matched: str = ""
    medicine_name_display: str = ""
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    unit: str = "strip"
    quantity_requested: int = 1
    price_per_unit_paisas: int = 0  # snapshot at time of addition
    line_subtotal_paisas: int = 0  # quantity × price before discount
    discount_applied_paisas: int = 0
    bonus_units: int = 0
    line_total_paisas: int = 0  # after discount
    is_out_of_stock: bool = False
    stock_available_at_add: Optional[int] = None
    is_unlisted: bool = False
    is_confirmed_by_customer: bool = False
    cancelled: bool = False  # never delete — set this for audit
    input_method: InputMethod = InputMethod.TEXT
    voice_transcription: Optional[str] = None
    fuzzy_match_score: Optional[float] = None
    fuzzy_alternatives_shown: Optional[list[str]] = None
    added_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    discount_request: Optional[ItemDiscountRequest] = None


class OrderLevelDiscountRequest(BaseModel):
    """Discount request on the entire order."""

    request_text: str  # exactly what the customer said
    status: DiscountRequestStatus = DiscountRequestStatus.PENDING


class AutoAppliedDiscount(BaseModel):
    """Record of a discount rule that was automatically applied."""

    rule_id: UUID
    rule_name: str = ""
    amount_paisas: int = 0


class PricingSnapshot(BaseModel):
    """Pricing summary recalculated on every item change."""

    subtotal_paisas: int = 0
    item_discounts_paisas: int = 0
    order_discount_paisas: int = 0
    auto_applied_discounts: list[AutoAppliedDiscount] = Field(default_factory=list)
    delivery_charges_paisas: int = 0
    total_paisas: int = 0
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now().astimezone()
    )


class DeliveryInfo(BaseModel):
    """Delivery details for the order."""

    address: Optional[str] = None
    zone_id: Optional[UUID] = None
    zone_name: Optional[str] = None
    estimated_delivery_hours: Optional[int] = None
    delivery_day_display: Optional[str] = None  # e.g. "Kal ya parson"
    address_confirmed: bool = False


class PendingClarification(BaseModel):
    """A single ambiguity that needs customer clarification."""

    line_id: UUID
    ambiguity_type: AmbiguityType
    options_presented: list[str] = Field(default_factory=list)
    resolved: bool = False


class AmbiguityResolution(BaseModel):
    """Tracks all pending ambiguity clarifications."""

    pending_clarifications: list[PendingClarification] = Field(default_factory=list)
    all_resolved: bool = True


class VoiceOrderContext(BaseModel):
    """Context for orders initiated via voice message."""

    original_transcription: str
    items_extracted_count: int = 0
    transcription_confirmed_by_customer: bool = False
    audio_duration_seconds: float = 0.0
    ai_confidence: AIConfidence = AIConfidence.MEDIUM


class QuickReorderSource(BaseModel):
    """Context when this order is a quick reorder of a previous one."""

    source_order_id: UUID
    source_order_number: str
    items_changed: bool = False


# ═══════════════════════════════════════════════════════════════════
# TOP-LEVEL ORDER CONTEXT
# ═══════════════════════════════════════════════════════════════════


class OrderContext(BaseModel):
    """Complete order context stored in sessions.pending_order_draft.

    This model is the single source of truth for an in-progress order.
    It must be sufficient to fully reconstruct the conversation state
    after a complete process restart.

    Update rules:
    1. Update ``last_modified_at`` on every field change.
    2. Update ``pricing_snapshot`` whenever any item is added/removed/modified.
    3. Never delete items — set ``cancelled=True`` instead (for audit).
    4. Append to ``voice_order_context`` only — never overwrite.
    5. Persist to DB on every state transition — not just at end.
    6. When order is confirmed, clear ``pending_order_draft`` to ``{}``.
    7. Generate ``ai_context_summary`` when item count exceeds 8.
    """

    order_context_version: str = "1.0"
    session_order_id: UUID = Field(default_factory=uuid4)
    flow_step: OrderFlowStep = OrderFlowStep.ITEM_COLLECTION
    initiated_at: datetime = Field(
        default_factory=lambda: datetime.now().astimezone()
    )
    last_modified_at: datetime = Field(
        default_factory=lambda: datetime.now().astimezone()
    )
    total_messages_in_order: int = 0

    # Items
    items: list[OrderItemDraft] = Field(default_factory=list)

    # Order-level discount
    order_level_discount_request: Optional[OrderLevelDiscountRequest] = None

    # Pricing
    pricing_snapshot: PricingSnapshot = Field(default_factory=PricingSnapshot)

    # Delivery
    delivery: DeliveryInfo = Field(default_factory=DeliveryInfo)

    # Ambiguity
    ambiguity_resolution: AmbiguityResolution = Field(
        default_factory=AmbiguityResolution
    )

    # Voice context
    voice_order_context: Optional[VoiceOrderContext] = None

    # Quick reorder
    quick_reorder_source: Optional[QuickReorderSource] = None

    # Trailing fields
    customer_notes: Optional[str] = None
    bill_shown_at: Optional[datetime] = None
    bill_shown_count: int = 0
    confirmation_requested_at: Optional[datetime] = None
    order_cancelled: bool = False
    cancellation_reason: Optional[str] = None
    ai_context_summary: Optional[str] = None

    model_config = {"from_attributes": True}
