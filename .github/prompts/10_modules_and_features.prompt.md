# TELETRAAN Modules — Key Specifications and Changes

## M05 — AI and NLU Engine (Multi-Provider)
- All AI calls go through `AIProvider` factory — no provider-specific code in business logic
- Track `ai_provider` field in all `analytics_events` inserts
- Implement fallback chain per `08_ai_provider_abstraction.prompt.md`
- Support `ACTIVE_STT_PROVIDER` independently from `ACTIVE_AI_PROVIDER`
- Log which provider handled each request + its cost estimate
- Add `health_check()` calls for AI provider in scheduler health job

## M06 — Voice Pipeline (Multi-STT)
- Routes to `ACTIVE_STT_PROVIDER` — never hardcoded to Gemini
- If `gemini`: send audio bytes directly to Gemini native audio input
- If `whisper`: send to OpenAI Whisper endpoint (`openai.audio.transcriptions`)
- Both paths produce `AITranscriptionResponse` with identical fields
- Audio conversion (pydub/ffmpeg `.ogg` → `.wav`) happens before any STT call
- STT provider health checked separately from text AI health

## M23 — Payment Layer (Multi-Gateway)
- All gateway logic in `app/payments/gateways/` subdirectory
- Factory pattern: `ACTIVE_PAYMENT_GATEWAY` env selects default
- Per-distributor `preferred_payment_gateway` override supported
- Implement SafePay: hosted checkout URL generation + HMAC webhook verification
- Implement NayaPay: merchant payment initiation + QR code URL + webhook
- Implement bank_transfer: instructions bot flow + screenshot + manual confirm
- Gateway selection offered to payer when multiple gateways configured
- All gateway events tracked in `analytics_events` with `payment_gateway` field
- Gateway health checks in scheduler health job
- Admin commands: "list gateways", "check gateway [name]" via admin API
- `docs/payment_gateways.md` — full integration guide for each gateway

## M35 — Order Context Manager (`app/orders/context_manager.py`)
All 16 functions must be implemented (no stubs):

| Function | Purpose |
|---|---|
| `create_empty_context()` | Initialize blank context with new `session_order_id` |
| `add_item_to_context(context, item_data)` | Add item, recalculate `pricing_snapshot` |
| `remove_item_from_context(context, line_id)` | Mark cancelled (never delete), recalculate |
| `update_item_quantity(context, line_id, new_qty)` | Recalculate line and pricing |
| `apply_discount_to_item(context, line_id, discount_data)` | Update item and pricing |
| `apply_order_level_discount(context, discount_data)` | Apply to order_level_discount_request |
| `add_voice_context(context, transcription, duration, confidence, confirmed)` | Populate voice_order_context |
| `set_delivery(context, address, zone_id, charges)` | Update delivery + pricing |
| `mark_bill_shown(context)` | Increment `bill_shown_count`, set `bill_shown_at` |
| `mark_confirmed(context)` | Set `confirmation_requested_at` |
| `cancel_order(context, reason)` | Set `order_cancelled = True` + reason |
| `get_context_from_session(session)` | Deserialize `pending_order_draft` to `OrderContext` |
| `save_context_to_session(context, session_repo, session_id)` | Serialize and persist to DB |
| `validate_context(context)` | Check required fields, positive quantities, consistent prices |
| `generate_ai_summary(context, ai_provider)` | Summarize long orders to save tokens |
| `to_order_create_payload(context)` | Dict ready to insert into orders + order_items tables |
| `context_to_display_string(context, language)` | Human-readable bill in customer's language |

**Pydantic model:** `app/db/models/order_context.py` — exact model of order context schema.
