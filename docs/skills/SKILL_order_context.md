# ORDER CONTEXT SKILL
## SKILL: order-context | Version: 1.0 | Priority: CRITICAL

---

## PURPOSE

This skill defines how TELETRAAN stores, manages, and recovers in-progress
order state. The order context is the single source of truth for everything
that has happened in an order conversation — from the first item mentioned
to the final confirmation.

If the server restarts mid-order, the customer must be able to continue
seamlessly. This is achieved by persisting all order state in
`sessions.pending_order_draft` (JSONB) after every change.

---

## THE CORE PROBLEM THIS SOLVES

Without proper context persistence:
- Server restart loses the entire in-progress order
- Customer must start over → bad experience, lost order
- AI loses context → coherent conversation breaks
- Pricing becomes inconsistent → customer shown wrong amounts
- Voice transcriptions lost → untraceable audit issues

With proper context persistence:
- Every piece of information captured at the moment it's received
- Process restart = seamless continuation from exact state
- Full audit trail of what customer said vs what was matched
- Consistent pricing from first item to confirmation

---

## CONTEXT MODULE: app/orders/context_manager.py

This is a pure service module — no direct DB access.
It operates on `OrderContext` Pydantic objects.
Persistence (reading from / writing to DB) is handled by the caller
using `session_repo`.

### Functions to implement — all of them:

#### Creation and retrieval
```
create_empty_context(session_order_id: str | None = None) → OrderContext
    Create a blank OrderContext with generated session_order_id.
    Set initiated_at = now(). All lists empty. All flags False.

get_context_from_session(session: Session) → OrderContext
    Deserialize session.pending_order_draft to OrderContext model.
    If pending_order_draft is empty dict: return create_empty_context().
    Validate with OrderContext.model_validate(). Raise if invalid.

save_context_to_session(
    context: OrderContext,
    session_id: str,
    session_repo: SessionRepository
) → None
    Update context.last_modified_at = now().
    Serialize with context.model_dump(mode="json").
    Call session_repo.update_order_draft(session_id, draft_dict).
    This MUST be called after every context mutation.
```

#### Item management
```
add_item_to_context(
    context: OrderContext,
    catalog_id: str | None,
    medicine_name_raw: str,
    medicine_name_matched: str,
    medicine_name_display: str,
    quantity: int,
    price_per_unit_paisas: int,
    unit: str,
    is_out_of_stock: bool,
    stock_available: int | None,
    is_unlisted: bool,
    input_method: str,  # "text", "voice", "button_selection"
    fuzzy_match_score: float | None,
    fuzzy_alternatives: list[str] | None,
    voice_transcription: str | None,
    generic_name: str | None,
    brand_name: str | None,
    strength: str | None,
    form: str | None,
) → tuple[OrderContext, str]:  # (updated_context, line_id)
    Generate line_id = str(uuid4()).
    Compute line_subtotal_paisas = quantity × price_per_unit_paisas.
    Set line_total_paisas = line_subtotal_paisas (discount = 0 initially).
    Append to context.items.
    Call _recalculate_pricing_snapshot(context).
    Return (context, line_id).

remove_item_from_context(
    context: OrderContext,
    line_id: str,
) → OrderContext
    Find item by line_id. If not found: raise ValueError.
    Set item.cancelled = True (never delete — audit trail).
    Call _recalculate_pricing_snapshot(context).
    Return updated context.

update_item_quantity(
    context: OrderContext,
    line_id: str,
    new_quantity: int,
) → OrderContext
    Validate new_quantity > 0.
    Find item, update quantity_requested and recalculate line amounts.
    Call _recalculate_pricing_snapshot(context).
    Return updated context.

confirm_item_match(
    context: OrderContext,
    line_id: str,
) → OrderContext
    Set item.is_confirmed_by_customer = True.
    Return updated context.
```

#### Discount management
```
apply_discount_to_item(
    context: OrderContext,
    line_id: str,
    discount_paisas: int,
    bonus_units: int,
    request_type: str,
    requested_value: str,
    status: str,
) → OrderContext
    Update item.discount_applied_paisas, item.bonus_units.
    Recalculate item.line_total_paisas.
    Set item.discount_request with status.
    Call _recalculate_pricing_snapshot(context).
    Return updated context.

apply_order_level_discount(
    context: OrderContext,
    request_text: str,
    discount_paisas: int,
    status: str,
) → OrderContext
    Set context.order_level_discount_request.
    Update context.pricing_snapshot.order_discount_paisas.
    Recalculate total.
    Return updated context.

add_discount_request(
    context: OrderContext,
    line_id: str | None,  # None = order-level
    request_type: str,
    requested_value: str,
) → OrderContext
    Set status = "pending".
    If line_id: update item.discount_request.
    Else: set order_level_discount_request.
    Return updated context.
```

#### Pricing (internal — called by all item mutations)
```
_recalculate_pricing_snapshot(context: OrderContext) → OrderContext
    Sum active (non-cancelled) items:
        subtotal = sum(item.line_total_paisas for item if not cancelled)
    item_discounts = sum(item.discount_applied_paisas for active items)
    total = subtotal + delivery_charges - order_level_discount
    Update context.pricing_snapshot:
        subtotal_paisas, item_discounts_paisas,
        order_discount_paisas, delivery_charges_paisas,
        total_paisas, calculated_at=now()
    Return context.
```

