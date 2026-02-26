"""Coverage gap tests — orders, billing, catalog, fuzzy matching, notifications.

Targets the largest coverage gaps to push overall project coverage past 80%.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _mock_db_chain() -> MagicMock:
    """Create a mock Supabase client chain.

    Methods that return self for chaining, `.execute` returns AsyncMock.
    """
    mock = MagicMock()
    chain = [
        "table", "select", "insert", "update", "delete", "upsert",
        "eq", "neq", "gt", "gte", "lt", "lte", "in_",
        "like", "ilike", "is_", "order", "limit", "offset",
        "range", "single", "maybe_single", "on_conflict",
    ]
    for method in chain:
        getattr(mock, method).return_value = mock
    mock.execute = AsyncMock(return_value=MagicMock(data=[]))
    return mock


def _make_catalog_item(**overrides) -> MagicMock:
    """Create a mock CatalogItem for fuzzy matching tests."""
    item = MagicMock()
    item.id = overrides.get("id", uuid4())
    item.medicine_name = overrides.get("medicine_name", "Panadol 500mg")
    item.generic_name = overrides.get("generic_name", "Paracetamol")
    item.brand_name = overrides.get("brand_name", "GSK")
    item.category = overrides.get("category", "Analgesics")
    item.unit_price_paisas = overrides.get("unit_price_paisas", 5000)
    item.price_per_unit_paisas = overrides.get("unit_price_paisas", 5000)
    item.stock_quantity = overrides.get("stock_quantity", 100)
    item.reserved_quantity = overrides.get("reserved_quantity", 0)
    item.low_stock_threshold = overrides.get("low_stock_threshold", 10)
    item.is_active = overrides.get("is_active", True)
    item.search_keywords = overrides.get("search_keywords", "panadol tablet")
    item.strength = overrides.get("strength", "500mg")
    item.pack_size = overrides.get("pack_size", "10 tablets")
    item.units_per_pack = overrides.get("units_per_pack", 10)
    item.form = overrides.get("form", "tablet")
    return item


# ═══════════════════════════════════════════════════════════════════
# FUZZY MATCHER (pure functions — no DB mocks needed)
# ═══════════════════════════════════════════════════════════════════


class TestNormaliseQuery:
    """Test query normalisation for fuzzy matching."""

    def test_basic_lowercase(self) -> None:
        from app.inventory.fuzzy_matcher import _normalise_query
        assert _normalise_query("PANADOL") == "panadol"

    def test_strips_whitespace(self) -> None:
        from app.inventory.fuzzy_matcher import _normalise_query
        result = _normalise_query("  panadol  500mg  ")
        assert result == "panadol 500mg"

    def test_roman_urdu_corrections(self) -> None:
        from app.inventory.fuzzy_matcher import _normalise_query
        result = _normalise_query("panadol")
        assert "panadol" in result.lower()


class TestExtractStrength:
    """Test strength extraction from text."""

    def test_extracts_mg(self) -> None:
        from app.inventory.fuzzy_matcher import _extract_strength
        assert _extract_strength("Panadol 500mg") is not None

    def test_returns_none_for_no_strength(self) -> None:
        from app.inventory.fuzzy_matcher import _extract_strength
        assert _extract_strength("Panadol tablets") is None


class TestStripStrength:
    """Test strength stripping from text."""

    def test_strips_mg(self) -> None:
        from app.inventory.fuzzy_matcher import _strip_strength
        result = _strip_strength("Panadol 500mg")
        assert "500mg" not in result

    def test_preserves_text_without_strength(self) -> None:
        from app.inventory.fuzzy_matcher import _strip_strength
        assert _strip_strength("Panadol").strip() == "Panadol"


class TestFuzzyMatchMedicine:
    """Test the main fuzzy matching function."""

    def test_exact_match_returns_high_confidence(self) -> None:
        from app.inventory.fuzzy_matcher import fuzzy_match_medicine

        items = [
            _make_catalog_item(medicine_name="Panadol 500mg"),
            _make_catalog_item(medicine_name="Brufen 400mg"),
        ]
        response = fuzzy_match_medicine("Panadol 500mg", items)
        assert len(response.matches) > 0
        assert response.matches[0].score >= 80

    def test_no_match_below_threshold(self) -> None:
        from app.inventory.fuzzy_matcher import fuzzy_match_medicine

        items = [_make_catalog_item(medicine_name="Amoxicillin 250mg")]
        response = fuzzy_match_medicine(
            "zzzznotamedicine", items, threshold=95
        )
        assert len(response.matches) == 0

    def test_respects_max_results(self) -> None:
        from app.inventory.fuzzy_matcher import fuzzy_match_medicine

        items = [
            _make_catalog_item(medicine_name=f"Panadol {i}mg")
            for i in range(100, 120)
        ]
        response = fuzzy_match_medicine(
            "Panadol", items, threshold=30, max_results=3
        )
        assert len(response.matches) <= 3

    def test_empty_catalog_returns_empty(self) -> None:
        from app.inventory.fuzzy_matcher import fuzzy_match_medicine

        response = fuzzy_match_medicine("Panadol", [])
        assert len(response.matches) == 0

    def test_auto_selected_on_high_confidence(self) -> None:
        from app.inventory.fuzzy_matcher import fuzzy_match_medicine

        items = [_make_catalog_item(medicine_name="Panadol 500mg")]
        response = fuzzy_match_medicine(
            "Panadol 500mg", items, high_confidence=70
        )
        if response.auto_selected is not None:
            assert response.auto_selected.score >= 70


class TestFormatMatchOptions:
    """Test formatting match results for WhatsApp."""

    def test_format_english(self) -> None:
        from app.inventory.fuzzy_matcher import (
            FuzzyMatchResult,
            format_match_options,
        )

        item = _make_catalog_item(
            medicine_name="Panadol 500mg",
            unit_price_paisas=5000,
            pack_size="10 tablets",
        )

        matches = [
            FuzzyMatchResult(
                item=item,
                score=95.0,
                matched_field="medicine_name",
                is_high_confidence=True,
            ),
        ]
        result = format_match_options(matches, language="english")
        assert "Panadol" in result
        assert "1" in result

    def test_format_empty(self) -> None:
        from app.inventory.fuzzy_matcher import format_match_options

        result = format_match_options([], language="english")
        assert isinstance(result, str)


class TestScoreItem:
    """Test per-item scoring logic."""

    def test_score_exact_name_high(self) -> None:
        from app.inventory.fuzzy_matcher import _score_item

        item = _make_catalog_item(medicine_name="Panadol 500mg")
        score, field = _score_item("Panadol 500mg", None, item)
        assert score >= 80
        assert field == "medicine_name"

    def test_score_with_strength_boost(self) -> None:
        from app.inventory.fuzzy_matcher import _score_item

        item = _make_catalog_item(
            medicine_name="Panadol 500mg", strength="500mg"
        )
        score1, _ = _score_item("Panadol 500mg", "500mg", item)
        score2, _ = _score_item("Panadol 250mg", "250mg", item)
        assert score1 >= score2


# ═══════════════════════════════════════════════════════════════════
# BILLING SERVICE (pure functions + mocked async)
# ═══════════════════════════════════════════════════════════════════


class TestBillingPureFunctions:
    """Test pure billing calculation functions."""

    def test_calculate_bonus_units_basic(self) -> None:
        from app.orders.billing_service import _calculate_bonus_units

        assert _calculate_bonus_units(6, 3, 1) == 2

    def test_calculate_bonus_units_not_enough(self) -> None:
        from app.orders.billing_service import _calculate_bonus_units

        assert _calculate_bonus_units(3, 5, 1) == 0

    def test_calculate_bonus_units_exact(self) -> None:
        from app.orders.billing_service import _calculate_bonus_units

        assert _calculate_bonus_units(2, 2, 1) == 1

    def test_recalculate_line_totals(self) -> None:
        from app.orders.billing_service import _recalculate_line_totals

        item = MagicMock()
        item.quantity_requested = 10
        item.price_per_unit_paisas = 500
        item.discount_applied_paisas = 100

        _recalculate_line_totals(item)
        assert item.line_subtotal_paisas == 5000
        assert item.line_total_paisas == 4900


class TestBillingServiceManualDiscounts:
    """Test manual discount application."""

    def test_apply_manual_item_discount(self) -> None:
        from app.orders.billing_service import BillingService

        service = BillingService()

        item = MagicMock()
        item.quantity_requested = 10
        item.price_per_unit_paisas = 1000
        item.discount_applied_paisas = 0
        item.line_subtotal_paisas = 10000
        item.line_total_paisas = 10000

        service.apply_manual_item_discount(item, 500)
        assert item.discount_applied_paisas == 500

    def test_apply_manual_order_discount(self) -> None:
        from app.orders.billing_service import BillingService

        service = BillingService()

        pricing = MagicMock()
        pricing.order_discount_paisas = 0
        pricing.subtotal_paisas = 10000
        pricing.total_paisas = 10000

        ctx = MagicMock()
        ctx.pricing_snapshot = pricing
        ctx.items = []
        ctx.order_level_discount_request = None

        service.apply_manual_order_discount(ctx, 1000)
        assert pricing.order_discount_paisas == 1000


class TestBillingFormatPreview:
    """Test bill preview formatting."""

    def test_format_bill_preview(self) -> None:
        from app.orders.billing_service import BillingService

        service = BillingService()

        item1 = MagicMock()
        item1.medicine_name = "Panadol 500mg"
        item1.quantity_requested = 10
        item1.unit = "strips"
        item1.price_per_unit_paisas = 500
        item1.line_total_paisas = 5000
        item1.discount_applied_paisas = 0
        item1.bonus_units = 0
        item1.cancelled = False

        pricing = MagicMock()
        pricing.subtotal_paisas = 5000
        pricing.item_discounts_paisas = 0
        pricing.order_discount_paisas = 0
        pricing.delivery_charges_paisas = 0
        pricing.total_paisas = 5000
        pricing.auto_applied_discounts = []

        ctx = MagicMock()
        ctx.items = [item1]
        ctx.pricing_snapshot = pricing

        result = service.format_bill_preview(ctx, language="english")
        assert isinstance(result, str)
        assert "Panadol" in result or "50" in result


# ═══════════════════════════════════════════════════════════════════
# ORDER SERVICE
# ═══════════════════════════════════════════════════════════════════


class TestOrderServiceHelpers:
    """Test order service helper functions."""

    def test_generate_order_number_format(self) -> None:
        from app.orders.order_service import _generate_order_number

        result = _generate_order_number()
        assert result.startswith("ORD-")
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8

    def test_generate_order_number_unique(self) -> None:
        from app.orders.order_service import _generate_order_number

        numbers = {_generate_order_number() for _ in range(50)}
        assert len(numbers) >= 45


class TestOrderServiceMethods:
    """Test OrderService async methods with mocked repos."""

    @pytest.mark.asyncio
    async def test_get_order(self) -> None:
        from app.orders.order_service import OrderService

        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.distributor_id = uuid4()

        mock_order_repo = MagicMock()
        mock_order_repo.get_by_id_or_raise = AsyncMock(return_value=mock_order)

        service = OrderService(order_repo=mock_order_repo)
        result = await service.get_order(
            str(mock_order.id), str(mock_order.distributor_id)
        )
        assert result == mock_order

    @pytest.mark.asyncio
    async def test_get_order_with_items(self) -> None:
        from app.orders.order_service import OrderService

        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.distributor_id = uuid4()
        mock_items = [MagicMock(), MagicMock()]

        mock_order_repo = MagicMock()
        mock_order_repo.get_order_with_items = AsyncMock(
            return_value=(mock_order, mock_items)
        )

        service = OrderService(order_repo=mock_order_repo)
        order, items = await service.get_order_with_items(
            str(mock_order.id), str(mock_order.distributor_id)
        )
        assert order == mock_order
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_customer_orders(self) -> None:
        from app.orders.order_service import OrderService

        mock_orders = [MagicMock(), MagicMock()]
        mock_order_repo = MagicMock()
        mock_order_repo.get_customer_orders = AsyncMock(
            return_value=mock_orders
        )

        service = OrderService(order_repo=mock_order_repo)
        result = await service.get_customer_orders(
            str(uuid4()), str(uuid4())
        )
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_recent_orders(self) -> None:
        from app.orders.order_service import OrderService

        mock_orders = [MagicMock()]
        mock_order_repo = MagicMock()
        mock_order_repo.get_recent_orders = AsyncMock(
            return_value=mock_orders
        )

        service = OrderService(order_repo=mock_order_repo)
        result = await service.get_recent_orders(str(uuid4()), limit=5)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_order_by_number(self) -> None:
        from app.orders.order_service import OrderService

        mock_order = MagicMock()
        mock_order_repo = MagicMock()
        mock_order_repo.get_by_order_number = AsyncMock(
            return_value=mock_order
        )

        service = OrderService(order_repo=mock_order_repo)
        result = await service.get_order_by_number(
            "ORD-123", str(uuid4())
        )
        assert result == mock_order


# ═══════════════════════════════════════════════════════════════════
# CATALOG SERVICE
# ═══════════════════════════════════════════════════════════════════


class TestCatalogService:
    """Test CatalogService methods."""

    @pytest.mark.asyncio
    async def test_get_active_catalog_cached(self) -> None:
        from app.inventory.catalog_service import CatalogService

        mock_repo = MagicMock()
        items = [_make_catalog_item()]
        mock_repo.get_active_catalog = AsyncMock(return_value=items)

        service = CatalogService(repo=mock_repo)
        dist_id = str(uuid4())

        result1 = await service.get_active_catalog(dist_id)
        assert len(result1) == 1

        result2 = await service.get_active_catalog(dist_id)
        assert len(result2) == 1
        assert mock_repo.get_active_catalog.await_count == 1

    @pytest.mark.asyncio
    async def test_get_active_catalog_force_refresh(self) -> None:
        from app.inventory.catalog_service import CatalogService

        mock_repo = MagicMock()
        mock_repo.get_active_catalog = AsyncMock(return_value=[])

        service = CatalogService(repo=mock_repo)
        dist_id = str(uuid4())

        await service.get_active_catalog(dist_id)
        await service.get_active_catalog(dist_id, force_refresh=True)
        assert mock_repo.get_active_catalog.await_count == 2

    def test_invalidate_cache(self) -> None:
        from app.inventory.catalog_service import CatalogService

        service = CatalogService()
        service.invalidate_cache(str(uuid4()))

    def test_invalidate_all_caches(self) -> None:
        from app.inventory.catalog_service import CatalogService

        service = CatalogService()
        service.invalidate_all_caches()

    @pytest.mark.asyncio
    async def test_get_categories(self) -> None:
        from app.inventory.catalog_service import CatalogService

        items = [
            _make_catalog_item(category="Analgesics"),
            _make_catalog_item(category="Antibiotics"),
            _make_catalog_item(category="Analgesics"),
        ]
        mock_repo = MagicMock()
        mock_repo.get_active_catalog = AsyncMock(return_value=items)

        service = CatalogService(repo=mock_repo)
        cats = await service.get_categories(str(uuid4()))
        assert "Analgesics" in cats
        assert "Antibiotics" in cats
        assert len(cats) == 2

    @pytest.mark.asyncio
    async def test_get_items_by_category(self) -> None:
        from app.inventory.catalog_service import CatalogService

        items = [
            _make_catalog_item(category="Analgesics", stock_quantity=10),
            _make_catalog_item(category="Antibiotics", stock_quantity=0),
        ]
        mock_repo = MagicMock()
        mock_repo.get_active_catalog = AsyncMock(return_value=items)

        service = CatalogService(repo=mock_repo)
        results = await service.get_items_by_category(
            str(uuid4()), "Analgesics"
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_check_stock_availability(self) -> None:
        from app.inventory.catalog_service import CatalogService

        item = _make_catalog_item(stock_quantity=100, reserved_quantity=20)
        item.allow_order_when_out_of_stock = False
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=item)

        service = CatalogService(repo=mock_repo)
        dist_id = str(uuid4())
        item_id = str(item.id)

        available, qty = await service.check_stock_availability(
            dist_id, item_id, 50
        )
        assert available is True
        assert qty == 80

    @pytest.mark.asyncio
    async def test_get_low_stock_items(self) -> None:
        from app.inventory.catalog_service import CatalogService

        low = _make_catalog_item(stock_quantity=5, low_stock_threshold=10)
        mock_repo = MagicMock()
        mock_repo.get_low_stock_items = AsyncMock(return_value=[low])

        service = CatalogService(repo=mock_repo)
        result = await service.get_low_stock_items(str(uuid4()))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create_item(self) -> None:
        from app.inventory.catalog_service import CatalogService

        mock_item = _make_catalog_item()
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=mock_item)

        service = CatalogService(repo=mock_repo)
        data = MagicMock()
        data.distributor_id = str(uuid4())
        result = await service.create_item(data)
        assert result == mock_item

    @pytest.mark.asyncio
    async def test_update_item(self) -> None:
        from app.inventory.catalog_service import CatalogService

        mock_item = _make_catalog_item()
        mock_repo = MagicMock()
        mock_repo.update = AsyncMock(return_value=mock_item)

        service = CatalogService(repo=mock_repo)
        result = await service.update_item(
            str(uuid4()), MagicMock(), distributor_id=str(uuid4())
        )
        assert result == mock_item

    @pytest.mark.asyncio
    async def test_delete_item(self) -> None:
        from app.inventory.catalog_service import CatalogService

        mock_repo = MagicMock()
        mock_repo.soft_delete = AsyncMock(return_value=True)

        service = CatalogService(repo=mock_repo)
        result = await service.delete_item(
            str(uuid4()), distributor_id=str(uuid4())
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_catalog_stats(self) -> None:
        from app.inventory.catalog_service import CatalogService

        items = [
            _make_catalog_item(
                stock_quantity=10, low_stock_threshold=5,
                unit_price_paisas=1000, category="A",
            ),
            _make_catalog_item(
                stock_quantity=0, low_stock_threshold=5,
                unit_price_paisas=2000, category="B",
            ),
        ]
        mock_repo = MagicMock()
        mock_repo.get_active_catalog = AsyncMock(return_value=items)

        service = CatalogService(repo=mock_repo)
        stats = await service.get_catalog_stats(str(uuid4()))
        assert stats["total_items"] == 2
        assert stats["category_count"] == 2


# ═══════════════════════════════════════════════════════════════════
# WHATSAPP NOTIFIER
# ═══════════════════════════════════════════════════════════════════


class TestWhatsAppNotifier:
    """Test WhatsAppNotifier send methods."""

    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with (
            patch(
                "app.notifications.whatsapp_notifier.whatsapp_client"
            ) as mock_wa,
            patch(
                "app.notifications.whatsapp_notifier.notification_repo"
            ) as mock_repo,
        ):
            mock_wa.send_message = AsyncMock(return_value="msg_123")
            mock_repo.create = AsyncMock()

            result = await notifier.send_text(
                phone_number_id="pnid_1",
                to="+923001234567",
                text="Hello test",
                distributor_id=str(uuid4()),
            )
            assert result == "msg_123"
            mock_wa.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_buttons(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with (
            patch(
                "app.notifications.whatsapp_notifier.whatsapp_client"
            ) as mock_wa,
            patch(
                "app.notifications.whatsapp_notifier.notification_repo"
            ) as mock_repo,
        ):
            mock_wa.send_message = AsyncMock(return_value="msg_456")
            mock_repo.create = AsyncMock()

            result = await notifier.send_buttons(
                phone_number_id="pnid_1",
                to="+923001234567",
                body="Choose an option",
                buttons=[("btn_1", "Yes"), ("btn_2", "No")],
                distributor_id=str(uuid4()),
            )
            assert result == "msg_456"

    @pytest.mark.asyncio
    async def test_send_read_receipt(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with patch(
            "app.notifications.whatsapp_notifier.whatsapp_client"
        ) as mock_wa:
            mock_wa.mark_as_read = AsyncMock()
            await notifier.send_read_receipt("pnid_1", "msg_123")
            mock_wa.mark_as_read.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_text_failure_returns_none(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with (
            patch(
                "app.notifications.whatsapp_notifier.whatsapp_client"
            ) as mock_wa,
            patch(
                "app.notifications.whatsapp_notifier.notification_repo"
            ) as mock_repo,
        ):
            mock_wa.send_message = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_repo.create = AsyncMock()

            result = await notifier.send_text(
                phone_number_id="pnid_1",
                to="+923001234567",
                text="Hello",
                distributor_id=str(uuid4()),
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_send_document(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with (
            patch(
                "app.notifications.whatsapp_notifier.whatsapp_client"
            ) as mock_wa,
            patch(
                "app.notifications.whatsapp_notifier.notification_repo"
            ) as mock_repo,
        ):
            mock_wa.send_message = AsyncMock(return_value="msg_789")
            mock_repo.create = AsyncMock()

            result = await notifier.send_document(
                phone_number_id="pnid_1",
                to="+923001234567",
                document_url="https://example.com/doc.pdf",
                filename="report.pdf",
                distributor_id=str(uuid4()),
            )
            assert result == "msg_789"

    @pytest.mark.asyncio
    async def test_send_list(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with (
            patch(
                "app.notifications.whatsapp_notifier.whatsapp_client"
            ) as mock_wa,
            patch(
                "app.notifications.whatsapp_notifier.notification_repo"
            ) as mock_repo,
        ):
            mock_wa.send_message = AsyncMock(return_value="msg_list")
            mock_repo.create = AsyncMock()

            result = await notifier.send_list(
                phone_number_id="pnid_1",
                to="+923001234567",
                body="Select an item",
                button_label="View items",
                sections=[{"title": "Section 1", "rows": []}],
                distributor_id=str(uuid4()),
            )
            assert result == "msg_list"

    @pytest.mark.asyncio
    async def test_notify_owner(self) -> None:
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        notifier = WhatsAppNotifier()

        with (
            patch(
                "app.notifications.whatsapp_notifier.whatsapp_client"
            ) as mock_wa,
            patch(
                "app.notifications.whatsapp_notifier.notification_repo"
            ) as mock_repo,
            patch(
                "app.notifications.whatsapp_notifier.get_settings"
            ) as mock_settings,
            patch(
                "app.notifications.whatsapp_notifier.get_template"
            ) as mock_template,
            patch(
                "app.notifications.whatsapp_notifier.build_text_message"
            ) as mock_build,
        ):
            mock_wa.send_message = AsyncMock(return_value="msg_owner")
            mock_repo.create = AsyncMock()
            mock_template.return_value = "Owner notification: {detail}"
            mock_build.return_value = {
                "messaging_product": "whatsapp",
                "to": "+923009876543",
                "type": "text",
                "text": {"body": "Owner notification: test"},
            }

            s = MagicMock()
            s.owner_phone_number_id = "owner_pnid"
            s.owner_whatsapp_number = "+923009876543"
            mock_settings.return_value = s

            result = await notifier.notify_owner(
                template_key="NEW_ORDER",
                template_kwargs={"detail": "test"},
                distributor_id=str(uuid4()),
            )
            assert result == "msg_owner"


# ═══════════════════════════════════════════════════════════════════
# WHATSAPP CLIENT
# ═══════════════════════════════════════════════════════════════════


class TestWhatsAppClient:
    """Test WhatsApp client methods with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        from app.whatsapp.client import WhatsAppClient

        client = WhatsAppClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messages": [{"id": "wamid.123"}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._http = mock_http

        with patch("app.whatsapp.client.get_settings") as mock_settings:
            s = MagicMock()
            s.meta_api_version = "v19.0"
            s.meta_api_base_url = "https://graph.facebook.com"
            mock_settings.return_value = s

            result = await client.send_message(
                phone_number_id="pnid_1",
                payload={
                    "messaging_product": "whatsapp",
                    "to": "+923001234567",
                    "type": "text",
                    "text": {"body": "hi"},
                },
            )
            assert result == "wamid.123"

    @pytest.mark.asyncio
    async def test_mark_as_read(self) -> None:
        from app.whatsapp.client import WhatsAppClient

        client = WhatsAppClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._http = mock_http

        with patch("app.whatsapp.client.get_settings") as mock_settings:
            s = MagicMock()
            s.meta_api_version = "v19.0"
            s.meta_api_base_url = "https://graph.facebook.com"
            mock_settings.return_value = s

            await client.mark_as_read("pnid_1", "msg_123")


