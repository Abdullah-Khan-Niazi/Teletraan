"""Order context manager — all CRUD operations on OrderContext.

Pure service module operating on ``OrderContext`` Pydantic objects.
Persistence is handled via ``save_context_to_session()`` which calls
the session repository.  Every mutation updates ``last_modified_at``
and recalculates ``pricing_snapshot`` where applicable.

Location reference:
- Pydantic model: ``app/db/models/order_context.py``
- Session repo: ``app/db/repositories/session_repo.py``
- Spec: ``.github/prompts/07_order_context_schema.prompt.md``
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from loguru import logger

from app.core.constants import (
    AI_CONTEXT_SUMMARY_ITEM_THRESHOLD,
    AIConfidence,
    AmbiguityType,
    DiscountRequestStatus,
    DiscountRequestType,
    InputMethod,
    OrderFlowStep,
)
from app.db.models.order_context import (
    AmbiguityResolution,
    AutoAppliedDiscount,
    DeliveryInfo,
    ItemDiscountRequest,
    OrderContext,
    OrderItemDraft,
    OrderLevelDiscountRequest,
    PendingClarification,
    PricingSnapshot,
    QuickReorderSource,
    VoiceOrderContext,
)
from app.db.models.session import Session


# ═══════════════════════════════════════════════════════════════════
# CONTEXT CREATION / RETRIEVAL
# ═══════════════════════════════════════════════════════════════════


def create_empty_context(
    session_order_id: str | None = None,
) -> OrderContext:
    """Initialise a blank OrderContext.

    Args:
        session_order_id: Optional pre-generated UUID string.
            If None, a fresh UUID is generated.

    Returns:
        Empty OrderContext ready for item collection.
    """
    now = datetime.now().astimezone()
    order_id = UUID(session_order_id) if session_order_id else uuid4()

    ctx = OrderContext(
        session_order_id=order_id,
        flow_step=OrderFlowStep.ITEM_COLLECTION,
        initiated_at=now,
        last_modified_at=now,
        total_messages_in_order=0,
        items=[],
        pricing_snapshot=PricingSnapshot(
            subtotal_paisas=0,
            item_discounts_paisas=0,
            order_discount_paisas=0,
            delivery_charges_paisas=0,
            total_paisas=0,
            calculated_at=now,
        ),
        delivery=DeliveryInfo(),
        ambiguity_resolution=AmbiguityResolution(),
    )
    logger.debug("context.created", session_order_id=str(order_id))
    return ctx


def get_context_from_session(session: Session) -> OrderContext:
    """Deserialise ``session.pending_order_draft`` to OrderContext.

    If the draft is empty or ``{}``, returns a fresh blank context.

    Args:
        session: Session row from the database.

    Returns:
        OrderContext — either deserialised or newly created.
    """
    draft = session.pending_order_draft
    if not draft:
        logger.debug(
            "context.empty_draft",
            session_id=str(session.id),
        )
        return create_empty_context()

    try:
        ctx = OrderContext.model_validate(draft)
        logger.debug(
            "context.loaded_from_session",
            session_id=str(session.id),
            flow_step=ctx.flow_step,
            items_count=len(ctx.items),
        )
        return ctx
    except Exception as exc:
        logger.warning(
            "context.deserialisation_failed",
            session_id=str(session.id),
            error=str(exc),
        )
        return create_empty_context()


async def save_context_to_session(
    context: OrderContext,
    session_id: str,
    session_repo: object,
) -> None:
    """Serialise the context and persist it to the session row.

    Updates ``last_modified_at`` before writing.

    Args:
        context: The current order context.
        session_id: UUID string of the session.
        session_repo: SessionRepository instance (typed as object
            to avoid circular imports).

    Raises:
        DatabaseError: If the repository write fails.
    """
    context.last_modified_at = datetime.now().astimezone()
    draft = context.model_dump(mode="json")

    await session_repo.update_order_draft(session_id, draft)  # type: ignore[union-attr]
    logger.debug(
        "context.saved",
        session_id=session_id,
        flow_step=context.flow_step,
        items_count=len(context.items),
    )


# ═══════════════════════════════════════════════════════════════════
# ITEM OPERATIONS
# ═══════════════════════════════════════════════════════════════════


def add_item_to_context(
    context: OrderContext,
    *,
    catalog_id: str | None = None,
    name_raw: str,
    name_matched: str = "",
    name_display: str = "",
    generic_name: str | None = None,
    brand_name: str | None = None,
    strength: str | None = None,
    form: str | None = None,
    unit: str = "strip",
    quantity: int = 1,
    price_per_unit_paisas: int = 0,
    is_out_of_stock: bool = False,
    stock_available: int | None = None,
    is_unlisted: bool = False,
    input_method: InputMethod = InputMethod.TEXT,
    voice_transcription: str | None = None,
    fuzzy_match_score: float | None = None,
    fuzzy_alternatives_shown: list[str] | None = None,
) -> tuple[OrderContext, str]:
    """Add a new item to the order context.

    Recalculates ``pricing_snapshot`` after addition.

    Args:
        context: Current order context.
        catalog_id: UUID string of catalog item (None if unlisted).
        name_raw: Exactly what the customer typed/said.
        name_matched: Name after fuzzy matching.
        name_display: Clean display name shown to customer.
        generic_name: Generic medicine name.
        brand_name: Brand name.
        strength: e.g. '500mg'.
        form: e.g. 'tablet', 'syrup'.
        unit: Unit of measure (strip, box, etc.).
        quantity: Requested quantity.
        price_per_unit_paisas: Price snapshot at time of addition.
        is_out_of_stock: Whether item is currently out of stock.
        stock_available: Stock quantity at time of addition.
        is_unlisted: True if not in catalog.
        input_method: How the customer supplied this item.
        voice_transcription: Original transcription if voice input.
        fuzzy_match_score: RapidFuzz score (None if exact or unlisted).
        fuzzy_alternatives_shown: Other options shown during matching.

    Returns:
        Tuple of (updated context, new line_id string).
    """
    line_id = uuid4()
    line_subtotal = quantity * price_per_unit_paisas
    line_total = line_subtotal  # No discount yet

    item = OrderItemDraft(
        line_id=line_id,
        catalog_id=UUID(catalog_id) if catalog_id else None,
        medicine_name_raw=name_raw,
        medicine_name_matched=name_matched or name_raw,
        medicine_name_display=name_display or name_matched or name_raw,
        generic_name=generic_name,
        brand_name=brand_name,
        strength=strength,
        form=form,
        unit=unit,
        quantity_requested=quantity,
        price_per_unit_paisas=price_per_unit_paisas,
        line_subtotal_paisas=line_subtotal,
        discount_applied_paisas=0,
        bonus_units=0,
        line_total_paisas=line_total,
        is_out_of_stock=is_out_of_stock,
        stock_available_at_add=stock_available,
        is_unlisted=is_unlisted,
        is_confirmed_by_customer=False,
        cancelled=False,
        input_method=input_method,
        voice_transcription=voice_transcription,
        fuzzy_match_score=fuzzy_match_score,
        fuzzy_alternatives_shown=fuzzy_alternatives_shown,
    )

    context.items.append(item)
    context.total_messages_in_order += 1
    _recalculate_pricing_snapshot(context)

    logger.info(
        "context.item_added",
        line_id=str(line_id),
        name_raw=name_raw,
        quantity=quantity,
        unit=unit,
        price=price_per_unit_paisas,
    )
    return context, str(line_id)


def remove_item_from_context(
    context: OrderContext,
    line_id: str,
) -> OrderContext:
    """Mark an item as cancelled (never delete — audit trail).

    Recalculates ``pricing_snapshot`` after removal.

    Args:
        context: Current order context.
        line_id: UUID string of the line item to cancel.

    Returns:
        Updated context.
    """
    target_uuid = UUID(line_id)
    found = False
    for item in context.items:
        if item.line_id == target_uuid and not item.cancelled:
            item.cancelled = True
            found = True
            logger.info("context.item_removed", line_id=line_id)
            break

    if not found:
        logger.warning("context.item_not_found_for_removal", line_id=line_id)

    _recalculate_pricing_snapshot(context)
    return context


def update_item_quantity(
    context: OrderContext,
    line_id: str,
    new_quantity: int,
) -> OrderContext:
    """Update quantity of an existing item and recalculate pricing.

    Args:
        context: Current order context.
        line_id: UUID string of the line item.
        new_quantity: New quantity value (must be > 0).

    Returns:
        Updated context.
    """
    target_uuid = UUID(line_id)
    for item in context.items:
        if item.line_id == target_uuid and not item.cancelled:
            item.quantity_requested = new_quantity
            item.line_subtotal_paisas = new_quantity * item.price_per_unit_paisas
            item.line_total_paisas = (
                item.line_subtotal_paisas - item.discount_applied_paisas
            )
            logger.info(
                "context.item_quantity_updated",
                line_id=line_id,
                new_quantity=new_quantity,
            )
            break

    _recalculate_pricing_snapshot(context)
    return context


# ═══════════════════════════════════════════════════════════════════
# DISCOUNT OPERATIONS
# ═══════════════════════════════════════════════════════════════════


def apply_discount_to_item(
    context: OrderContext,
    line_id: str,
    discount_data: dict,
) -> OrderContext:
    """Apply a discount to a specific item and recalculate pricing.

    Args:
        context: Current order context.
        line_id: UUID string of the line item.
        discount_data: Dict with 'request_type', 'requested_value',
            'status', and optionally 'discount_amount_paisas',
            'bonus_units'.

    Returns:
        Updated context.
    """
    target_uuid = UUID(line_id)
    for item in context.items:
        if item.line_id == target_uuid and not item.cancelled:
            item.discount_request = ItemDiscountRequest(
                request_type=DiscountRequestType(
                    discount_data.get("request_type", "flat_amount")
                ),
                requested_value=discount_data.get("requested_value", ""),
                status=DiscountRequestStatus(
                    discount_data.get("status", "pending")
                ),
            )
            discount_amount = discount_data.get("discount_amount_paisas", 0)
            item.discount_applied_paisas = discount_amount
            item.bonus_units = discount_data.get("bonus_units", 0)
            item.line_total_paisas = (
                item.line_subtotal_paisas - discount_amount
            )
            logger.info(
                "context.item_discount_applied",
                line_id=line_id,
                discount_amount=discount_amount,
            )
            break

    _recalculate_pricing_snapshot(context)
    return context


def apply_order_level_discount(
    context: OrderContext,
    discount_data: dict,
) -> OrderContext:
    """Apply a discount at the order level.

    Args:
        context: Current order context.
        discount_data: Dict with 'request_text', 'status', and
            optionally 'discount_amount_paisas'.

    Returns:
        Updated context.
    """
    context.order_level_discount_request = OrderLevelDiscountRequest(
        request_text=discount_data.get("request_text", ""),
        status=DiscountRequestStatus(
            discount_data.get("status", "pending")
        ),
    )
    amount = discount_data.get("discount_amount_paisas", 0)
    context.pricing_snapshot.order_discount_paisas = amount

    logger.info(
        "context.order_discount_applied",
        discount_amount=amount,
    )
    _recalculate_pricing_snapshot(context)
    return context


# ═══════════════════════════════════════════════════════════════════
# VOICE CONTEXT
# ═══════════════════════════════════════════════════════════════════


def add_voice_context(
    context: OrderContext,
    transcription: str,
    duration: float,
    confidence: str,
    confirmed: bool = False,
) -> OrderContext:
    """Populate ``voice_order_context`` for voice-initiated orders.

    Appends only — never overwrites existing voice context data.

    Args:
        context: Current order context.
        transcription: Full raw transcription of the voice message.
        duration: Audio duration in seconds.
        confidence: 'high', 'medium', or 'low'.
        confirmed: Whether the customer confirmed the transcription.

    Returns:
        Updated context.
    """
    if context.voice_order_context is None:
        context.voice_order_context = VoiceOrderContext(
            original_transcription=transcription,
            items_extracted_count=0,
            transcription_confirmed_by_customer=confirmed,
            audio_duration_seconds=duration,
            ai_confidence=AIConfidence(confidence),
        )
    else:
        # Append — update counts and confirmation status only
        vc = context.voice_order_context
        vc.transcription_confirmed_by_customer = confirmed
        vc.items_extracted_count = len(
            [i for i in context.items if not i.cancelled]
        )

    context.last_modified_at = datetime.now().astimezone()
    logger.info(
        "context.voice_context_added",
        duration=duration,
        confidence=confidence,
    )
    return context


# ═══════════════════════════════════════════════════════════════════
# DELIVERY
# ═══════════════════════════════════════════════════════════════════


def set_delivery(
    context: OrderContext,
    address: str | None = None,
    zone_id: str | None = None,
    zone_name: str | None = None,
    estimated_delivery_hours: int | None = None,
    delivery_day_display: str | None = None,
    delivery_charges_paisas: int = 0,
) -> OrderContext:
    """Set or update delivery details and recalculate pricing.

    Args:
        context: Current order context.
        address: Delivery address.
        zone_id: UUID string of the delivery zone.
        zone_name: Human-readable zone name.
        estimated_delivery_hours: Estimated delivery time.
        delivery_day_display: e.g. 'Kal ya parson'.
        delivery_charges_paisas: Delivery fee in paisas.

    Returns:
        Updated context.
    """
    context.delivery = DeliveryInfo(
        address=address,
        zone_id=UUID(zone_id) if zone_id else None,
        zone_name=zone_name,
        estimated_delivery_hours=estimated_delivery_hours,
        delivery_day_display=delivery_day_display,
        address_confirmed=bool(address),
    )
    context.pricing_snapshot.delivery_charges_paisas = delivery_charges_paisas

    _recalculate_pricing_snapshot(context)
    logger.info(
        "context.delivery_set",
        zone_name=zone_name,
        charges=delivery_charges_paisas,
    )
    return context


# ═══════════════════════════════════════════════════════════════════
# FLOW LIFECYCLE
# ═══════════════════════════════════════════════════════════════════


def mark_bill_shown(context: OrderContext) -> OrderContext:
    """Record that the bill preview was shown to the customer.

    Increments ``bill_shown_count`` and sets ``bill_shown_at``.

    Args:
        context: Current order context.

    Returns:
        Updated context.
    """
    context.bill_shown_count += 1
    context.bill_shown_at = datetime.now().astimezone()
    context.flow_step = OrderFlowStep.BILL_PREVIEW
    context.last_modified_at = datetime.now().astimezone()
    logger.info(
        "context.bill_shown",
        count=context.bill_shown_count,
    )
    return context


def mark_confirmed(context: OrderContext) -> OrderContext:
    """Record that confirmation has been requested from the customer.

    Args:
        context: Current order context.

    Returns:
        Updated context.
    """
    context.confirmation_requested_at = datetime.now().astimezone()
    context.flow_step = OrderFlowStep.FINAL_CONFIRMATION
    context.last_modified_at = datetime.now().astimezone()
    logger.info("context.confirmation_requested")
    return context


def cancel_order(
    context: OrderContext,
    reason: str,
) -> OrderContext:
    """Cancel the order with a reason.

    Args:
        context: Current order context.
        reason: Cancellation reason.

    Returns:
        Updated context with ``order_cancelled=True``.
    """
    context.order_cancelled = True
    context.cancellation_reason = reason
    context.flow_step = OrderFlowStep.COMPLETE
    context.last_modified_at = datetime.now().astimezone()
    logger.info("context.order_cancelled", reason=reason)
    return context


# ═══════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════


def validate_context(context: OrderContext) -> list[str]:
    """Check the context for consistency errors.

    Validates required fields, positive quantities, and consistent
    pricing across all active items.

    Args:
        context: Order context to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    active_items = [i for i in context.items if not i.cancelled]

    for item in active_items:
        if not item.medicine_name_raw:
            errors.append(f"Item {item.line_id}: missing medicine_name_raw")
        if item.quantity_requested <= 0:
            errors.append(
                f"Item {item.line_id}: quantity must be positive, "
                f"got {item.quantity_requested}"
            )
        if item.price_per_unit_paisas < 0:
            errors.append(
                f"Item {item.line_id}: price cannot be negative"
            )
        expected_subtotal = (
            item.quantity_requested * item.price_per_unit_paisas
        )
        if item.line_subtotal_paisas != expected_subtotal:
            errors.append(
                f"Item {item.line_id}: line_subtotal_paisas mismatch "
                f"(expected {expected_subtotal}, got {item.line_subtotal_paisas})"
            )
        expected_total = item.line_subtotal_paisas - item.discount_applied_paisas
        if item.line_total_paisas != expected_total:
            errors.append(
                f"Item {item.line_id}: line_total_paisas mismatch "
                f"(expected {expected_total}, got {item.line_total_paisas})"
            )

    # Pricing snapshot consistency
    expected_subtotal_all = sum(i.line_total_paisas for i in active_items)
    snap = context.pricing_snapshot
    if snap.subtotal_paisas != expected_subtotal_all:
        errors.append(
            f"pricing_snapshot.subtotal_paisas mismatch "
            f"(expected {expected_subtotal_all}, got {snap.subtotal_paisas})"
        )

    expected_total = (
        snap.subtotal_paisas
        - snap.item_discounts_paisas
        - snap.order_discount_paisas
        + snap.delivery_charges_paisas
    )
    if snap.total_paisas != expected_total:
        errors.append(
            f"pricing_snapshot.total_paisas mismatch "
            f"(expected {expected_total}, got {snap.total_paisas})"
        )

    if errors:
        logger.warning("context.validation_failed", error_count=len(errors))

    return errors


