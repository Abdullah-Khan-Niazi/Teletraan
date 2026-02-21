# SKILL: Python Standards Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before writing any Python code.

---

## IDENTITY

This skill defines the Python code quality, style, and structural standards that
every file in the TELETRAAN project must follow. No exceptions. No shortcuts.
The goal is production-grade code that a senior engineer can maintain, audit, and
extend without reading documentation to understand what a function does.

---

## STYLE AND FORMATTING

### Tools (enforced via pre-commit)
- **black** — code formatter. Run before every commit. Never manually fight black.
- **isort** — import sorter. Configured in pyproject.toml with `profile = "black"`.
- **flake8** — linter. Max line length 88 (matches black).

### pyproject.toml minimum config
```toml
[tool.black]
line-length = 88
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 88

[tool.flake8]
max-line-length = 88
extend-ignore = ["E203", "W503"]
```

### Import ordering (isort handles this automatically)
1. Standard library
2. Third-party packages
3. Internal app imports (absolute, never relative for cross-module)

---

## TYPE HINTS — MANDATORY

Every function signature must have complete type hints. Every class attribute
must be typed. No `Any` unless genuinely unavoidable and explicitly commented.

### Required
```
def get_customer(distributor_id: UUID, phone: str) -> Customer | None:
```

### Forbidden
```
def get_customer(distributor_id, phone):     # NO — no type hints
def get_customer(distributor_id: Any, ...):  # NO — Any without justification
```

### Use `from __future__ import annotations` at top of every file for forward refs.

---

## DOCSTRINGS — GOOGLE STYLE — MANDATORY

Every public class and every public function must have a Google-style docstring.
Private methods (underscore prefix) should have docstrings if logic is non-obvious.
Module-level docstring required on every file.

### Module docstring format
```python
"""Module for [purpose].

[Optional longer description if needed.]
"""
```

### Function docstring format
```python
def calculate_bill(items: list[OrderItemDraft], discount_rules: list[DiscountRule]) -> BillingSummary:
    """Calculate the complete bill for an order draft.

    Applies automatic discount rules in priority order, calculates bonus units,
    and computes delivery charges based on customer delivery zone.

    Args:
        items: List of order item drafts with quantities and prices.
        discount_rules: Active discount rules for this distributor.

    Returns:
        BillingSummary with all amounts in paisas.

    Raises:
        BillingError: If any item has an invalid price (zero or negative).
    """
```

---

## EXCEPTION HANDLING — EVERY I/O BOUNDARY

### Rule: Never let external call exceptions propagate unhandled.
Every database call, API call, file read, and network request must be wrapped.

### Pattern
```python
try:
    result = await supabase_client.table("orders").select("*").execute()
except Exception as e:
    logger.error("DB query failed", table="orders", error=str(e))
    raise DatabaseError(f"Failed to fetch orders: {e}") from e
```

### Custom exception hierarchy (from app/core/exceptions.py)
- `TeletraanBaseException` — root
  - `DatabaseError`
  - `WhatsAppAPIError`
  - `AIProviderError`
    - `AITranscriptionError`
    - `AICompletionError`
  - `PaymentGatewayError`
  - `RateLimitError`
  - `ValidationError`
  - `SessionError`
  - `OrderContextError`
  - `ConfigurationError`

### Never catch bare Exception in business logic. Catch specific types.
### Never swallow exceptions silently (empty except block).

---

## LOGGING — LOGURU — ALWAYS STRUCTURED

### Never use `print()` in production code paths.
### Always use structured fields with loguru.

```python
from loguru import logger

# Good
logger.info("Order confirmed", order_id=str(order_id), distributor_id=str(distributor_id), total_paisas=total)

# Bad
print(f"Order {order_id} confirmed")  # NEVER
logger.info(f"Order {order_id} confirmed")  # Bad — not structured
```

