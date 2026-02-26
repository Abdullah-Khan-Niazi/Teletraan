"""Tests for uncovered repo methods: session, order, order_item, customer.

Each repo method follows the same pattern:
1. get_db_client() → mock client
2. client.table(TABLE).operation(...).eq(...).execute() → AsyncMock
3. Model.model_validate(result.data) for return

We mock the full chain and validate both success and error paths.

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import DatabaseError, NotFoundError

_NOW = datetime.now(tz=timezone.utc).isoformat()
_UUID1 = str(uuid4())
_UUID2 = str(uuid4())
_DIST_ID = str(uuid4())
_CUST_ID = str(uuid4())

# ── Fixtures for row dicts ──────────────────────────────────────


def _session_row(**kw: object) -> dict:
    base = {
        "id": _UUID1,
        "distributor_id": _DIST_ID,
        "whatsapp_number": "+923001234567",
        "customer_id": _CUST_ID,
        "channel": "A",
        "current_state": "idle",
        "previous_state": None,
        "state_data": {},
        "conversation_history": [],
        "pending_order_draft": {},
        "language": "roman_urdu",
        "retry_count": 0,
        "handoff_mode": False,
        "last_message_at": _NOW,
        "expires_at": _NOW,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(kw)
    return base


def _order_row(**kw: object) -> dict:
    base = {
        "id": _UUID1,
        "order_number": "ORD-2025-0001",
        "distributor_id": _DIST_ID,
        "customer_id": _CUST_ID,
        "status": "pending",
        "subtotal_paisas": 100_000,
        "discount_paisas": 0,
        "delivery_charges_paisas": 0,
        "total_paisas": 100_000,
        "payment_status": "unpaid",
        "payment_method": None,
        "delivery_address": None,
        "delivery_zone_id": None,
        "estimated_delivery_at": None,
        "dispatched_at": None,
        "delivered_at": None,
        "notes": None,
        "internal_notes": None,
        "discount_requests": [],
        "discount_approval_status": "not_requested",
        "source": "whatsapp",
        "is_quick_reorder": False,
        "source_order_id": None,
        "whatsapp_logged_at": None,
        "excel_logged_at": None,
        "order_context_snapshot": {},
        "metadata": {},
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(kw)
    return base


def _customer_row(**kw: object) -> dict:
    base = {
        "id": _CUST_ID,
        "distributor_id": _DIST_ID,
        "whatsapp_number": "+923001234567",
        "name": "Ali Medical",
        "shop_name": "Ali Store",
        "address": "Lahore",
        "city": "Lahore",
        "delivery_zone_id": None,
        "language_preference": "roman_urdu",
        "is_verified": True,
        "credit_limit_paisas": 0,
        "outstanding_balance_paisas": 0,
        "is_active": True,
        "is_blocked": False,
        "blocked_reason": None,
        "blocked_at": None,
        "last_order_at": None,
        "total_orders": 5,
        "total_spend_paisas": 500_000,
        "tags": [],
        "notes": None,
        "metadata": {},
        "registered_at": _NOW,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(kw)
    return base


def _order_item_row(**kw: object) -> dict:
    base = {
        "id": str(uuid4()),
        "order_id": _UUID1,
        "distributor_id": _DIST_ID,
        "catalog_id": None,
        "medicine_name_raw": "panadol",
        "medicine_name": "Panadol",
        "unit": "strip",
        "quantity_ordered": 10,
        "quantity_fulfilled": 0,
        "price_per_unit_paisas": 5000,
        "line_total_paisas": 50000,
        "discount_paisas": 0,
        "bonus_units_given": 0,
        "is_out_of_stock_order": False,
        "is_unlisted_item": False,
        "input_method": None,
        "fuzzy_match_score": None,
        "notes": None,
        "created_at": _NOW,
    }
    base.update(kw)
    return base


# ── Helper to build mock table chain ────────────────────────────


def _chain(**execute_kw: object) -> MagicMock:
    """Build a fluent mock chain for Supabase table operations."""
    tbl = MagicMock()
    for attr in (
        "select", "insert", "update", "delete",
        "eq", "gte", "lt", "lte", "neq", "not_",
        "order", "limit", "range", "maybe_single",
    ):
        setattr(tbl, attr, MagicMock(return_value=tbl))
    tbl.execute = AsyncMock(**execute_kw)
    return tbl


# ═══════════════════════════════════════════════════════════════════════════
# SessionRepository
# ═══════════════════════════════════════════════════════════════════════════

_SR = "app.db.repositories.session_repo.get_db_client"


class TestSessionRepoUpdate:

    @patch(_SR)
    async def test_update_success(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row(current_state="ordering")
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        data = MagicMock()
        data.model_dump.return_value = {"current_state": "ordering"}
        result = await repo.update(_UUID1, data)
        assert result.current_state == "ordering"

    @patch(_SR)
    async def test_update_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        data = MagicMock()
        data.model_dump.return_value = {"current_state": "x"}
        with pytest.raises(NotFoundError):
            await repo.update(_UUID1, data)

    @patch(_SR)
    async def test_update_empty_payload(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        # Empty payload → falls through to get_by_id_or_raise
        row = _session_row()
        tbl = _chain(return_value=MagicMock(data=row))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        data = MagicMock()
        data.model_dump.return_value = {}
        result = await repo.update(_UUID1, data)
        assert result is not None


class TestSessionRepoOrderDraft:

    @patch(_SR)
    async def test_update_order_draft(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row(pending_order_draft={"items": ["Panadol"]})
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        result = await repo.update_order_draft(_UUID1, {"items": ["Panadol"]})
        assert result.pending_order_draft == {"items": ["Panadol"]}

    @patch(_SR)
    async def test_update_order_draft_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        with pytest.raises(NotFoundError):
            await repo.update_order_draft(_UUID1, {"items": []})

    @patch(_SR)
    async def test_update_order_draft_db_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        with pytest.raises(DatabaseError):
            await repo.update_order_draft(_UUID1, {})

    @patch(_SR)
    async def test_clear_order_draft(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        row = _session_row(pending_order_draft={})
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        result = await repo.clear_order_draft(_UUID1)
        assert result.pending_order_draft == {}

    @patch(_SR)
    async def test_clear_order_draft_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        with pytest.raises(NotFoundError):
            await repo.clear_order_draft(_UUID1)

    @patch(_SR)
    async def test_clear_order_draft_db_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        with pytest.raises(DatabaseError):
            await repo.clear_order_draft(_UUID1)


class TestSessionRepoMisc:

    @patch(_SR)
    async def test_get_expired_sessions_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        with pytest.raises(DatabaseError):
            await repo.get_expired_sessions()

    @patch(_SR)
    async def test_delete_session_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.session_repo import SessionRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = SessionRepository()
        with pytest.raises(DatabaseError):
            await repo.delete_session(_UUID1)


# ═══════════════════════════════════════════════════════════════════════════
# OrderRepository
# ═══════════════════════════════════════════════════════════════════════════

_OR = "app.db.repositories.order_repo.get_db_client"


class TestOrderRepoUpdate:

    @patch(_OR)
    async def test_update_success(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        row = _order_row(status="confirmed")
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        data = MagicMock()
        data.model_dump.return_value = {"status": "confirmed"}
        result = await repo.update(_UUID1, data, distributor_id=_DIST_ID)
        assert result.status.value == "confirmed"

    @patch(_OR)
    async def test_update_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        data = MagicMock()
        data.model_dump.return_value = {"status": "confirmed"}
        with pytest.raises(NotFoundError):
            await repo.update(_UUID1, data, distributor_id=_DIST_ID)

    @patch(_OR)
    async def test_update_db_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(side_effect=RuntimeError("DB crash"))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        data = MagicMock()
        data.model_dump.return_value = {"status": "confirmed"}
        with pytest.raises(DatabaseError):
            await repo.update(_UUID1, data, distributor_id=_DIST_ID)


class TestOrderRepoDomainMethods:

    @patch(_OR)
    async def test_get_by_order_number(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        row = _order_row()
        tbl = _chain(return_value=MagicMock(data=row))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        result = await repo.get_by_order_number("ORD-2025-0001")
        assert result is not None

    @patch(_OR)
    async def test_get_customer_orders(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(return_value=MagicMock(data=[_order_row()]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        result = await repo.get_customer_orders(_DIST_ID, _CUST_ID)
        assert len(result) == 1

    @patch(_OR)
    async def test_get_customer_orders_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        with pytest.raises(DatabaseError):
            await repo.get_customer_orders(_DIST_ID, _CUST_ID)

    @patch(_OR)
    async def test_get_orders_by_status(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(return_value=MagicMock(data=[_order_row()]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        result = await repo.get_orders_by_status(_DIST_ID, "pending")
        assert len(result) == 1

    @patch(_OR)
    async def test_get_orders_by_status_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        with pytest.raises(DatabaseError):
            await repo.get_orders_by_status(_DIST_ID, "pending")

    @patch(_OR)
    async def test_get_recent_orders(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(return_value=MagicMock(data=[_order_row()]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        result = await repo.get_recent_orders(_DIST_ID)
        assert len(result) == 1

    @patch(_OR)
    async def test_get_recent_orders_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        with pytest.raises(DatabaseError):
            await repo.get_recent_orders(_DIST_ID)

    @patch(_OR)
    async def test_get_order_with_items(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        order_row = _order_row()
        item_row = _order_item_row()

        # First call: get_by_id_or_raise → select.eq.maybe_single.execute
        # Second call: items_result → select.eq.eq.execute
        call_count = 0

        async def execute_side_effect() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(data=order_row)
            return MagicMock(data=[item_row])

        tbl = _chain()
        tbl.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        order, items = await repo.get_order_with_items(_UUID1, _DIST_ID)
        assert order.id is not None
        assert len(items) == 1

    @patch(_OR)
    async def test_get_order_with_items_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_repo import OrderRepository

        tbl = _chain(return_value=MagicMock(data=None))
        mock_db.return_value.table.return_value = tbl

        repo = OrderRepository()
        with pytest.raises(NotFoundError):
            await repo.get_order_with_items(_UUID1, _DIST_ID)


# ═══════════════════════════════════════════════════════════════════════════
# OrderItemRepository
# ═══════════════════════════════════════════════════════════════════════════

_OIR = "app.db.repositories.order_item_repo.get_db_client"


class TestOrderItemRepo:

    @patch(_OIR)
    async def test_get_by_id(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        row = _order_item_row()
        tbl = _chain(return_value=MagicMock(data=row))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        result = await repo.get_by_id(row["id"], distributor_id=_DIST_ID)
        assert result is not None

    @patch(_OIR)
    async def test_get_by_id_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        tbl = _chain(return_value=MagicMock(data=None))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        result = await repo.get_by_id("missing", distributor_id=_DIST_ID)
        assert result is None

    @patch(_OIR)
    async def test_get_by_order(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        tbl = _chain(return_value=MagicMock(data=[_order_item_row()]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        result = await repo.get_by_order(_UUID1, _DIST_ID)
        assert len(result) == 1

    @patch(_OIR)
    async def test_get_by_order_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        with pytest.raises(DatabaseError):
            await repo.get_by_order(_UUID1, _DIST_ID)

    @patch(_OIR)
    async def test_create_batch_empty(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        repo = OrderItemRepository()
        result = await repo.create_batch([])
        assert result == []

    @patch(_OIR)
    async def test_update_fulfillment(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        row = _order_item_row(quantity_fulfilled=5)
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        result = await repo.update_fulfillment(row["id"], 5)
        assert result.quantity_fulfilled == 5

    @patch(_OIR)
    async def test_update_fulfillment_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        with pytest.raises(NotFoundError):
            await repo.update_fulfillment("missing", 5)

    @patch(_OIR)
    async def test_update_fulfillment_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.order_item_repo import OrderItemRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = OrderItemRepository()
        with pytest.raises(DatabaseError):
            await repo.update_fulfillment("x", 5)


# ═══════════════════════════════════════════════════════════════════════════
# CustomerRepository
# ═══════════════════════════════════════════════════════════════════════════

_CR = "app.db.repositories.customer_repo.get_db_client"


class TestCustomerRepoUpdate:

    @patch(_CR)
    async def test_update_order_stats(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        # First call: get_by_id_or_raise → returns current customer
        # Second call: update stats
        cust_row = _customer_row(total_orders=5, total_spend_paisas=500_000)
        updated_row = _customer_row(total_orders=6, total_spend_paisas=600_000)

        call_count = 0

        async def execute_side_effect() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(data=cust_row)
            return MagicMock(data=[updated_row])

        tbl = _chain()
        tbl.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        # update_order_stats returns None; just verify no error
        await repo.update_order_stats(_CUST_ID, _DIST_ID, 100_000)

    @patch(_CR)
    async def test_update_order_stats_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(DatabaseError):
            await repo.update_order_stats(_CUST_ID, _DIST_ID, 100_000)

    @patch(_CR)
    async def test_block_customer(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row(is_blocked=True, blocked_reason="Late payments")
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        result = await repo.block_customer(_CUST_ID, _DIST_ID, "Late payments")
        assert result.is_blocked is True

    @patch(_CR)
    async def test_block_customer_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(NotFoundError):
            await repo.block_customer("missing", _DIST_ID, "reason")

    @patch(_CR)
    async def test_unblock_customer(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        row = _customer_row(is_blocked=False, blocked_reason=None)
        tbl = _chain(return_value=MagicMock(data=[row]))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        result = await repo.unblock_customer(_CUST_ID, _DIST_ID)
        assert result.is_blocked is False

    @patch(_CR)
    async def test_unblock_customer_not_found(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(return_value=MagicMock(data=[]))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(NotFoundError):
            await repo.unblock_customer("missing", _DIST_ID)

    @patch(_CR)
    async def test_unblock_customer_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(DatabaseError):
            await repo.unblock_customer(_CUST_ID, _DIST_ID)


class TestCustomerRepoQueries:

    @patch(_CR)
    async def test_get_active_customers_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(DatabaseError):
            await repo.get_active_customers(_DIST_ID)

    @patch(_CR)
    async def test_search_by_name_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(DatabaseError):
            await repo.search_by_name(_DIST_ID, "Ali")

    @patch(_CR)
    async def test_get_by_whatsapp_number_error(self, mock_db: MagicMock) -> None:
        from app.db.repositories.customer_repo import CustomerRepository

        tbl = _chain(side_effect=RuntimeError("DB down"))
        mock_db.return_value.table.return_value = tbl

        repo = CustomerRepository()
        with pytest.raises(DatabaseError):
            await repo.get_by_whatsapp_number(_DIST_ID, "+923001234567")
