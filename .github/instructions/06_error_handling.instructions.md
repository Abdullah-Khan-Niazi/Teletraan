---
applyTo: "**/*.py"
---

# SKILL 06 — ERROR HANDLING
## Source: `docs/skills/SKILL_error_handling.md`

---

## EXCEPTION HIERARCHY (app/core/exceptions.py)

```
TeletraanBaseException
├── DatabaseError
├── WhatsAppAPIError
│   └── WhatsAppRateLimitError
├── AIProviderError
│   ├── AITranscriptionError
│   └── AICompletionError
├── PaymentGatewayError
│   └── PaymentSignatureError
├── RateLimitError
├── ValidationError
├── SessionError
│   └── StateTransitionError
├── OrderContextError
│   └── OrderContextConflictError
├── ConfigurationError
└── NotFoundError
```

All custom exceptions inherit from `TeletraanBaseException`.
Never raise generic `Exception` — always a typed custom exception.

---

## THE THREE FAILURE CATEGORIES

### Category 1: Retryable (transient — retry with backoff)
- Network timeout, AI provider 429/503, WhatsApp 429, Supabase timeout

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def call_external_api(...): ...
```

### Category 2: Permanent (don't retry)
- 401 Unauthorized, 400 Bad Request, 404 Not Found, validation failures
- Action: log, raise typed exception, do NOT retry

### Category 3: Critical (alert owner)
- DB completely unreachable, AI provider unreachable, payment callback fails all retries
- Action: `logger.critical(...)`, send WhatsApp alert to owner

---

## GLOBAL FASTAPI EXCEPTION HANDLER

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

---

## WEBHOOK EXCEPTION STRATEGY

**Webhook handlers ALWAYS return 200, even on internal errors.**
Gateway retries on non-200 → duplicate processing. Avoid at all costs.

```python
@router.post("/webhook/payment/callback")
async def payment_callback(request: Request) -> Response:
    try:
        payload = await request.json()
        await webhook_handlers.handle_payment_callback(payload)
    except PaymentSignatureError:
        logger.warning("Invalid payment signature — possible tampered request")
        # Return 200 anyway — we already rejected it internally
    except Exception as e:
        logger.error("Payment callback processing failed", error=str(e))
        # Return 200 — reconcile manually via payment_gateway_log
    return Response(status_code=200)
```

Exception: WhatsApp webhook GET challenge verification — must return exact challenge value.

---

## AI PROVIDER FAILURE FALLBACK

When AI provider fails after retries, bot must NOT go silent:

```python
async def generate_response(context, language) -> str:
    try:
        result = await ai_provider.text_complete(...)
        if result.success:
            return result.content
        raise AICompletionError("Provider returned unsuccessful result")
    except AIProviderError:
        logger.warning("AI provider failed — using rule-based fallback")
        return get_fallback_response(context.current_state, language)
```

Fallback responses defined in `app/ai/fallback_responses.py`.

---

## EXCEPTION CHAINING — ALWAYS USE `from exc`

```python
except Exception as exc:
    raise DatabaseError(f"Failed to fetch order: {exc}") from exc
```

Never `raise DatabaseError(...)` without `from exc` on caught exceptions.
This preserves the original traceback for debugging.

---

## NEVER SWALLOW EXCEPTIONS

```python
# WRONG — silent failure
try:
    await do_something()
except Exception:
    pass  # NEVER

# CORRECT
try:
    await do_something()
except SpecificError as exc:
    logger.error("Operation failed", error=str(exc))
    raise  # or raise typed exception
```