# ═══════════════════════════════════════════════════════════════════
# AI SUMMARY (for long orders)
# ═══════════════════════════════════════════════════════════════════


async def generate_ai_summary(
    context: OrderContext,
    ai_provider: object,
) -> OrderContext:
    """Summarise long orders to save tokens on subsequent AI calls.

    Only generates when item count exceeds
    ``AI_CONTEXT_SUMMARY_ITEM_THRESHOLD``.

    Args:
        context: Current order context.
        ai_provider: AIProvider instance for text generation.

    Returns:
        Updated context with ``ai_context_summary`` set.
    """
    active_items = [i for i in context.items if not i.cancelled]
    if len(active_items) < AI_CONTEXT_SUMMARY_ITEM_THRESHOLD:
        return context

    items_text = "\n".join(
        f"- {i.medicine_name_display} × {i.quantity_requested} {i.unit}"
        for i in active_items
    )
    prompt = (
        "Summarise this order in 2 sentences for context injection. "
        "Include total item count and approximate total:\n\n"
        f"{items_text}\n\n"
        f"Total: {context.pricing_snapshot.total_paisas / 100:.0f} PKR"
    )

    try:
        response = await ai_provider.generate_text(  # type: ignore[union-attr]
            system_prompt="You are a concise order summariser.",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )
        context.ai_context_summary = response.content
        context.last_modified_at = datetime.now().astimezone()
        logger.info(
            "context.ai_summary_generated",
            items_count=len(active_items),
        )
    except Exception as exc:
        logger.warning("context.ai_summary_failed", error=str(exc))

    return context


