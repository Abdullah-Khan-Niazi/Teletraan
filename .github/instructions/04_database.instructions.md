---
applyTo: "app/db/**,app/**/repositories/**,app/**/*repo*.py,app/**/*model*.py"
---

# SKILL 04 — DATABASE & REPOSITORY PATTERN
## Source: `docs/skills/SKILL_database.md`

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

---

## MULTI-TENANT ISOLATION — NON-NEGOTIABLE

EVERY query on tenant-scoped tables MUST include `distributor_id` filter.
Missing distributor_id = data leak between tenants.

```python
# CORRECT
result = await client.table("orders")
    .select("*")
    .eq("distributor_id", distributor_id)  # ALWAYS include
    .eq("status", "pending")
    .execute()

# WRONG — never query without tenant scope
result = await client.table("orders").select("*").execute()
```

---

## REPOSITORY PATTERN

Every repository file structure:

```python
"""[Entity] repository — all database operations for the [table] table."""

from __future__ import annotations
from typing import Optional
from uuid import UUID

from app.db.client import get_db_client
from app.db.models.[entity] import [Entity], [Entity]Create, [Entity]Update
from app.core.exceptions import DatabaseError, NotFoundError
from loguru import logger


class [Entity]Repository:
    """Repository for [table] table operations."""

    TABLE = "[table_name]"

    async def get_by_id(self, id: str) -> Optional[[Entity]]:...
    async def get_by_id_or_raise(self, id: str) -> [Entity]:...
    async def create(self, data: [Entity]Create) -> [Entity]:...
    async def update(self, id: str, data: [Entity]Update) -> [Entity]:...
    async def soft_delete(self, id: str) -> bool:...
    # Plus domain-specific methods
```

---

## SUPABASE CLIENT (app/db/client.py)

```python
def get_db_client() -> AsyncClient:
    """Return the initialized Supabase async client."""
    if _client is None:
        raise DatabaseError("Supabase client not initialized.")
    return _client

async def init_client() -> None:
    """Initialize Supabase client. Call once at startup."""

async def health_check() -> bool:
    """Return True if DB is reachable. Never raises."""
```

---

## PYDANTIC MODELS FOR DB

Every table has three Pydantic v2 models:
- `[Entity]` — full row (returned from DB)
- `[Entity]Create` — fields for INSERT (no id, created_at, updated_at)
- `[Entity]Update` — all fields Optional (for PATCH)

```python
class Order(BaseModel):
    id: UUID
    distributor_id: UUID
    customer_id: UUID
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

class OrderCreate(BaseModel):
    distributor_id: UUID
    customer_id: UUID
    status: OrderStatus = OrderStatus.DRAFT

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    confirmed_at: Optional[datetime] = None
```

---

## ERROR HANDLING IN REPOSITORIES

```python
async def get_by_id(self, id: str) -> Optional[Entity]:
    try:
        client = get_db_client()
        result = await client.table(self.TABLE).select("*").eq("id", id).single().execute()
        if result.data:
            return Entity.model_validate(result.data)
        return None
    except Exception as exc:
        if "no rows returned" in str(exc).lower():
            return None
        raise DatabaseError(f"Failed to fetch {self.TABLE}: {exc}", operation="get_by_id") from exc
```

---

## MIGRATION RULES

- Migrations stored in `db/migrations/` as numbered SQL files: `001_create_distributors.sql`
- Migrations run via Supabase dashboard or `db/migrate.py` script
- Each migration is idempotent (IF NOT EXISTS, etc.)
- Never modify a migration that has been applied to production — create a new migration
- Commit migrations separately from application code