#### Delivery
```
set_delivery(
    context: OrderContext,
    address: str,
    zone_id: str | None,
    zone_name: str | None,
    delivery_hours: int | None,
    delivery_day_display: str | None,
    delivery_charges_paisas: int,
    confirmed: bool = False,
) → OrderContext
    Update context.delivery.*
    Call _recalculate_pricing_snapshot (delivery charges affect total).
    Return updated context.
```

#### Voice context
```
add_voice_order_context(
    context: OrderContext,
    transcription: str,
    items_extracted_count: int,
    duration_seconds: float,
    confidence: str,
) → OrderContext
    Set context.voice_order_context if not already set.
    transcription_confirmed_by_customer starts as False.
    Return context.

confirm_voice_transcription(context: OrderContext) → OrderContext
    Set context.voice_order_context.transcription_confirmed_by_customer = True.
    Return context.
```

#### Bill display
```
mark_bill_shown(context: OrderContext) → OrderContext
    Increment context.bill_shown_count.
    Set context.bill_shown_at = now().
    If bill_shown_count >= 3: add note to customer_notes about repeated viewing.
    Return context.

mark_confirmation_requested(context: OrderContext) → OrderContext
    Set context.confirmation_requested_at = now().
    Return context.
```

#### Cancellation
```
cancel_order(context: OrderContext, reason: str) → OrderContext
    Set context.order_cancelled = True.
    Set context.cancellation_reason = reason.
    Return context.
```

#### Validation
```
validate_context(context: OrderContext) → list[str]:  # List of validation errors
    Check: at least one non-cancelled item.
    Check: all quantities > 0.
    Check: all prices > 0.
    Check: pricing_snapshot total matches sum of active item totals + delivery - discount.
    Check: all items with is_confirmed_by_customer = False (any unconfirmed matches).
    Return list of error strings. Empty list = valid.
```

#### AI context optimization
```
generate_ai_summary(
    context: OrderContext,
    ai_provider: AIProvider,
) → OrderContext
    Only call this when len(context.items) >= 8.
    Prompt AI: "Summarize this medicine order in 2 sentences for context:
               [list of items with quantities]. Include total value."
    Store result in context.ai_context_summary.
    Return context.
```

#### Export
```
to_order_create_payload(context: OrderContext) → dict
    Return dict ready to INSERT into orders and order_items tables.
    Includes: all active items as order_items list, pricing totals, delivery info.
    Includes: order_context_snapshot (full context as dict) for audit.

context_to_display_string(
    context: OrderContext,
    language: str,
) → str
    Generate human-readable bill summary in specified language.
    Format: item list with quantities, unit prices, discounts, subtotal, delivery, total.
    Use templates from notifications/templates/ for language-specific formatting.
    Return plain text (no markdown — this goes to WhatsApp).
```

---

## PYDANTIC MODEL: app/db/models/order_context.py

The `OrderContext` Pydantic model must exactly match the ORDER CONTEXT SCHEMA
in the build prompt. Every field specified there must be a typed Pydantic field.

Key model design rules:
- All timestamps as `datetime` with timezone
- All paisas amounts as `int` (not float, not Decimal)
- All optional fields explicitly `Optional[type] = None`
- `items` field as `list[OrderItemContext]` — a separate sub-model
- `pricing_snapshot` as `PricingSnapshot` sub-model
- `delivery` as `DeliveryContext` sub-model
- `voice_order_context` as `VoiceOrderContext` sub-model
- `ambiguity_resolution` as `AmbiguityResolution` sub-model
- Use `model_config = ConfigDict(use_enum_values=True)`
- Add `model_validator` to ensure pricing consistency on load

---

## HOW THE ORDER FLOW USES CONTEXT

```
Customer sends message
        ↓
order_flow.py handler called
        ↓
context = context_manager.get_context_from_session(session)
        ↓
[process customer input — add items, update quantities, etc.]
        ↓
context = context_manager.add_item_to_context(context, ...)
        ↓
await context_manager.save_context_to_session(context, session.id, session_repo)
        ↓
[generate response to customer]
        ↓
[if order confirmed:]
    payload = context_manager.to_order_create_payload(context)
    order = await order_service.create_order(payload)
    context = context_manager.cancel_order(context, "confirmed")
    await context_manager.save_context_to_session(context, ...)  # Clear draft
```

---

## CRITICAL SAVE POINTS

Save context to DB after EVERY one of these events:
- Item added
- Item removed
- Item quantity changed
- Discount applied or requested
- Voice transcription received and confirmed
- Delivery set
- Bill shown
- Confirmation requested
- Order cancelled
- AI summary generated

If save fails: raise exception. Do NOT continue. The customer can retry.
An unsaved state is a corrupted state.

---

## TESTING ORDER CONTEXT

Test file: `tests/unit/test_order_context.py`

Must test:
1. `create_empty_context()` produces valid empty context
2. `add_item_to_context()` correctly calculates line totals
3. `remove_item_from_context()` marks cancelled, recalculates total
4. `update_item_quantity()` recalculates correctly
5. `_recalculate_pricing_snapshot()` matches sum of active items
6. `validate_context()` catches inconsistencies
7. `to_order_create_payload()` produces correct DB-ready structure
8. Serialization/deserialization roundtrip: context → JSON → model → same context
9. Multi-item order with mixed discounts and out-of-stock items
10. Quick reorder context has source_order_id set
11. Voice context preserved after add_voice_order_context()
12. Order with 10 items: generate_ai_summary() is called, summary stored
