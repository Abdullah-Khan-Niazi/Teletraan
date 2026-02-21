# SKILL: Logging Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before writing any logging code.

---

## IDENTITY

This skill defines how TELETRAAN logs everything that happens. Good logging is
the difference between debugging a production issue in 5 minutes versus 5 hours.
Bad logging (or no logging) means flying blind. Every significant event must be
observable. Every error must be traceable. No PII in logs, ever.

---

## FRAMEWORK: LOGURU

```python
from loguru import logger
```

Configured in `app/core/logging.py`. This module is imported and called in
`app/main.py` during startup, before anything else.

---

## CONFIGURATION — app/core/logging.py

```python
import sys
from loguru import logger
from app.core.config import get_settings

def configure_logging() -> None:
    settings = get_settings()
    logger.remove()  # Remove default handler

    if settings.app_env == "production":
        # Structured JSON logs for log aggregation (Render log drain, etc.)
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{line} | {message} | {extra}",
            level=settings.log_level,
            serialize=True,       # JSON output
            filter=mask_pii,      # PII masking filter
        )
    else:
        # Human-readable colored logs for development
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> | {message} | {extra}",
            level="DEBUG",
            colorize=True,
            filter=mask_pii,
        )

    # Always write errors to a rotating file
    logger.add(
        "logs/teletraan_{time:YYYY-MM-DD}.log",
        rotation="00:00",     # New file daily at midnight
        retention="30 days",  # Keep 30 days of logs
        level="WARNING",      # Only WARNING and above to file
        serialize=True,
        filter=mask_pii,
    )
```

---

## PII MASKING FILTER — MANDATORY

Phone numbers must NEVER appear in plain text in any log.
Mask all phone numbers to show only last 4 digits.

```python
import re

PHONE_PATTERN = re.compile(r'(\+?92|0)?[\s\-]?([0-9]{2,4})[\s\-]?([0-9]{7,8})')

def mask_phone(number: str) -> str:
    """Mask a phone number to show only last 4 digits."""
    cleaned = re.sub(r'[\s\-\(\)]', '', number)
    if len(cleaned) >= 4:
        return "****" + cleaned[-4:]
    return "****"

def mask_pii(record: dict) -> bool:
    """Loguru filter that masks phone numbers in all log fields."""
    # Mask in message
    record["message"] = PHONE_PATTERN.sub(
        lambda m: "****" + m.group(0)[-4:], record["message"]
    )
    # Mask in extra fields
    for key, value in record.get("extra", {}).items():
        if isinstance(value, str) and PHONE_PATTERN.search(value):
            record["extra"][key] = PHONE_PATTERN.sub(
                lambda m: "****" + m.group(0)[-4:], value
            )
    return True
```

---

## LOG LEVELS — WHEN TO USE WHAT

### DEBUG
Only in development. Never in production by default.
Use for: DB query details, AI token counts, individual session state transitions.
```python
logger.debug("Session state transition", from_state=prev, to_state=new, session_id=sid)
```

### INFO
Significant business events. These should be meaningful to a product manager.
Use for: order confirmed, payment received, customer registered, distributor suspended, reminder sent.
```python
logger.info("Order confirmed", order_number=order.order_number, total_paisas=order.total_paisas, distributor_id=str(distributor_id))
```

### WARNING
Something unexpected happened but the system recovered.
Use for: fuzzy match below threshold (used fallback), rate limit approached, AI fallback triggered, stale session cleaned up.
```python
logger.warning("AI provider fallback triggered", reason=str(e), state=state, distributor_id=str(did))
```

### ERROR
A failure that affected a user or business operation.
Use for: API call failed after all retries, DB write failed, payment callback processing failed.
```python
logger.error("WhatsApp send failed after retries", recipient="****" + phone[-4:], error=str(e), message_type=msg_type)
```

### CRITICAL
System-level failure requiring immediate attention.
Use for: DB completely unreachable, HMAC verification failed (possible attack), server startup failed.
```python
logger.critical("Database unreachable — all requests failing", component="supabase", consecutive_failures=count)
```

---

## STRUCTURED LOGGING — ALWAYS USE EXTRA FIELDS

Never embed IDs and values in the message string. Use structured extra fields.

```python
# CORRECT — machine-parseable
logger.info(
    "Order confirmed",
    order_number=order.order_number,
    distributor_id=str(distributor.id),
    customer_id=str(customer.id),
    total_paisas=order.total_paisas,
    item_count=len(items),
)

# WRONG — not queryable in log aggregation
logger.info(f"Order {order.order_number} confirmed for distributor {distributor.id}")
```

---

## REQUEST ID MIDDLEWARE

Every incoming webhook request gets a UUID `request_id` assigned.
This ID threads through all log entries for that request.

```python
# In webhook handler
request_id = str(uuid4())
with logger.contextualize(request_id=request_id):
    logger.info("Webhook received", message_type=parsed.type)
    await process_message(parsed)
    logger.info("Webhook processed")
```

All log entries within the `contextualize` block automatically include `request_id`.

---

## JOB LOGGING PATTERN

Every scheduler job must log start, completion, and key metrics:

```python
async def run_daily_order_summary() -> None:
    start = time.monotonic()
    logger.info("Job started", job="daily_order_summary")
    try:
        distributors_processed = 0
        reports_sent = 0
        # ... job logic ...
        elapsed = int((time.monotonic() - start) * 1000)
        logger.info(
            "Job completed",
            job="daily_order_summary",
            duration_ms=elapsed,
            distributors_processed=distributors_processed,
            reports_sent=reports_sent,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.error(
            "Job failed",
            job="daily_order_summary",
            duration_ms=elapsed,
            error=str(e),
        )
        raise
```

---

## WHAT TO NEVER LOG

- Full phone numbers in plain text
- API keys, secrets, passwords
- Full payment card numbers (not applicable here but general rule)
- Full webhook payloads from payment gateways (may contain sensitive data)
  — log sanitized versions only (exclude signature fields, credentials)
- Full AI prompts (may contain customer order data — log only intent and token count)
- CNIC numbers
- Customer email addresses

---

## LOG RETENTION

- Render/Railway stdout: streamed to hosting platform log drain (configure Papertrail or similar)
- File logs: 30 days rotation, WARNING and above only
- Supabase `audit_log` table: permanent, all state-changing operations
- Supabase `notifications_log`: 90 days (cleanup job prunes older records)
- Supabase `analytics_events`: 12 months then archive

---

## AI INTERACTION LOGGING

Every Gemini/OpenAI call logs to both loguru and `ai_provider_log` table:

```python
logger.debug(
    "AI call completed",
    provider=provider_name,
    operation=operation,
    input_tokens=result.input_tokens,
    output_tokens=result.output_tokens,
    latency_ms=result.latency_ms,
    success=result.success,
)
```

This is essential for cost monitoring and debugging conversation quality issues.
