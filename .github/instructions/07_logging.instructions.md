---
applyTo: "**/*.py"
---

# SKILL 07 — LOGGING
## Source: `docs/skills/SKILL_logging.md`

---

## FRAMEWORK: LOGURU

```python
from loguru import logger
```

Configured in `app/core/logging.py`. Called at startup in `app/main.py` before anything else.

---

## RULE: NEVER `print()` IN PRODUCTION CODE

```python
# CORRECT — structured, queryable
logger.info("order.confirmed", order_id=str(order_id), distributor_id=str(did), total_paisas=total)

# WRONG — never
print(f"Order {order_id} confirmed")
logger.info(f"Order {order_id} confirmed")   # Not structured
```

---

## LOG LEVELS

| Level | When |
|---|---|
| `DEBUG` | Detailed trace, DB queries, AI token counts (dev only) |
| `INFO` | Order confirmed, payment received, distributor suspended |
| `WARNING` | Fuzzy match below threshold, rate limit approached, AI fallback triggered |
| `ERROR` | API call failed after retries, DB write failed |
| `CRITICAL` | DB unreachable, server startup failed, possible attack detected |

---

## STRUCTURED EVENT NAMING CONVENTION

Use `noun.verb` format for event names:

```python
logger.info("session.created", channel="channel_a")
logger.info("order.confirmed", order_id=str(oid))
logger.info("payment.received", gateway="jazzcash", amount_paisas=5000)
logger.warning("ai.fallback_triggered", reason="provider_timeout")
logger.error("db.write_failed", table="orders", error=str(exc))
logger.critical("db.unreachable", retries=3)
```

---

## PII MASKING — PHONE NUMBERS

Phone numbers must NEVER appear plain in logs. Show only last 4 digits.

```python
import re

PHONE_PATTERN = re.compile(r'(\+?92|0)?[\s\-]?([0-9]{2,4})[\s\-]?([0-9]{7,8})')

def mask_phone(number: str) -> str:
    """Return phone number with all but last 4 digits masked."""
    digits_only = re.sub(r'\D', '', number)
    return f"****{digits_only[-4:]}"
```

PII masking is applied at the loguru filter level — automatically masks all log output.
NEVER manually build phone number strings for log messages.

---

## LOGGING CONFIGURATION (app/core/logging.py)

```python
def configure_logging() -> None:
    settings = get_settings()
    logger.remove()  # Remove default handler

    if settings.app_env == "production":
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{line} | {message} | {extra}",
            level=settings.log_level,
            serialize=True,      # JSON for log aggregation
            filter=mask_pii,
        )
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> | {message} | {extra}",
            level="DEBUG",
            colorize=True,
            filter=mask_pii,
        )

    # Always write WARNING+ to rotating file
    logger.add(
        "logs/teletraan_{time:YYYY-MM-DD}.log",
        rotation="00:00",      # New file daily
        retention="30 days",
        level="WARNING",
        serialize=True,
        filter=mask_pii,
    )
```

---

## MODULE-LEVEL LOGGER PATTERN

Add context to log records to track across requests:

```python
# In request handlers
with logger.contextualize(
    request_id=request_id,
    distributor_id=str(distributor_id),
    number_suffix=whatsapp_number[-4:],     # PII-safe
):
    await process_message(...)
    # All log calls inside inherit this context
```

---

## COMMENTS — WHY NOT WHAT

```python
# GOOD comment — explains why
# Mask phone number to last 4 digits only — PII compliance
safe_number = f"****{whatsapp_number[-4:]}"

# BAD comment — redundant (code already says this)
# Get last 4 digits of phone number
safe_number = whatsapp_number[-4:]
```
