---
applyTo: "app/orders/**,app/**/context*/**,app/**/*context*.py,app/**/*order*.py"
---

# SKILL 10 — ORDER CONTEXT
## Source: `docs/skills/SKILL_order_context.md`

---

## PURPOSE

The order context is the single source of truth for an in-progress order conversation.
Persisted in `sessions.pending_order_draft` (JSONB) after EVERY mutation.
If the server restarts mid-order, the customer must be able to continue seamlessly.

---

## THE RULE

**Every context mutation must call `save_context_to_session()` before returning.**
Never mutate context in memory and skip persistence — the next request will see stale data.

---

## CONTEXT MODULE: app/orders/context_manager.py

Pure service module — no direct DB access. Operates on `OrderContext` Pydantic objects.
Persistence handled by the caller via `session_repo`.

### Required functions

```python
create_empty_context(session_order_id: str | None = None) -> OrderContext
    # Fresh blank context, initiated_at = now()

get_context_from_session(session: Session) -> OrderContext
    # Deserialize session.pending_order_draft → OrderContext
    # Empty dict → return create_empty_context()

save_context_to_session(
    context: OrderContext,
    session_id: str,
    session_repo: SessionRepository,
) -> None
    # Set last_modified_at = now(), serialize, call repo.update_order_draft()

add_item_to_context(context, catalog_id, name_raw, name_matched,
                    quantity, price_per_unit_paisas, ...) -> tuple[OrderContext, str]
    # Returns (updated_context, line_id: str = uuid4())
    # Calls _recalculate_pricing_snapshot()

remove_item_from_context(context, line_id) -> OrderContext
    # Marks item cancelled=True, calls _recalculate_pricing_snapshot()

update_item_quantity(context, line_id, new_quantity) -> OrderContext
    # Updates quantity and recalculates pricing

apply_discount_to_context(context, discount_rule) -> OrderContext
    # Applies discount rule, recalculates pricing

clear_context(context) -> OrderContext
    # Reset to empty, keep session_order_id

finalize_context(context) -> OrderContext
    # Set is_finalized=True, calculate final totals
```

---

## OrderContext SCHEMA

```python
class OrderContext(BaseModel):
    session_order_id: str               # UUID, stable throughout order conversation
    initiated_at: datetime
    last_modified_at: datetime
    items: list[OrderItemDraft]         # All items (includes cancelled)
    delivery_address: str | None
    delivery_zone: str | None
    special_notes: str | None
    pricing_snapshot: PricingSnapshot   # ALWAYS recomputed after every mutation
    is_finalized: bool = False
    confirmation_attempts: int = 0
    customer_confirmed: bool = False

class OrderItemDraft(BaseModel):
    line_id: str                        # UUID
    catalog_id: str | None
    medicine_name_raw: str              # Exactly what customer said
    medicine_name_matched: str          # What was matched in catalog
    medicine_name_display: str          # Clean display name
    quantity: int
    unit: str
    price_per_unit_paisas: int
    line_subtotal_paisas: int           # quantity × price_per_unit_paisas
    line_total_paisas: int              # After item-level discounts
    is_cancelled: bool = False
    is_out_of_stock: bool = False
    is_unlisted: bool = False
    input_method: str                   # "text", "voice", "button_selection"
    fuzzy_match_score: float | None
    voice_transcription: str | None     # Original transcription if voice

class PricingSnapshot(BaseModel):
    subtotal_paisas: int                # Sum of active line totals
    discount_paisas: int
    delivery_charge_paisas: int
    total_paisas: int
    bonus_units: list[BonusUnit]
    applied_discount_rules: list[str]   # Rule IDs
```

---

## PRICING SNAPSHOT RULE

`_recalculate_pricing_snapshot()` MUST be called:
- After any item add, remove, or quantity change
- After any discount applied
- After delivery address set (affects delivery charge)

Never allow `pricing_snapshot` to be stale. It's shown directly to the customer.

---

## VOICE TRANSCRIPTION STORAGE

When item added via voice:
- Store raw transcription in `OrderItemDraft.voice_transcription`
- Store the matched name separately in `medicine_name_matched`
- This creates full audit trail: what customer said → what was matched
