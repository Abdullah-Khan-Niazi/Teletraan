# ORCHESTRATION SKILL
## SKILL: orchestration | Version: 1.0 | Priority: CRITICAL

---

## PURPOSE

This skill defines how the TELETRAAN orchestrator coordinates every component —
WhatsApp webhooks, AI providers, MCP tools, payment gateways, order context,
FSM state machine, and outbound messaging — into a coherent request-response
pipeline.

The orchestrator is the brain of TELETRAAN. Every incoming message passes
through it. Every outbound response originates from it.

---

## ARCHITECTURE

```
WhatsApp Webhook (POST /webhook/whatsapp/{distributor_id})
                │
                ▼
    [1] Signature Verification (HMAC-SHA256)
                │
                ▼
    [2] Message Deduplication (TTLCache on message.id)
                │
                ▼
    [3] Distributor Resolution (phone_number_id → distributor)
                │
                ▼
    [4] Subscription Check (is distributor active?)
                │
                ▼
    [5] Customer Resolution / Onboarding
                │
                ▼
    [6] Session Load (or create)
                │
                ▼
    [7] OrderContext Load (from session.pending_order_context)
                │
                ▼
    [8] Message Type Router
         ├── text       → TextOrchestrator
         ├── audio      → VoiceOrchestrator → (transcribe) → TextOrchestrator
         ├── interactive → InteractiveOrchestrator
         ├── image      → ImageOrchestrator
         └── unsupported → send "type not supported" message
                │
                ▼
    [9] Channel Router
         ├── Channel A (customer_order) → ChannelAOrchestrator
         └── Channel B (sales_rep)      → ChannelBOrchestrator
                │
                ▼
   [10] Intent Classification (AI)
                │
                ▼
   [11] Entity Extraction (AI, if needed)
                │
                ▼
   [12] FSM State Transition Check
                │
                ▼
   [13] MCP Tool Execution (catalog lookup, order write, etc.)
                │
                ▼
   [14] Response Generation (AI or template)
                │
                ▼
   [15] OrderContext Save (persist before respond)
                │
                ▼
   [16] WhatsApp Response Send
                │
                ▼
   [17] Read Receipt
                │
                ▼
   [18] Session Update
```

---

## DIRECTORY STRUCTURE

```
app/
  core/
    orchestrator.py           ← Master orchestrator (entry point from handler)
    channel_a_orchestrator.py ← Customer order flow coordination
    channel_b_orchestrator.py ← Sales rep flow coordination
    voice_orchestrator.py     ← Voice note preprocessing
    interactive_orchestrator.py ← Button/list reply handling
    session_manager.py        ← Session load/save/create
    customer_resolver.py      ← Phone → customer lookup/create
    distributor_resolver.py   ← phone_number_id → distributor lookup
    fsm.py                    ← Finite state machine (state transitions)
    request_context.py        ← RequestContext dataclass (threading request state)
```

---

## REQUEST CONTEXT

Every message handler receives a single RequestContext object.
No global state. No thread-locals. No implicit dependencies.

```python
# app/core/request_context.py

from dataclasses import dataclass, field
from typing import Optional
from app.models import Distributor, Customer, Session
from app.orders.context_store import OrderContext
from app.ai.base import AIProvider
from app.payments.base import PaymentGateway


@dataclass
class RequestContext:
    """
    Immutable context for a single incoming WhatsApp message.

    Constructed once at the start of message processing.
    Passed through the entire orchestration pipeline.
    Never modified after initial construction — use output objects instead.
    """
    # Request identifiers
    request_id: str                       # UUID for log correlation
    message_id: str                       # WhatsApp message ID (for dedup)
    received_at_utc: datetime

    # WhatsApp message
    from_phone: str                       # sender's phone number
    to_phone_number_id: str              # receiving WhatsApp number ID
    message_type: str                    # text | audio | image | interactive | ...
    message_body: Optional[str]           # text content (or None)
    media_id: Optional[str]              # for audio/image
    interactive_payload: Optional[dict]  # for button/list replies

    # Resolved entities
    distributor: Distributor
    customer: Customer
    session: Session
    order_context: Optional[OrderContext]

    # Active providers (resolved from distributor config)
    ai_provider: AIProvider
    payment_gateway: PaymentGateway

    # Channel
    channel: str                         # "A" (customer) | "B" (sales)
```