# ═══════════════════════════════════════════════════════════════════
# CONVERSION / DISPLAY
# ═══════════════════════════════════════════════════════════════════


def to_order_create_payload(context: OrderContext) -> dict:
    """Convert the order context to a dict ready for orders + order_items tables.

    Args:
        context: Finalised order context.

    Returns:
        Dict with 'order' and 'items' keys for database insertion.
    """
    active_items = [i for i in context.items if not i.cancelled]
    snap = context.pricing_snapshot

    order_payload = {
        "session_order_id": str(context.session_order_id),
        "subtotal_paisas": snap.subtotal_paisas,
        "discount_paisas": snap.item_discounts_paisas + snap.order_discount_paisas,
        "delivery_charges_paisas": snap.delivery_charges_paisas,
        "total_paisas": snap.total_paisas,
        "delivery_address": context.delivery.address,
        "delivery_zone_id": (
            str(context.delivery.zone_id)
            if context.delivery.zone_id
            else None
        ),
        "customer_notes": context.customer_notes,
        "initiated_at": context.initiated_at.isoformat(),
        "total_messages_in_order": context.total_messages_in_order,
    }

    items_payload = []
    for item in active_items:
        items_payload.append({
            "catalog_id": str(item.catalog_id) if item.catalog_id else None,
            "medicine_name_raw": item.medicine_name_raw,
            "medicine_name_matched": item.medicine_name_matched,
            "medicine_name_display": item.medicine_name_display,
            "generic_name": item.generic_name,
            "brand_name": item.brand_name,
            "strength": item.strength,
            "form": item.form,
            "unit": item.unit,
            "quantity": item.quantity_requested,
            "price_per_unit_paisas": item.price_per_unit_paisas,
            "line_subtotal_paisas": item.line_subtotal_paisas,
            "discount_applied_paisas": item.discount_applied_paisas,
            "bonus_units": item.bonus_units,
            "line_total_paisas": item.line_total_paisas,
            "is_out_of_stock": item.is_out_of_stock,
            "is_unlisted": item.is_unlisted,
            "input_method": item.input_method.value,
            "voice_transcription": item.voice_transcription,
            "fuzzy_match_score": item.fuzzy_match_score,
        })

    return {"order": order_payload, "items": items_payload}