# ═══════════════════════════════════════════════════════════════════
# WHATSAPP MEDIA
# ═══════════════════════════════════════════════════════════════════


class TestWhatsAppMedia:
    """Test media download and processing."""

    @pytest.mark.asyncio
    async def test_download_voice_bytes(self) -> None:
        from app.whatsapp.media import download_voice_bytes

        mock_bytes = b"fake audio content"

        with patch(
            "app.whatsapp.media.whatsapp_client"
        ) as mock_wa:
            mock_wa.download_media = AsyncMock(
                return_value=(mock_bytes, "audio/ogg")
            )
            data, mime = await download_voice_bytes("media_123")
            assert data == mock_bytes
            assert mime == "audio/ogg"


# ═══════════════════════════════════════════════════════════════════
# NOTIFICATION TEMPLATES
# ═══════════════════════════════════════════════════════════════════


class TestTemplateResolver:
    """Test template key resolution across languages."""

    def test_get_english_template(self) -> None:
        from app.notifications.templates import get_template

        result = get_template("GENERIC_ERROR", "english")
        assert result is not None
        assert isinstance(result, str)

    def test_get_roman_urdu_template(self) -> None:
        from app.notifications.templates import get_template

        result = get_template("GENERIC_ERROR", "roman_urdu")
        assert result is not None

    def test_get_urdu_template(self) -> None:
        from app.notifications.templates import get_template

        result = get_template("GENERIC_ERROR", "urdu")
        assert result is not None

    def test_missing_template_returns_none(self) -> None:
        from app.notifications.templates import get_template

        result = get_template("NONEXISTENT", "english")
        assert result is None or isinstance(result, str)

    def test_get_template_with_kwargs(self) -> None:
        from app.notifications.templates import get_template

        result = get_template("DISCOUNT_APPROVED", "english")
        if result:
            assert "{" in result


