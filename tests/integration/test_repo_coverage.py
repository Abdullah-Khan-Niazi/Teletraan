"""Tests for DB repositories with mocked Supabase client.

Covers CatalogRepository, CustomerRepository, OrderRepository,
OrderItemRepository, SessionRepository.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ═══════════════════════════════════════════════════════════════
# Supabase mock helper
# ═══════════════════════════════════════════════════════════════

NOW = "2025-01-01T00:00:00Z"
LATER = "2025-01-02T00:00:00Z"
DIST_ID = str(uuid4())
CUST_ID = str(uuid4())


def _mock_supabase(data: list | dict | None = None) -> MagicMock:
    """Create a chainable Supabase mock."""
    mock = MagicMock()
    chain_methods = [
        "table", "select", "insert", "update", "delete", "upsert",
        "eq", "neq", "gt", "gte", "lt", "lte", "in_",
        "like", "ilike", "is_", "not_", "or_",
        "order", "limit", "offset", "range",
        "single", "maybe_single", "on_conflict",
    ]
    for method in chain_methods:
        getattr(mock, method).return_value = mock
    if data is None:
        data = []
    mock.execute = AsyncMock(return_value=MagicMock(data=data))
    return mock


def _catalog_row(**overrides: object) -> dict:
    """Return a complete CatalogItem dict."""
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "medicine_name": "Panadol 500mg",
        "price_per_unit_paisas": 5000,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(overrides)
    return row


def _customer_row(**overrides: object) -> dict:
    """Return a complete Customer dict."""
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "whatsapp_number": "+923001234567",
        "name": "Test Customer",
        "shop_name": "Ali Pharmacy",
        "registered_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(overrides)
    return row


def _order_row(**overrides: object) -> dict:
    """Return a complete Order dict."""
    row = {
        "id": str(uuid4()),
        "order_number": "ORD-20250101-ABCD",
        "distributor_id": DIST_ID,
        "customer_id": CUST_ID,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(overrides)
    return row


def _order_item_row(**overrides: object) -> dict:
    """Return a complete OrderItem dict."""
    row = {
        "id": str(uuid4()),
        "order_id": str(uuid4()),
        "distributor_id": DIST_ID,
        "medicine_name": "Panadol 500mg",
        "quantity_ordered": 10,
        "price_per_unit_paisas": 5000,
        "line_total_paisas": 50000,
        "created_at": NOW,
    }
    row.update(overrides)
    return row


def _session_row(**overrides: object) -> dict:
    """Return a complete Session dict."""
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "whatsapp_number": "+923001234567",
        "last_message_at": NOW,
        "expires_at": LATER,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(overrides)
    return row


# ═══════════════════════════════════════════════════════════════
# CATALOG REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestCatalogRepo:
    """Test CatalogRepository with mocked Supabase."""

    PATCH = "app.db.repositories.catalog_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        row = _catalog_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.get_by_id(row["id"], distributor_id=DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        mock_db = _mock_supabase(None)
        mock_db.execute = AsyncMock(return_value=MagicMock(data=None))
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.get_by_id(str(uuid4()), distributor_id=DIST_ID)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_active_catalog(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        rows = [_catalog_row(), _catalog_row(medicine_name="Brufen")]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.get_active_catalog(DIST_ID)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        row = _catalog_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            data = MagicMock()
            data.model_dump.return_value = {
                "distributor_id": DIST_ID,
                "medicine_name": "New Drug",
                "price_per_unit_paisas": 3000,
            }
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        row = _catalog_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            data = MagicMock()
            data.model_dump.return_value = {"medicine_name": "Updated Drug"}
            result = await repo.update(row["id"], data, distributor_id=DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_soft_delete(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        row = _catalog_row(is_active=False)
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.soft_delete(str(uuid4()), DIST_ID)
            assert result is True

    @pytest.mark.asyncio
    async def test_update_stock(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        row = _catalog_row(stock_quantity=50)
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.update_stock(row["id"], DIST_ID, 50)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_low_stock_items(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        rows = [_catalog_row(stock_quantity=3)]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.get_low_stock_items(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_search_medicines(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        rows = [_catalog_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CatalogRepository()
            result = await repo.search_medicines(DIST_ID, "panadol")
            assert len(result) >= 1



# ═══════════════════════════════════════════════════════════════
# CUSTOMER REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestCustomerRepo:
    """Test CustomerRepository with mocked Supabase."""

    PATCH = "app.db.repositories.customer_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            result = await repo.get_by_id(row["id"], distributor_id=DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_whatsapp_number(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            result = await repo.get_by_whatsapp_number(DIST_ID, "+923001234567")
            assert result is not None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            data = MagicMock()
            data.model_dump.return_value = {
                "distributor_id": DIST_ID,
                "whatsapp_number": "+923001234567",
                "name": "Test Customer",
                "shop_name": "Ali Pharmacy",
            }
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row(name="Updated")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            data = MagicMock()
            data.model_dump.return_value = {"name": "Updated"}
            result = await repo.update(row["id"], data, distributor_id=DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_active_customers(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        rows = [_customer_row(), _customer_row(name="Second")]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            result = await repo.get_active_customers(DIST_ID)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_by_name(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        rows = [_customer_row(name="Ali Pharmacy")]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            result = await repo.search_by_name(DIST_ID, "Ali")
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_block_customer(self) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row(is_blocked=True)
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerRepository()
            result = await repo.block_customer(row["id"], DIST_ID, "Spam")
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# ORDER REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestOrderRepo:
    """Test OrderRepository with mocked Supabase."""

    PATCH = "app.db.repositories.order_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.order_repo import OrderRepository

        row = _order_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderRepository()
            result = await repo.get_by_id(row["id"], distributor_id=DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.order_repo import OrderRepository

        row = _order_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderRepository()
            data = MagicMock()
            data.model_dump.return_value = {
                "distributor_id": DIST_ID,
                "order_number": "ORD-456",
                "customer_id": CUST_ID,
            }
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_order_number(self) -> None:
        from app.db.repositories.order_repo import OrderRepository

        row = _order_row(order_number="ORD-789")
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderRepository()
            result = await repo.get_by_order_number("ORD-789")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_customer_orders(self) -> None:
        from app.db.repositories.order_repo import OrderRepository

        rows = [_order_row(), _order_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderRepository()
            result = await repo.get_customer_orders(DIST_ID, CUST_ID)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_orders_by_status(self) -> None:
        from app.db.repositories.order_repo import OrderRepository

        rows = [_order_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderRepository()
            result = await repo.get_orders_by_status(DIST_ID, "pending")
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_recent_orders(self) -> None:
        from app.db.repositories.order_repo import OrderRepository

        rows = [_order_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderRepository()
            result = await repo.get_recent_orders(DIST_ID)
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# ORDER ITEM REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestOrderItemRepo:
    """Test OrderItemRepository with mocked Supabase."""

    PATCH = "app.db.repositories.order_item_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        row = _order_item_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderItemRepository()
            data = MagicMock()
            data.model_dump.return_value = {
                "order_id": str(uuid4()),
                "distributor_id": DIST_ID,
                "catalog_id": str(uuid4()),
                "medicine_name": "Panadol",
                "quantity_ordered": 10,
                "price_per_unit_paisas": 5000,
                "line_total_paisas": 50000,
            }
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_order(self) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        rows = [_order_item_row(), _order_item_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderItemRepository()
            result = await repo.get_by_order(str(uuid4()), DIST_ID)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_create_batch(self) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        rows = [_order_item_row(), _order_item_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = OrderItemRepository()
            item1 = MagicMock()
            item1.model_dump.return_value = {
                "order_id": str(uuid4()),
                "distributor_id": DIST_ID,
                "medicine_name": "Drug1",
                "quantity_ordered": 5,
                "price_per_unit_paisas": 3000,
                "line_total_paisas": 15000,
            }
            item2 = MagicMock()
            item2.model_dump.return_value = {
                "order_id": str(uuid4()),
                "distributor_id": DIST_ID,
                "medicine_name": "Drug2",
                "quantity_ordered": 3,
                "price_per_unit_paisas": 4000,
                "line_total_paisas": 12000,
            }
            result = await repo.create_batch([item1, item2])
            assert len(result) == 2


# ═══════════════════════════════════════════════════════════════
# SESSION REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestSessionRepo:
    """Test SessionRepository with mocked Supabase."""

    PATCH = "app.db.repositories.session_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = SessionRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = SessionRepository()
            data = MagicMock()
            data.model_dump.return_value = {
                "distributor_id": DIST_ID,
                "whatsapp_number": "+923001234567",
            }
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_number(self) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = SessionRepository()
            result = await repo.get_by_number(DIST_ID, "+923001234567")
            assert result is not None

    @pytest.mark.asyncio
    async def test_update_state(self) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row(current_state="ordering")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = SessionRepository()
            result = await repo.update_state(row["id"], "ordering")
            assert result is not None

    @pytest.mark.asyncio
    async def test_delete_session(self) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = SessionRepository()
            result = await repo.delete_session(str(uuid4()))
            assert result is True

    @pytest.mark.asyncio
    async def test_get_expired_sessions(self) -> None:
        from app.db.repositories.session_repo import SessionRepository

        rows = [_session_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = SessionRepository()
            result = await repo.get_expired_sessions()
            assert len(result) >= 1