def context_to_display_string(
    context: OrderContext,
    language: str = "roman_urdu",
) -> str:
    """Render a human-readable order bill in the customer's language.

    Formats the order summary following the UX spec:
    numbered items, subtotal, discount, delivery, total.

    Args:
        context: Current order context.
        language: Language code ('roman_urdu', 'english', 'urdu').

    Returns:
        Formatted bill string.
    """
    active_items = [i for i in context.items if not i.cancelled]
    snap = context.pricing_snapshot

    if not active_items:
        if language == "english":
            return "Your order is empty."
        return "Aapka order khaali hai."

    lines: list[str] = []
    # Header
    if language == "english":
        lines.append("\U0001f4e6 Your Order:\n")
    else:
        lines.append("\U0001f4e6 Aapka Order:\n")

    # Items
    for idx, item in enumerate(active_items, 1):
        price_pkr = item.line_total_paisas / 100
        display = item.medicine_name_display or item.medicine_name_matched
        line = (
            f"{idx}. {display}"
            f" × {item.quantity_requested} {item.unit}"
            f"  —  PKR {price_pkr:,.0f}"
        )
        if item.is_out_of_stock:
            line += " ⚠️ OOS"
        lines.append(line)

    # Separator
    lines.append("\n─────────────────────────")

    # Totals
    subtotal_pkr = snap.subtotal_paisas / 100
    total_discount = snap.item_discounts_paisas + snap.order_discount_paisas
    discount_pkr = total_discount / 100
    delivery_pkr = snap.delivery_charges_paisas / 100
    total_pkr = snap.total_paisas / 100

    if language == "english":
        lines.append(f"Subtotal:   PKR {subtotal_pkr:,.0f}")
        if total_discount > 0:
            lines.append(f"Discount:   PKR {discount_pkr:,.0f}")
        if snap.delivery_charges_paisas > 0:
            lines.append(f"Delivery:   PKR {delivery_pkr:,.0f}")
        lines.append(f"─────────────────────────")
        lines.append(f"Total:      PKR {total_pkr:,.0f}")
    else:
        lines.append(f"Sub-total:  PKR {subtotal_pkr:,.0f}")
        if total_discount > 0:
            lines.append(f"Discount:   PKR {discount_pkr:,.0f}")
        if snap.delivery_charges_paisas > 0:
            lines.append(f"Delivery:   PKR {delivery_pkr:,.0f}")
        lines.append(f"─────────────────────────")
        lines.append(f"Total:      PKR {total_pkr:,.0f}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# INTERNAL: PRICING RECALCULATION
# ═══════════════════════════════════════════════════════════════════


def _recalculate_pricing_snapshot(context: OrderContext) -> None:
    """Recalculate the pricing snapshot from all active items.

    Must be called after every item add, remove, quantity change,
    or discount application.  Mutates ``context.pricing_snapshot``
    in place.

    Args:
        context: Order context to recalculate.
    """
    active_items = [i for i in context.items if not i.cancelled]

    subtotal = sum(i.line_total_paisas for i in active_items)
    item_discounts = sum(i.discount_applied_paisas for i in active_items)

    # Preserve existing order-level discount and delivery charges
    order_discount = context.pricing_snapshot.order_discount_paisas
    delivery = context.pricing_snapshot.delivery_charges_paisas
    auto_discounts = context.pricing_snapshot.auto_applied_discounts

    total = subtotal - order_discount + delivery

    context.pricing_snapshot = PricingSnapshot(
        subtotal_paisas=subtotal,
        item_discounts_paisas=item_discounts,
        order_discount_paisas=order_discount,
        auto_applied_discounts=auto_discounts,
        delivery_charges_paisas=delivery,
        total_paisas=total,
        calculated_at=datetime.now().astimezone(),
    )
    context.last_modified_at = datetime.now().astimezone()