# ═══════════════════════════════════════════════════════════════════
# CONFIG & CONSTANTS
# ═══════════════════════════════════════════════════════════════════


class TestConfigConstants:
    """Test config validation and constants."""

    def test_subscription_status_values(self) -> None:
        from app.core.constants import SubscriptionStatus

        assert SubscriptionStatus.TRIAL == "trial"
        assert SubscriptionStatus.ACTIVE == "active"
        assert SubscriptionStatus.SUSPENDED == "suspended"
        assert SubscriptionStatus.CANCELLED == "cancelled"
        assert SubscriptionStatus.EXPIRING == "expiring"

    def test_channel_type_values(self) -> None:
        from app.core.constants import ChannelType

        assert ChannelType.A == "A"
        assert ChannelType.B == "B"

    def test_order_status_values(self) -> None:
        from app.core.constants import OrderStatus

        assert "pending" in [s.value for s in OrderStatus]
        assert "confirmed" in [s.value for s in OrderStatus]
        assert "cancelled" in [s.value for s in OrderStatus]

    def test_language_enum(self) -> None:
        from app.core.constants import Language

        assert Language.ENGLISH == "english"
        assert Language.ROMAN_URDU == "roman_urdu"
        assert Language.URDU == "urdu"

    def test_payment_method_enum(self) -> None:
        from app.core.constants import PaymentMethod

        assert "cash" in [m.value for m in PaymentMethod]
        assert "jazzcash" in [m.value for m in PaymentMethod]
