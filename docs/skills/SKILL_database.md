# DATABASE AND REPOSITORY PATTERN SKILL
## SKILL: database | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines how TELETRAAN interacts with Supabase/PostgreSQL.
All database access goes through the repository layer. No direct DB calls
in handlers, flows, or services. The repository pattern is the law.

---

## ARCHITECTURE

```
Handler / Service / Flow
         ↓
  Repository (e.g., order_repo.py)
         ↓
  Supabase Client (db/client.py)
         ↓
  PostgreSQL (Supabase)
```

Business logic never sees Supabase SDK calls.
Repositories never contain business logic.
This separation makes testing trivial — mock the repo, not the DB.

---

## SUPABASE CLIENT (app/db/client.py)

Implement as a singleton using Python's module-level instance:

```python
# Initialized once at startup in main.py lifespan
# Accessed everywhere as: from app.db.client import get_db_client

def get_db_client() -> AsyncClient:
    """Return the initialized Supabase async client."""
    if _client is None:
        raise DatabaseError("Supabase client not initialized. Call init_client() first.")
    return _client

async def init_client() -> None:
    """Initialize Supabase client. Call once at application startup."""
    # Create AsyncClient with service role key for full access
    # Verify connectivity with a lightweight query
    # Log success or raise DatabaseError

async def health_check() -> bool:
    """Return True if DB is reachable and responding."""
    # Try a simple SELECT 1 or count on a small table
    # Return False on exception — never raise from health check
```

---

## REPOSITORY PATTERN

### Structure of every repository file:

```python
"""Customer repository — all database operations for the customers table.

This repository provides typed, async access to customer data.
All queries are scoped to distributor_id for multi-tenant isolation.
"""

from __future__ import annotations
from typing import Optional
from uuid import UUID

from app.db.client import get_db_client
from app.db.models.customer import Customer, CustomerCreate, CustomerUpdate
from app.core.exceptions import DatabaseError, NotFoundError
from loguru import logger


class CustomerRepository:
    """Repository for customer table operations."""

    TABLE = "customers"

    async def get_by_number(
        self,
        distributor_id: str,
        whatsapp_number: str,
    ) -> Optional[Customer]:
        """Get customer by WhatsApp number within a distributor's tenant.

        Args:
            distributor_id: UUID of the distributor (tenant scope).
            whatsapp_number: E.164 formatted number.

        Returns:
            Customer if found, None otherwise.

        Raises:
            DatabaseError: On DB connectivity or query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("whatsapp_number", whatsapp_number)
                .eq("is_active", True)
                .single()
                .execute()
            )
            if result.data:
                return Customer.model_validate(result.data)
            return None
        except Exception as exc:
            if "no rows returned" in str(exc).lower():
                return None
            raise DatabaseError(
                f"Failed to fetch customer: {exc}",
                operation="get_by_number",
            ) from exc
```

### Every repository must have these methods (at minimum):

- `get_by_id(id: str) → Optional[Model]`
- `get_by_id_or_raise(id: str) → Model` (raises NotFoundError if not found)
- `create(data: ModelCreate) → Model`
- `update(id: str, data: ModelUpdate) → Model`
- `soft_delete(id: str) → bool` (set is_deleted=True where applicable)
- Domain-specific methods as needed (e.g., `get_by_number`, `list_by_distributor`)

---

## MULTI-TENANT ISOLATION

EVERY query on tenant-scoped tables MUST include `distributor_id` filter.
This is non-negotiable. Missing distributor_id filter = data leak between tenants.

```python
# CORRECT — always scope to distributor
result = await client.table("orders")
    .select("*")
    .eq("distributor_id", distributor_id)  # ← ALWAYS INCLUDE
    .eq("status", "pending")
    .execute()

# WRONG — never query without tenant scope
result = await client.table("orders")
    .select("*")
    .eq("status", "pending")
    .execute()
```

Tables that are NOT tenant-scoped (no distributor_id filter needed):
- `subscription_plans` (global config)
- `service_registry` (global config)
- `audit_log` (owner-level access only)
- `analytics_events` (aggregated — but still filter by distributor_id in most cases)

---

## ERROR HANDLING IN REPOSITORIES

