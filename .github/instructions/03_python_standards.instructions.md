---
applyTo: "**/*.py"
---

# SKILL 03 — PYTHON STANDARDS
## Source: `docs/skills/SKILL_python_standards.md`

---

## FORMATTING TOOLS (enforced via pre-commit)

- **black** — formatter. Line length 88. Never fight it.
- **isort** — import sorter. Profile: `"black"`.
- **flake8** — linter. Max line 88. Extend-ignore: `E203, W503`.

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

---

## TYPE HINTS — MANDATORY

Every function parameter and return value must be typed. No bare `Any`.
Use `from __future__ import annotations` at the top of every file.

```python
# CORRECT
def get_customer(distributor_id: UUID, phone: str) -> Customer | None: ...

# WRONG — banned
def get_customer(distributor_id, phone): ...
def get_customer(distributor_id: Any, ...): ...
```

---

## DOCSTRINGS — GOOGLE STYLE — ALL PUBLIC FUNCTIONS/CLASSES

```python
def calculate_bill(items: list[OrderItemDraft], discount_rules: list[DiscountRule]) -> BillingSummary:
    """Calculate the complete bill for an order draft.

    Applies automatic discount rules in priority order, calculates bonus
    units, and computes delivery charges based on customer delivery zone.

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

## FILE STRUCTURE — EVERY PYTHON FILE

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

## ASYNC — ALWAYS

This is a fully async application.

- All route handlers: `async def`
- All repository methods: `async def`
- All service methods: `async def`
- All AI provider methods: `async def`
- All payment gateway methods: `async def`
- Use `asyncio.sleep()` never `time.sleep()`
- Use `asyncio.gather()` for concurrent independent operations
- NEVER blocking I/O in async context

---

## EXCEPTION HANDLING — EVERY I/O BOUNDARY

```python
try:
    result = await supabase_client.table("orders").select("*").execute()
except Exception as e:
    logger.error("DB query failed", table="orders", error=str(e))
    raise DatabaseError(f"Failed to fetch orders: {e}") from e
```

Never catch bare `Exception` in business logic — catch specific types.
Never swallow exceptions silently.

---

## LOGGING — LOGURU — ALWAYS STRUCTURED

```python
# CORRECT
logger.info("Order confirmed", order_id=str(order_id), total_paisas=total)

# WRONG — never
print(f"Order {order_id} confirmed")
logger.info(f"Order {order_id} confirmed")  # Not structured
```

---

## ENVIRONMENT VARIABLES — NEVER HARDCODE

```python
# CORRECT
from app.core.config import get_settings
settings = get_settings()
api_key = settings.gemini_api_key

# WRONG — never
API_KEY = "AIzaSy..."
```

---

## INPUT VALIDATION — PYDANTIC EVERYWHERE

All external input validated via Pydantic models before any business logic.
Length limits enforced: text 2000 chars, name 255 chars, address 500 chars.

---

## DEPENDENCY INJECTION — NOT GLOBAL STATE

```python
# CORRECT
class OrderService:
    def __init__(self, order_repo: OrderRepository, billing_service: BillingService):
        self.order_repo = order_repo
        self.billing = billing_service

# WRONG
class OrderService:
    def __init__(self):
        self.order_repo = OrderRepository()  # hidden dependency
```

---

## CONSTANTS AND ENUMS

Use `enum.Enum` or `enum.StrEnum`. Define in `app/core/constants.py`.
Never use magic strings inline.

```python
# CORRECT
from app.core.constants import OrderStatus
if order.status == OrderStatus.CONFIRMED:

# WRONG
if order.status == "confirmed":
```

---

## RETURN VALUES — NEVER None SILENTLY

Functions that can fail must:
- Return `T | None` and caller checks, OR
- Raise a typed exception, OR
- Return a Result-like object

Never raise generic `Exception` — always a typed custom exception.
