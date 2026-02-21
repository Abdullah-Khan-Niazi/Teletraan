---
applyTo: "app/core/**,app/**/*orchestrat*.py,app/**/*pipeline*.py,app/**/*handler*.py"
---

# SKILL 17 — ORCHESTRATION
## Source: `docs/skills/SKILL_orchestration.md`

---

## PURPOSE

The orchestrator is the brain of TELETRAAN. Every incoming message passes through it.
Every outbound response originates from it. It coordinates WhatsApp, AI, MCP tools,
payment gateways, order context, and the FSM state machine.

---

## PROCESSING PIPELINE (in strict order)

```
[1]  Signature Verification (HMAC-SHA256) — reject if invalid
[2]  Message Deduplication (TTLCache on message.id) — skip if seen
[3]  Distributor Resolution (phone_number_id → distributor)
[4]  Subscription Check (is distributor active?) — reject if suspended
[5]  Customer Resolution / Onboarding (create if new)
[6]  Session Load (or create idle session)
[7]  OrderContext Load (from session.pending_order_context)
[8]  Message Type Router → TextOrchestrator / VoiceOrchestrator / InteractiveOrchestrator
[9]  Channel Router → ChannelAOrchestrator / ChannelBOrchestrator
[10] Intent Classification (AI)
[11] Entity Extraction (AI, if needed)
[12] FSM State Transition Check
[13] MCP Tool Execution (catalog lookup, order write, etc.)
[14] Response Generation (AI or template)
[15] OrderContext Save — BEFORE sending response
[16] WhatsApp Response Send
[17] Read Receipt
[18] Analytics Event Log
```

**Step 15 (context save) ALWAYS happens before step 16 (send response).**
If we send response but fail to save context, next message has stale state.

---

## FSM STATE MACHINE

Session states (app/core/constants.py):
```
idle → greeting_sent → collecting_order → confirming_order → payment_pending
     → order_complete → timed_out → escalated
```

Rules:
- Invalid state transition → `StateTransitionError`, log error, send recovery message
- `timed_out` sessions reset to `idle` on next message (with context preserved)
- `escalated` sessions pause bot — human operator takes over

---

## DEDUPLICATION

```python
from cachetools import TTLCache

# Keyed by message_id, TTL = 24 hours, max = 10,000 entries
_seen_messages: TTLCache = TTLCache(maxsize=10_000, ttl=86400)

def is_duplicate_message(message_id: str) -> bool:
    if message_id in _seen_messages:
        logger.info("message.duplicate_skipped", message_id=message_id)
        return True
    _seen_messages[message_id] = True
    return False
```

---

## VOICE MESSAGE PIPELINE

```python
# VoiceOrchestrator
async def handle_voice(message: WhatsAppMessage, context: RequestContext) -> str:
    # 1. Download audio bytes from WhatsApp media API
    audio_bytes, mime_type = await whatsapp_client.download_media(message.audio.id)
    
    # 2. Transcribe with active STT provider
    transcription = await stt_provider.transcribe_audio(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        language_hint="ur",
    )
    
    # 3. Store raw transcription in context for audit trail
    # 4. Pass transcribed text to TextOrchestrator
    return await text_orchestrator.handle(transcription.text, context)
```

---

## RATE LIMITING

Before processing any message:
```python
if await rate_limiter.is_rate_limited(customer_phone):
    await whatsapp_client.send_text(
        customer_phone,
        "Thoda wait karein — aap bohat fast messages bhej rahe hain."
    )
    return
```

---

## SUBSCRIPTION CHECK

```python
async def check_distributor_subscription(distributor: Distributor) -> bool:
    if distributor.subscription_status == SubscriptionStatus.ACTIVE:
        return True
    if distributor.subscription_status == SubscriptionStatus.SUSPENDED:
        # Bot completely silent for suspended distributors
        logger.warning("message.rejected_suspended_distributor", did=distributor.id)
        return False
    # TRIAL or GRACE_PERIOD — allow but log
    logger.warning("distributor.subscription_at_risk", status=distributor.subscription_status)
    return True
```

---

## ORCHESTRATOR FILE STRUCTURE

```
app/core/
├── orchestrator.py          # Main entry point, pipeline steps 1-6
├── text_orchestrator.py     # Steps 8-18 for text messages
├── voice_orchestrator.py    # Steps 8-18 for voice messages
├── interactive_orchestrator.py  # Steps 8-18 for button/list replies
└── channel_router.py        # Step 9: route to Channel A or B
```