### Log levels
- `DEBUG` — detailed trace, DB queries, AI token counts (dev only)
- `INFO` — significant events: order confirmed, payment received, distributor suspended
- `WARNING` — recoverable issues: fuzzy match below threshold, rate limit approached
- `ERROR` — failures that need attention: API call failed after retries, DB write failed
- `CRITICAL` — system-level failures: DB unreachable, server startup failed

### PII masking — from app/core/logging.py
Phone numbers must always be masked in log output (show only last 4 digits).
Full phone number never appears in any log. Masking applied at loguru filter level.

---

## ENVIRONMENT VARIABLES — NO HARDCODING

### Rule: Zero hardcoded secrets, URLs, credentials, or configuration values.

All configuration accessed via `get_settings()` which returns the Pydantic Settings singleton.

```python
from app.core.config import get_settings

settings = get_settings()
api_key = settings.gemini_api_key  # From env
```

### Never
```python
API_KEY = "AIzaSy..."           # NEVER
BASE_URL = "https://..."        # NEVER hardcode in business logic
TIMEOUT = 30                    # NEVER — use settings.ai_request_timeout_seconds
```

### Startup validation
Config must validate ALL required vars at startup. App must refuse to start if any
required variable is missing. Use Pydantic `@validator` or `model_validator`.

---

## INPUT VALIDATION — PYDANTIC EVERYWHERE

All external input — WhatsApp payloads, API request bodies, payment callbacks —
validated via Pydantic models before entering any business logic.

Invalid input → `ValidationError` logged and request rejected with 422 (API)
or handled gracefully (WhatsApp — send error message to user).

Input length limits enforced:
- Customer text message: 2000 characters max
- Medicine name: 500 characters max
- Address: 1000 characters max
- Description fields: 5000 characters max

---

## ASYNC — ALWAYS

This is a fully async application. FastAPI, Supabase, httpx are all async.

- All route handlers: `async def`
- All repository methods: `async def`
- All service methods: `async def`
- All AI provider methods: `async def`
- All payment gateway methods: `async def`

Never use `time.sleep()` — use `asyncio.sleep()`.
Never use blocking I/O in async context.
Use `asyncio.gather()` for concurrent independent operations.

---

## DEPENDENCY INJECTION — NOT GLOBAL STATE

Services receive their dependencies as constructor arguments or function parameters.
No service instantiates its own dependencies internally.

### Good
```python
class OrderService:
    def __init__(self, order_repo: OrderRepository, billing_service: BillingService):
        self.order_repo = order_repo
        self.billing = billing_service
```

### Bad
```python
class OrderService:
    def __init__(self):
        self.order_repo = OrderRepository()  # BAD — hidden dependency
```

Database client is the one exception — Supabase client is a singleton from `get_db_client()`.

---

## FILE STRUCTURE WITHIN MODULES

Every Python file structure:
```
1. Module docstring
2. from __future__ import annotations
3. Standard library imports
4. Third-party imports
5. Internal imports
6. Module-level constants (if any)
7. Class definitions (each with docstring)
8. Standalone function definitions (each with docstring)
```

---

## RETURN VALUES — NEVER NONE SILENTLY

Functions that can fail must either:
- Return `T | None` and caller checks
- Raise a typed exception
- Return a Result-like object

Never return `None` to indicate failure without documenting it in the type hint.
Never raise generic `Exception` — always a typed custom exception.

---

## CONSTANTS AND ENUMS

All string literals used as state names, status values, enum values must be
defined in `app/core/constants.py` and imported, never hardcoded inline.

```python
# Good
from app.core.constants import OrderStatus
if order.status == OrderStatus.CONFIRMED:

# Bad
if order.status == "confirmed":  # NEVER magic strings
```

Use Python `enum.Enum` or `enum.StrEnum` (Python 3.11+) for all enumerated values.

---

## TESTING REQUIREMENTS

See SKILL_testing.md for full testing protocol.
Minimum: every public function in core business logic modules has at least one test.