---

## MASTER ORCHESTRATOR

```python
# app/core/orchestrator.py

class TeletraanOrchestrator:
    """
    Entry point for all incoming WhatsApp messages.

    Coordinates all subsystems. Returns nothing — side effects are:
    1. WhatsApp response sent to customer
    2. Database state updated
    3. All actions logged
    """

    async def handle(self, raw_webhook: dict, distributor_id: str) -> None:
        request_id = str(uuid4())

        try:
            # Steps 3-8: Build RequestContext
            ctx = await self._build_context(raw_webhook, distributor_id, request_id)
            if ctx is None:
                return  # Dedup hit or unsupported message type — already handled

            # Step 9: Route to channel
            if ctx.channel == "A":
                await ChannelAOrchestrator(ctx).handle()
            elif ctx.channel == "B":
                await ChannelBOrchestrator(ctx).handle()
            else:
                logger.warning("Unknown channel", channel=ctx.channel, request_id=request_id)

        except Exception as exc:
            logger.exception("Orchestrator unhandled error", request_id=request_id, error=str(exc))
            await self._send_fallback_error_response(raw_webhook, distributor_id)

    async def _build_context(self, raw_webhook: dict, distributor_id: str, request_id: str) -> RequestContext | None:
        # Parse WhatsApp webhook payload
        msg = parse_whatsapp_message(raw_webhook)
        if not msg:
            return None

        # Deduplication
        if message_cache.get(msg.message_id):
            logger.debug("Duplicate message skipped", message_id=msg.message_id)
            return None
        message_cache.set(msg.message_id, True)

        # Distributor
        distributor = await distributor_repo.get_by_id(distributor_id)
        if not distributor or not distributor.is_active:
            await whatsapp_client.send_text(
                msg.from_phone, SUSPENDED_MESSAGE, distributor.whatsapp_phone_number_id
            )
            return None

        # Subscription check
        if distributor.subscription_expires_at < datetime.utcnow():
            await whatsapp_client.send_text(msg.from_phone, SUBSCRIPTION_EXPIRED_MESSAGE, ...)
            return None

        # Customer
        customer = await customer_resolver.resolve_or_create(msg.from_phone, distributor)

        # Session
        session = await session_manager.load_or_create(customer.id, distributor.id)

        # Order context
        order_context = None
        if session.pending_order_context:
            order_context = OrderContext.from_json(session.pending_order_context)

        # Providers
        ai_provider = ai_factory.get_provider(distributor.preferred_ai_provider)
        payment_gateway = payment_factory.get_gateway(distributor.preferred_payment_gateway)

        # Channel detection
        channel = "B" if msg.from_phone in distributor.sales_rep_phones else "A"

        return RequestContext(
            request_id=request_id,
            message_id=msg.message_id,
            received_at_utc=datetime.utcnow(),
            from_phone=msg.from_phone,
            to_phone_number_id=msg.to_phone_number_id,
            message_type=msg.message_type,
            message_body=msg.body,
            media_id=msg.media_id,
            interactive_payload=msg.interactive_payload,
            distributor=distributor,
            customer=customer,
            session=session,
            order_context=order_context,
            ai_provider=ai_provider,
            payment_gateway=payment_gateway,
            channel=channel,
        )
```

---

## CHANNEL A ORCHESTRATOR

