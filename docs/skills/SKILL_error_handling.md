# SKILL: Error Handling Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before implementing any module with external I/O.

---

## IDENTITY

This skill defines the complete error handling strategy for TELETRAAN. Bad error
handling is invisible until it isn't — then it's a customer not getting a
confirmation, a payment silently failing, or a subscription wrongly suspended.
Every error must be caught, logged, classified, and handled with a defined outcome.
"Undefined behavior" is not acceptable in a production system handling money.

---

## EXCEPTION HIERARCHY

Defined in `app/core/exceptions.py`. All custom exceptions inherit from this tree.

```
TeletraanBaseException
├── DatabaseError                  # Supabase/PostgreSQL failures
├── WhatsAppAPIError               # Meta Cloud API failures
│   └── WhatsAppRateLimitError     # 429 specifically
├── AIProviderError                # AI provider API failures
│   ├── AITranscriptionError       # Voice transcription failures
│   └── AICompletionError          # Text completion failures
├── PaymentGatewayError            # Payment API failures
│   └── PaymentSignatureError      # Invalid webhook signature
├── RateLimitError                 # Internal rate limit enforcement
├── ValidationError                # Input validation failures
├── SessionError                   # Session state machine errors
│   └── StateTransitionError       # Invalid FSM state transition
├── OrderContextError              # Order context store errors
│   └── OrderContextConflictError  # Optimistic concurrency failure
├── ConfigurationError             # Missing/invalid env config
└── NotFoundError                  # DB record not found
```

---

## THE THREE CATEGORIES OF FAILURES

### Category 1: Retryable
Transient failures — will likely succeed on retry.
- Network timeout
- AI provider 429 / 503
- WhatsApp API 429
- Supabase connection timeout

**Action: Retry with exponential backoff via tenacity.**

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def call_external_api(...):
    ...
```

### Category 2: Permanent (don't retry)
Errors where retry will not help.
- 401 Unauthorized (wrong API key)
- 400 Bad Request (invalid payload)
- 404 Not Found
- Input validation failure

**Action: Log, raise typed exception, do NOT retry.**

### Category 3: Critical (alert owner)
Failures that indicate systemic issues.
- Database completely unreachable after retries
- AI provider unreachable after retries
- Webhook signature verification fails (possible attack)
- Payment gateway callback fails all retries

**Action: Log CRITICAL, send WhatsApp alert to owner, continue serving other requests.**

---

## GLOBAL FASTAPI EXCEPTION HANDLER

In `app/main.py`:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    logger.error(
        "Unhandled exception",
        request_id=request_id,
        path=str(request.url),
        exc_type=type(exc).__name__,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id}
    )
```

Never expose internal error details to external callers in production.
Always include `request_id` in error responses for tracing.

---

## WEBHOOK EXCEPTION STRATEGY

Webhooks from Meta and payment gateways have a critical constraint:
**The gateway retries if it receives non-200. This causes duplicate processing.**

### Rule: Webhook handlers always return 200, even on internal errors.

```python
@router.post("/webhook/jazzcash/callback")
async def jazzcash_callback(request: Request) -> Response:
    try:
        payload = await request.json()
        await webhook_handlers.handle_payment_callback("jazzcash", payload)
    except PaymentSignatureError:
        logger.warning("Invalid JazzCash signature — possible tampered request")
        # Return 200 anyway to prevent replay storm
        # Security: we already rejected it internally
    except Exception as e:
        logger.error("JazzCash callback processing failed", error=str(e))
        # Return 200 — we'll reconcile manually via payment_gateway_log
    return Response(status_code=200)
```

Exception: signature verification failure → log as security warning, return 200,
but absolutely do not process the callback.

---

## AI PROVIDER FAILURE FALLBACK

When the AI provider fails (after retries), the bot must not go silent.
Implement rule-based fallback responses in `app/ai/response_generator.py`.

```python
async def generate_response(context, language) -> str:
    try:
        result = await ai_provider.text_complete(...)
        if result.success:
            return result.content
        # Fall through to fallback
    except AIProviderError as e:
        logger.warning("AI provider failed, using fallback", error=str(e))

    # Fallback: return template-based response
    return get_fallback_response(context.current_state, language)
```

Fallback responses for every critical state must exist in templates.
Fallback responses are not AI-generated — they are static templates.
Fallback must be grammatically correct in all three languages.

The bot shows a message like:
"Maafi chahta hoon — thodi der ke liye technical masla aa gaya. Thodi der baad try karein."
(Sorry — we're experiencing a brief technical issue. Please try again in a moment.)

---

## DATABASE ERROR HANDLING

All repository methods:
- Wrap every DB call in try/except
- On `Exception`: log with table name and operation, raise `DatabaseError`
- Never let Supabase exceptions bubble up raw to business logic

```python
async def get_customer_by_phone(
    self, distributor_id: UUID, phone: str
) -> Customer | None:
    try:
        result = await self._client.table("customers") \
            .select("*") \
            .eq("distributor_id", str(distributor_id)) \
            .eq("whatsapp_number", phone) \
            .maybe_single() \
            .execute()
        return Customer.model_validate(result.data) if result.data else None
    except Exception as e:
        raise DatabaseError(
            f"Failed to fetch customer for distributor {distributor_id}: {e}"
        ) from e
```

---

## RETRY CONFIGURATION BY USE CASE

| Use Case | Max Retries | Backoff | Retry On |
|---|---|---|---|
| AI text completion | 3 | exp(1s, 2s, 4s) | timeout, 429, 503 |
| AI voice transcription | 2 | exp(2s, 4s) | timeout, 503 |
| WhatsApp message send | 3 | exp(1s, 2s, 4s) | timeout, 429, 5xx |
| Payment link generation | 2 | exp(2s, 4s) | timeout, 5xx |
| Supabase DB query | 2 | exp(0.5s, 1s) | timeout, connection error |
| WhatsApp media download | 3 | exp(1s, 2s, 4s) | timeout, 5xx |
| Scheduled message send | 3 (spread over hours) | cron-based | any send failure |

---

## ORDER CONTEXT CONFLICT HANDLING

When `save_context` detects a version mismatch (concurrent message from same user):

1. Log warning with both version numbers
2. Reload context from DB (get fresh version)
3. Re-apply the change that was being saved
4. Retry save with new version
5. If conflict persists after 3 attempts → raise `OrderContextConflictError`
6. On `OrderContextConflictError`: send customer "Aapka message process ho raha hai, thodi der karein" and stop processing this message

This prevents race conditions when customers send rapid-fire messages.

---

## SILENT FAILURE PREVENTION

These patterns are FORBIDDEN:

```python
try:
    await send_notification(...)
except Exception:
    pass  # NEVER — swallowing errors

try:
    result = await db_call(...)
except Exception as e:
    return None  # NEVER — returning None to hide errors without logging

try:
    await critical_operation(...)
except Exception as e:
    logger.error(str(e))  # PARTIAL — log but not raise means caller doesn't know it failed
```

Every except block must either:
1. Log + re-raise
2. Log + raise a typed exception
3. Log + return a typed failure result
4. Log + execute a defined fallback action

Never: log + ignore. Never: ignore without logging.
