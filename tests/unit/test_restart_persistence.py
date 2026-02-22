"""Test that order context survives a simulated process restart.

Verifies the core contract: if the server restarts mid-order, the
customer can continue seamlessly because the context is persisted
to the ``sessions.pending_order_draft`` JSONB column after every
mutation.

Since we cannot actually kill/restart a live server in unit tests,
we simulate the flow:
1. Create a context, add items, save to a mock session repo.
2. Clear all in-memory references (simulating process death).
3. Re-load from the saved draft.
4. Assert that all state (items, pricing, flow_step) is intact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.constants import InputMethod, OrderFlowStep
from app.db.models.order_context import OrderContext, PricingSnapshot
from app.db.models.session import Session
from app.orders.context_manager import (
    add_item_to_context,
    cancel_order,
    context_to_display_string,
    create_empty_context,
    get_context_from_session,
    mark_bill_shown,
    mark_confirmed,
    remove_item_from_context,
    save_context_to_session,
    set_delivery,
    to_order_create_payload,
    update_item_quantity,
    validate_context,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════


def _make_session(draft: dict | None = None) -> Session:
    """Create a fake Session for testing."""
    now = datetime.now(timezone.utc)
    return Session(
        id=uuid4(),
        distributor_id=uuid4(),
        whatsapp_number="+923001234567",
        channel="A",
        current_state="order_item_collection",
        last_message_at=now,
        expires_at=now,
        created_at=now,
        updated_at=now,
        pending_order_draft=draft or {},
    )


# ═══════════════════════════════════════════════════════════════════
# RESTART PERSISTENCE TEST
# ═══════════════════════════════════════════════════════════════════


class TestProcessRestartPersistence:
    """Verify that order context survives a simulated process restart."""

    @pytest.mark.asyncio
    async def test_context_survives_restart(self):
        """Full round-trip: create → add items → save → reload → verify."""
        # ── Phase 1: Build order state ──────────────────────────

        ctx = create_empty_context()
        assert ctx.flow_step == OrderFlowStep.ITEM_COLLECTION
        assert len(ctx.items) == 0

        # Add two items
        ctx, line_id_1 = add_item_to_context(
            ctx,
            name_raw="paracetamol",
            name_matched="Paracetamol 500mg",
            name_display="Paracetamol 500mg (GSK)",
            unit="strip",
            quantity=10,
            price_per_unit_paisas=6500,
        )
        ctx, line_id_2 = add_item_to_context(
            ctx,
            name_raw="amoxil",
            name_matched="Amoxil 250mg Caps",
            name_display="Amoxil 250mg Caps",
            unit="box",
            quantity=2,
            price_per_unit_paisas=42000,
        )

        # Verify pricing is correct
        assert ctx.pricing_snapshot.subtotal_paisas == (10 * 6500) + (2 * 42000)
        assert ctx.pricing_snapshot.total_paisas == (10 * 6500) + (2 * 42000)

        # Set delivery
        ctx = set_delivery(
            ctx,
            address="Shop 5, Medical Lane, Lahore",
            zone_name="Lahore Central",
            delivery_charges_paisas=10000,
        )

        # Mark bill shown
        ctx = mark_bill_shown(ctx)
        assert ctx.flow_step == OrderFlowStep.BILL_PREVIEW
        assert ctx.bill_shown_count == 1

        # ── Phase 2: Save to mock session repo ─────────────────
        saved_draft: dict = {}

        mock_repo = AsyncMock()

        async def capture_draft(session_id: str, draft: dict) -> None:
            nonlocal saved_draft
            saved_draft = draft

        mock_repo.update_order_draft = capture_draft

        await save_context_to_session(
            ctx, str(uuid4()), mock_repo
        )

        # Verify something was saved
        assert saved_draft != {}
        assert "items" in saved_draft
        assert len(saved_draft["items"]) == 2

        # ── Phase 3: Simulate process death ─────────────────────
        # Delete all in-memory references
        original_order_id = str(ctx.session_order_id)
        original_total = ctx.pricing_snapshot.total_paisas
        del ctx

        # ── Phase 4: Reload from saved draft ────────────────────
        # Simulate a fresh process reading the session from DB
        restored_session = _make_session(draft=saved_draft)
        restored_ctx = get_context_from_session(restored_session)

        # ── Phase 5: Verify everything is intact ────────────────
        assert str(restored_ctx.session_order_id) == original_order_id
        assert restored_ctx.flow_step == OrderFlowStep.BILL_PREVIEW
        assert len(restored_ctx.items) == 2
        assert restored_ctx.items[0].medicine_name_raw == "paracetamol"
        assert restored_ctx.items[0].quantity_requested == 10
        assert restored_ctx.items[0].price_per_unit_paisas == 6500
        assert restored_ctx.items[1].medicine_name_raw == "amoxil"
        assert restored_ctx.items[1].quantity_requested == 2
        assert restored_ctx.pricing_snapshot.total_paisas == original_total
        assert restored_ctx.pricing_snapshot.delivery_charges_paisas == 10000
        assert restored_ctx.delivery.address == "Shop 5, Medical Lane, Lahore"
        assert restored_ctx.bill_shown_count == 1

    @pytest.mark.asyncio
    async def test_empty_session_creates_fresh_context(self):
        """Loading from an empty session.pending_order_draft returns fresh context."""
        session = _make_session(draft={})
        ctx = get_context_from_session(session)

        assert ctx.flow_step == OrderFlowStep.ITEM_COLLECTION
        assert len(ctx.items) == 0
        assert ctx.pricing_snapshot.total_paisas == 0

    @pytest.mark.asyncio
    async def test_corrupted_draft_returns_fresh_context(self):
        """Corrupted draft gracefully falls back to fresh context."""
        session = _make_session(draft={"invalid": "data", "items": "not_a_list"})
        ctx = get_context_from_session(session)

        # Should return fresh context rather than crash
        assert ctx.flow_step == OrderFlowStep.ITEM_COLLECTION
        assert isinstance(ctx.items, list)

    @pytest.mark.asyncio
    async def test_mid_order_modification_after_restart(self):
        """After restart, can continue modifying the restored order."""
        # Create and save
        ctx = create_empty_context()
        ctx, line_id = add_item_to_context(
            ctx,
            name_raw="brufen",
            name_matched="Brufen 400mg",
            name_display="Brufen 400mg",
            unit="strip",
            quantity=5,
            price_per_unit_paisas=4500,
        )

        draft = ctx.model_dump(mode="json")

        # Simulate restart
        del ctx
        restored_session = _make_session(draft=draft)
        restored_ctx = get_context_from_session(restored_session)

        # Modify after restart
        restored_ctx = update_item_quantity(restored_ctx, line_id, 8)
        assert restored_ctx.items[0].quantity_requested == 8
        assert restored_ctx.items[0].line_subtotal_paisas == 8 * 4500

        # Add another item
        restored_ctx, new_line_id = add_item_to_context(
            restored_ctx,
            name_raw="flagyl",
            name_matched="Flagyl 400mg",
            name_display="Flagyl 400mg",
            unit="strip",
            quantity=3,
            price_per_unit_paisas=3000,
        )
        assert len(restored_ctx.items) == 2
        assert restored_ctx.pricing_snapshot.subtotal_paisas == (8 * 4500) + (3 * 3000)


# ═══════════════════════════════════════════════════════════════════
# CONTEXT MANAGER UNIT TESTS
# ═══════════════════════════════════════════════════════════════════


class TestCreateEmptyContext:
    def test_fresh_context(self):
        ctx = create_empty_context()
        assert ctx.flow_step == OrderFlowStep.ITEM_COLLECTION
        assert len(ctx.items) == 0
        assert ctx.pricing_snapshot.total_paisas == 0
        assert ctx.order_cancelled is False

    def test_with_custom_id(self):
        custom_id = str(uuid4())
        ctx = create_empty_context(session_order_id=custom_id)
        assert str(ctx.session_order_id) == custom_id


class TestAddItemToContext:
    def test_basic_add(self):
        ctx = create_empty_context()
        ctx, line_id = add_item_to_context(
            ctx,
            name_raw="panadol",
            name_matched="Panadol 500mg",
            quantity=5,
            price_per_unit_paisas=3000,
        )
        assert len(ctx.items) == 1
        assert ctx.items[0].medicine_name_raw == "panadol"
        assert ctx.items[0].quantity_requested == 5
        assert ctx.items[0].line_subtotal_paisas == 15000
        assert ctx.items[0].line_total_paisas == 15000
        assert ctx.pricing_snapshot.subtotal_paisas == 15000
        assert ctx.pricing_snapshot.total_paisas == 15000

    def test_multiple_items(self):
        ctx = create_empty_context()
        ctx, _ = add_item_to_context(
            ctx, name_raw="a", quantity=2, price_per_unit_paisas=1000,
        )
        ctx, _ = add_item_to_context(
            ctx, name_raw="b", quantity=3, price_per_unit_paisas=2000,
        )
        assert len(ctx.items) == 2
        assert ctx.pricing_snapshot.subtotal_paisas == (2 * 1000) + (3 * 2000)


class TestRemoveItemFromContext:
    def test_cancel_item(self):
        ctx = create_empty_context()
        ctx, line_id = add_item_to_context(
            ctx, name_raw="test", quantity=1, price_per_unit_paisas=5000,
        )
        assert ctx.pricing_snapshot.subtotal_paisas == 5000

        ctx = remove_item_from_context(ctx, line_id)
        assert ctx.items[0].cancelled is True
        assert ctx.pricing_snapshot.subtotal_paisas == 0

    def test_remove_nonexistent(self):
        ctx = create_empty_context()
        ctx = remove_item_from_context(ctx, str(uuid4()))
        assert len(ctx.items) == 0


class TestUpdateItemQuantity:
    def test_update(self):
        ctx = create_empty_context()
        ctx, line_id = add_item_to_context(
            ctx, name_raw="test", quantity=5, price_per_unit_paisas=1000,
        )
        ctx = update_item_quantity(ctx, line_id, 10)
        assert ctx.items[0].quantity_requested == 10
        assert ctx.items[0].line_subtotal_paisas == 10000
        assert ctx.pricing_snapshot.subtotal_paisas == 10000


class TestSetDelivery:
    def test_set_delivery(self):
        ctx = create_empty_context()
        ctx, _ = add_item_to_context(
            ctx, name_raw="test", quantity=1, price_per_unit_paisas=10000,
        )
        ctx = set_delivery(ctx, address="Lahore", delivery_charges_paisas=5000)
        assert ctx.delivery.address == "Lahore"
        assert ctx.pricing_snapshot.delivery_charges_paisas == 5000
        assert ctx.pricing_snapshot.total_paisas == 10000 + 5000


class TestValidateContext:
    def test_valid(self):
        ctx = create_empty_context()
        ctx, _ = add_item_to_context(
            ctx, name_raw="test", quantity=5, price_per_unit_paisas=1000,
        )
        errors = validate_context(ctx)
        assert errors == []

    def test_invalid_quantity(self):
        ctx = create_empty_context()
        ctx, line_id = add_item_to_context(
            ctx, name_raw="test", quantity=1, price_per_unit_paisas=1000,
        )
        # Force bad quantity
        ctx.items[0].quantity_requested = 0
        errors = validate_context(ctx)
        assert any("quantity must be positive" in e for e in errors)


class TestCancelOrder:
    def test_cancel(self):
        ctx = create_empty_context()
        ctx = cancel_order(ctx, "customer changed mind")
        assert ctx.order_cancelled is True
        assert ctx.cancellation_reason == "customer changed mind"
        assert ctx.flow_step == OrderFlowStep.COMPLETE


class TestToOrderCreatePayload:
    def test_payload(self):
        ctx = create_empty_context()
        ctx, _ = add_item_to_context(
            ctx,
            name_raw="para",
            name_matched="Paracetamol",
            name_display="Paracetamol 500mg",
            quantity=5,
            price_per_unit_paisas=1000,
        )
        payload = to_order_create_payload(ctx)
        assert "order" in payload
        assert "items" in payload
        assert len(payload["items"]) == 1
        assert payload["order"]["total_paisas"] == 5000


class TestContextToDisplayString:
    def test_empty_order(self):
        ctx = create_empty_context()
        result = context_to_display_string(ctx)
        assert "khaali" in result

    def test_with_items(self):
        ctx = create_empty_context()
        ctx, _ = add_item_to_context(
            ctx,
            name_raw="para",
            name_matched="Paracetamol",
            name_display="Paracetamol 500mg",
            quantity=10,
            unit="strip",
            price_per_unit_paisas=6500,
        )
        result = context_to_display_string(ctx)
        assert "Paracetamol 500mg" in result
        assert "PKR" in result
        assert "650" in result  # 65000 paisas = PKR 650

    def test_english(self):
        ctx = create_empty_context()
        result = context_to_display_string(ctx, language="english")
        assert "empty" in result