```python
# app/core/channel_a_orchestrator.py

class ChannelAOrchestrator:
    """
    Orchestrates the customer order conversation (Channel A).

    Pipeline:
    1. Preprocess message (voice transcription if needed)
    2. Classify intent
    3. Extract entities (if add_item intent)
    4. FSM transition
    5. Execute MCP tool
    6. Generate response
    7. Save context (BEFORE sending response)
    8. Send response
    """

    def __init__(self, ctx: RequestContext):
        self.ctx = ctx
        self.mcp = MCPExecutor(ctx.distributor.id, ctx.customer.phone, db)
        self.whatsapp = WhatsAppClient()

    async def handle(self) -> None:
        ctx = self.ctx

        # Step 1: Preprocessing
        message_text = await self._preprocess_message(ctx)
        if message_text is None:
            return  # Low-confidence voice handled with clarification message

        # Step 2: Intent classification
        intent_result = await ctx.ai_provider.classify_intent(
            message=message_text,
            history=ctx.session.conversation_history_last_5(),
            order_state=ctx.order_context.order_state if ctx.order_context else "none",
            channel="A",
        )

        # Step 3: Interrupt commands (override any state)
        if await self._handle_interrupt(intent_result.intent, ctx):
            return

        # Step 4: Route by intent
        handler = self._get_intent_handler(intent_result.intent)
        if not handler:
            await self._send_clarification(ctx, intent_result)
            return

        result: OrchestratorResult = await handler(ctx, message_text, intent_result)

        # Step 5: Save context BEFORE sending response
        if result.updated_order_context:
            await order_context_store.save(
                session_id=ctx.session.id,
                context=result.updated_order_context,
            )

        # Step 6: Send response
        await self._send_response(ctx, result)

        # Step 7: Session update
        await session_manager.record_message(ctx.session.id, message_text, result.response_text)

    async def _preprocess_message(self, ctx: RequestContext) -> str | None:
        if ctx.message_type == "audio":
            return await VoiceOrchestrator(ctx).transcribe_and_confirm()
        elif ctx.message_type == "interactive":
            return InteractiveOrchestrator(ctx).extract_payload()
        elif ctx.message_type == "text":
            return ctx.message_body
        else:
            await self.whatsapp.send_text(
                ctx.from_phone,
                "Sirf text ya voice note bhejein.",
                ctx.to_phone_number_id,
            )
            return None

    def _get_intent_handler(self, intent: str):
        return {
            "add_item": self._handle_add_item,
            "remove_item": self._handle_remove_item,
            "modify_quantity": self._handle_modify_quantity,
            "confirm_order": self._handle_confirm_order,
            "cancel_order": self._handle_cancel_order,
            "view_bill": self._handle_view_bill,
            "request_discount": self._handle_discount_request,
            "check_stock": self._handle_stock_check,
            "ask_price": self._handle_price_inquiry,
            "reorder": self._handle_reorder,
            "greeting": self._handle_greeting,
            "unrelated": self._handle_unrelated,
        }.get(intent)

    async def _handle_interrupt(self, intent: str, ctx: RequestContext) -> bool:
        """Handle commands that override current FSM state."""
        if intent == "cancel_order" and ctx.order_context:
            await self.mcp.execute("cancel_order", {"reason": "customer_requested"})
            await self.whatsapp.send_text(ctx.from_phone, "Order cancel ho gaya. ✅", ctx.to_phone_number_id)
            return True
        return False
```

---

## FSM (FINITE STATE MACHINE)