Three exception types from `app/core/exceptions.py`:
- `DatabaseError` — connectivity or query execution failure
- `NotFoundError` — entity doesn't exist (for get_or_raise methods)
- `ConflictError` — unique constraint violation

```python
try:
    result = await client.table(...).insert(data).execute()
    return Model.model_validate(result.data[0])
except Exception as exc:
    error_str = str(exc).lower()
    if "unique constraint" in error_str or "duplicate" in error_str:
        raise ConflictError(f"Record already exists: {exc}") from exc
    raise DatabaseError(f"Insert failed: {exc}", operation="create") from exc
```

Never let raw Supabase/asyncpg exceptions propagate beyond the repository layer.

---

## PYDANTIC MODELS (app/db/models/)

Every table has three Pydantic models:

```python
class CustomerBase(BaseModel):
    """Shared fields for customer creation and update."""
    name: str
    shop_name: str
    address: Optional[str] = None
    language_preference: str = "roman_urdu"

class CustomerCreate(CustomerBase):
    """Fields required to create a new customer."""
    distributor_id: str
    whatsapp_number: str

class CustomerUpdate(BaseModel):
    """Fields that can be updated — all optional."""
    name: Optional[str] = None
    shop_name: Optional[str] = None
    address: Optional[str] = None
    language_preference: Optional[str] = None

class Customer(CustomerBase):
    """Full customer record from DB — includes generated fields."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    distributor_id: str
    whatsapp_number: str
    total_orders: int
    total_spend_paisas: int
    is_active: bool
    is_blocked: bool
    created_at: datetime
    updated_at: datetime
```

Use `model_validate(dict_from_db)` — not `**kwargs` — to construct from DB results.
Add `model_config = ConfigDict(from_attributes=True)` to models that read from DB.

---

## MIGRATIONS

Migration files in `migrations/` are numbered SQL files.
Apply them in order via `scripts/run_migrations.py`.
Never modify an applied migration. Create a new migration instead.

Migration file structure:
```sql
-- migrations/009_create_orders.sql
-- Description: Creates the orders table with full order lifecycle tracking
-- Dependencies: 003_create_customers.sql, 007_create_delivery_zones.sql

BEGIN;

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- ... all columns ...
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger to auto-update updated_at
CREATE TRIGGER orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
```

The `update_updated_at_column()` function must be created in migration 001:
```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';
```

Apply this trigger to every table that has `updated_at`.

---

## ORDERING — AVOIDING NULL RETURNS FROM SUPABASE .single()

Supabase `.single()` raises an exception if 0 rows returned.
Use this pattern to handle gracefully:

```python
# Pattern for get-by-X methods:
result = await client.table(TABLE).select("*").eq(...).execute()
if not result.data:
    return None
return Model.model_validate(result.data[0])
# (Don't use .single() — use .execute() and check result.data)
```

---

## SOFT DELETES

For tables with `is_deleted` column, all SELECT queries must filter:
`.eq("is_deleted", False)`

The `soft_delete()` repository method must:
1. Set `is_deleted = True`
2. Set `deleted_at = NOW()`
3. Log to audit_log

Hard deletes are never used in production — only in tests.

---

## REPOSITORY SINGLETON PATTERN

Repositories are instantiated once and injected. Use this pattern in main.py:

```python
# In app/main.py lifespan:
customer_repo = CustomerRepository()
order_repo = OrderRepository()
# etc.

# Make available via app state:
app.state.customer_repo = customer_repo
app.state.order_repo = order_repo

# In routes — access via request.app.state:
customer_repo: CustomerRepository = request.app.state.customer_repo
```

Or use FastAPI dependency injection with Depends().
Either approach is acceptable — be consistent throughout the codebase.

---

## TESTING REPOSITORIES

For unit tests: mock the repository at the boundary.
For integration tests: use a test schema in Supabase.

```python
# In conftest.py — create test fixtures:
@pytest.fixture
def mock_customer_repo():
    repo = AsyncMock(spec=CustomerRepository)
    repo.get_by_number.return_value = Customer(...)
    return repo
```

Never call real Supabase in unit tests. Use `AsyncMock(spec=Repository)`.
Integration tests use a separate test project in Supabase with test data seeded.