```python
# app/core/fsm.py

from enum import Enum


class OrderState(str, Enum):
    IDLE = "idle"
    BUILDING = "building"
    AWAITING_ITEM_CONFIRMATION = "awaiting_item_confirmation"
    AWAITING_QUANTITY = "awaiting_quantity"
    AWAITING_FUZZY_SELECTION = "awaiting_fuzzy_selection"
    REVIEWING_BILL = "reviewing_bill"
    AWAITING_DISCOUNT_RESPONSE = "awaiting_discount_response"
    AWAITING_FINAL_CONFIRMATION = "awaiting_final_confirmation"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# Valid transitions: (from_state, intent) → to_state
TRANSITIONS: dict[tuple[OrderState, str], OrderState] = {
    (OrderState.IDLE, "add_item"):                          OrderState.AWAITING_ITEM_CONFIRMATION,
    (OrderState.IDLE, "greeting"):                          OrderState.IDLE,
    (OrderState.BUILDING, "add_item"):                      OrderState.AWAITING_ITEM_CONFIRMATION,
    (OrderState.BUILDING, "view_bill"):                     OrderState.REVIEWING_BILL,
    (OrderState.BUILDING, "confirm_order"):                 OrderState.AWAITING_FINAL_CONFIRMATION,
    (OrderState.AWAITING_ITEM_CONFIRMATION, "confirm_order"): OrderState.BUILDING,
    (OrderState.AWAITING_ITEM_CONFIRMATION, "cancel_order"):  OrderState.BUILDING,
    (OrderState.AWAITING_FUZZY_SELECTION, "confirm_order"):   OrderState.AWAITING_QUANTITY,
    (OrderState.REVIEWING_BILL, "confirm_order"):           OrderState.AWAITING_FINAL_CONFIRMATION,
    (OrderState.REVIEWING_BILL, "request_discount"):        OrderState.AWAITING_DISCOUNT_RESPONSE,
    (OrderState.AWAITING_FINAL_CONFIRMATION, "confirm_order"): OrderState.CONFIRMED,
    # Cancel from any state
    (OrderState.BUILDING, "cancel_order"):                  OrderState.CANCELLED,
    (OrderState.REVIEWING_BILL, "cancel_order"):            OrderState.CANCELLED,
    (OrderState.AWAITING_FINAL_CONFIRMATION, "cancel_order"): OrderState.CANCELLED,
}


def get_next_state(
    current: OrderState,
    intent: str,
) -> OrderState | None:
    """
    Returns the next valid state given current state and intent.
    Returns None if the transition is not allowed.
    """
    return TRANSITIONS.get((current, intent))


def is_valid_transition(current: OrderState, intent: str) -> bool:
    return (current, intent) in TRANSITIONS
```

---

## VOICE ORCHESTRATOR

```python
# app/core/voice_orchestrator.py

class VoiceOrchestrator:
    """
    Handles voice note messages.

    Pipeline:
    1. Download audio from WhatsApp
    2. Convert to WAV (pydub + ffmpeg)
    3. Transcribe (active STT provider)
    4. If confidence HIGH: return transcript as text
    5. If confidence LOW: send clarification message, return None
    6. Log to voice_transcript_log in OrderContext
    """

    CONFIDENCE_THRESHOLD = 0.75   # below this → ask for clarification

    async def transcribe_and_confirm(self) -> str | None:
        ctx = self.ctx

        # Download
        audio_bytes = await whatsapp_client.download_media(ctx.media_id)

        # Convert to WAV
        wav_bytes = await convert_ogg_to_wav(audio_bytes)

        # Transcribe
        transcript_result = await ctx.ai_provider.transcribe_audio(
            audio_bytes=wav_bytes,
            mime_type="audio/wav",
            language_hint="ur",
        )

        # Log to order context
        if ctx.order_context:
            ctx.order_context.voice_transcript_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "transcript": transcript_result.text,
                "confidence": transcript_result.confidence,
                "ai_provider": ctx.ai_provider.get_provider_name(),
                "customer_confirmed": None,
            })

        if transcript_result.confidence >= self.CONFIDENCE_THRESHOLD:
            return transcript_result.text

        # Low confidence — send clarification
        clarification_msg = voice_fallback_prompt.render(
            partial_transcript=transcript_result.text,
            confidence_score=transcript_result.confidence,
            customer_name=ctx.customer.name or "aap",
        )
        await whatsapp_client.send_text(ctx.from_phone, clarification_msg, ctx.to_phone_number_id)
        return None
```

---

## ORCHESTRATOR RESULT

```python
# app/core/orchestrator.py (continued)

@dataclass
class OrchestratorResult:
    """
    The output of any intent handler.

    Contains everything needed to:
    1. Persist state changes
    2. Send the response
    """
    response_text: Optional[str] = None           # plain text response
    response_interactive: Optional[dict] = None    # WhatsApp interactive message
    updated_order_context: Optional[OrderContext] = None
    updated_session_state: Optional[dict] = None
    log_entry: Optional[dict] = None               # extra data to log
    send_read_receipt: bool = True
```

---

## ORCHESTRATION INVARIANTS

These conditions must hold after every message is processed.
The build agent must verify these invariants in integration tests.

```
INVARIANT 1: Every message gets a response
  The customer must receive exactly one response per message.
  Zero responses: never acceptable.
  Two responses: only acceptable for two-step flows (e.g., confirm then bill).

INVARIANT 2: Context saved before response sent
  If updated_order_context is not None, it must be persisted to DB
  BEFORE the WhatsApp message is sent. Process restart must not lose data.

INVARIANT 3: Duplicate messages are idempotent
  Replaying the same message_id twice produces the same DB state.
  The second replay returns a response but does not duplicate DB writes.

INVARIANT 4: Invalid FSM transitions are rejected gracefully
  If a customer message triggers an invalid transition, the bot responds
  with a gentle redirect. It does not throw an exception or go silent.

INVARIANT 5: All errors produce a customer message
  Any exception in the orchestrator pipeline triggers the fallback error
  response. The customer is never left waiting silently.
```

---

## INTEGRATION TEST COVERAGE FOR ORCHESTRATOR

```python
# tests/core/test_orchestrator.py

async def test_full_order_flow(mock_ctx, mock_mcp, mock_whatsapp):
    """Simulate a complete order from greeting to confirmation."""
    ctx = mock_ctx(channel="A", message="10 strip paracetamol")
    await TeletraanOrchestrator().handle(ctx.raw_webhook, ctx.distributor.id)
    # Verify: item added to order context, bill calculated, response sent

async def test_duplicate_message_idempotent(mock_ctx):
    """Same message_id twice should not duplicate DB writes."""
    ctx = mock_ctx(channel="A", message="CONFIRM")
    await TeletraanOrchestrator().handle(ctx.raw_webhook, ctx.distributor.id)
    await TeletraanOrchestrator().handle(ctx.raw_webhook, ctx.distributor.id)
    orders = await order_repo.get_by_session(ctx.session.id)
    assert len(orders) == 1   # not 2

async def test_technical_error_sends_fallback(mock_ctx, mock_ai_failure):
    """AI provider failure must still produce a customer response."""
    ctx = mock_ctx(channel="A", message="order karna hai")
    await TeletraanOrchestrator().handle(ctx.raw_webhook, ctx.distributor.id)
    assert mock_whatsapp.messages_sent[-1].body == ERROR_MESSAGES["technical_error"]

async def test_invalid_fsm_transition_graceful(mock_ctx):
    """Confirm without any items in order should not crash."""
    ctx = mock_ctx(channel="A", message="CONFIRM", order_state="idle")
    await TeletraanOrchestrator().handle(ctx.raw_webhook, ctx.distributor.id)
    # Verify: bot sends redirect message, no exception raised
```

---

## GIT COMMIT FORMAT FOR ORCHESTRATOR CHANGES

```
feat(core): implement ChannelAOrchestrator with full intent routing

Orchestrator coordinates:
- Intent classification via active AI provider
- MCP tool execution for catalog/order operations
- FSM state transition validation
- OrderContext persist-before-respond guarantee
- Fallback error handling for all failure modes

Handles intents: add_item, remove_item, modify_quantity,
confirm_order, cancel_order, view_bill, request_discount,
check_stock, ask_price, reorder, greeting, unrelated

Integration tests: 8 scenarios covering full order flow,
duplicate message idempotency, AI failure fallback, FSM
invalid transition handling.

Signed-off-by: Abdullah-Khan-Niazi
```

---

*End of SKILL: orchestration v1.0*
