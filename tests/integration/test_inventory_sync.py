"""Integration tests for Phase 7 — inventory sync pipeline.

Covers:
- Excel and CSV parsing with column normalization
- Row validation and error collection
- Catalog upsert (insert + update) via sync service
- Stock availability checks and is_in_stock flag refresh
- Low-stock detection and alert dispatch
- Scheduler sync job orchestration
- Sync log lifecycle (STARTED → COMPLETED/PARTIAL/FAILED)

All DB and WhatsApp calls are mocked.  File parsing uses real
openpyxl and csv modules on in-memory data.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.constants import SyncSource, SyncStatus
from app.db.models.audit import InventorySyncLog
from app.db.models.catalog import CatalogItem, CatalogItemCreate
from app.db.models.distributor import Distributor
from app.inventory.stock_service import StockService
from app.inventory.sync_service import (
    KNOWN_COLUMNS,
    REQUIRED_COLUMNS,
    InventorySyncService,
    RowError,
    SyncResult,
)

# ── Fixtures ────────────────────────────────────────────────────────

_NOW = datetime.now(tz=timezone.utc)
_DIST_ID = str(uuid4())
_ITEM_ID = str(uuid4())
_SYNC_LOG_ID = str(uuid4())


def _make_catalog_item(**overrides: Any) -> CatalogItem:
    """Create a CatalogItem with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": UUID(_ITEM_ID),
        "distributor_id": UUID(_DIST_ID),
        "medicine_name": "Panadol Extra",
        "price_per_unit_paisas": 1500,
        "stock_quantity": 100,
        "reserved_quantity": 10,
        "low_stock_threshold": 20,
        "is_in_stock": True,
        "allow_order_when_out_of_stock": True,
        "unit": "strip",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return CatalogItem(**defaults)


def _make_sync_log(**overrides: Any) -> InventorySyncLog:
    """Create an InventorySyncLog with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": UUID(_SYNC_LOG_ID),
        "distributor_id": UUID(_DIST_ID),
        "sync_source": SyncSource.GOOGLE_DRIVE,
        "file_name": "inventory.xlsx",
        "status": SyncStatus.STARTED,
        "rows_processed": 0,
        "rows_updated": 0,
        "rows_inserted": 0,
        "rows_failed": 0,
        "started_at": _NOW,
    }
    defaults.update(overrides)
    return InventorySyncLog(**defaults)


def _make_distributor(**overrides: Any) -> Distributor:
    """Create a Distributor with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": UUID(_DIST_ID),
        "business_name": "Test Pharma",
        "owner_name": "Test Owner",
        "whatsapp_number": "+923001234567",
        "whatsapp_phone_number_id": "123456789",
        "catalog_sync_url": "https://drive.google.com/file/d/abc123/view",
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return Distributor(**defaults)


def _make_xlsx_bytes(headers: list[str], rows: list[list[Any]]) -> bytes:
    """Create a real .xlsx file in memory using openpyxl."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _make_csv_bytes(headers: list[str], rows: list[list[Any]]) -> bytes:
    """Create CSV file bytes in memory."""
    output = io.StringIO()
    output.write(",".join(headers) + "\n")
    for row in rows:
        output.write(",".join(str(v) for v in row) + "\n")
    return output.getvalue().encode("utf-8")


# ═══════════════════════════════════════════════════════════════════
# COLUMN NORMALIZATION
# ═══════════════════════════════════════════════════════════════════


class TestColumnNormalization:
    """Tests for header normalization and alias mapping."""

    def test_known_columns_preserved(self) -> None:
        svc = InventorySyncService()
        headers = ["medicine_name", "price_per_unit_paisas", "stock_quantity"]
        result = svc._normalize_headers(headers)
        assert result == ["medicine_name", "price_per_unit_paisas", "stock_quantity"]

    def test_aliases_mapped(self) -> None:
        svc = InventorySyncService()
        headers = ["name", "price", "qty", "brand", "cat"]
        result = svc._normalize_headers(headers)
        assert result == [
            "medicine_name",
            "price_per_unit_paisas",
            "stock_quantity",
            "brand_name",
            "category",
        ]

    def test_unknown_columns_empty_string(self) -> None:
        svc = InventorySyncService()
        headers = ["medicine_name", "foo_bar", "stock_quantity"]
        result = svc._normalize_headers(headers)
        assert result == ["medicine_name", "", "stock_quantity"]

    def test_whitespace_and_case_handled(self) -> None:
        svc = InventorySyncService()
        headers = ["  Medicine Name  ", "STOCK QUANTITY", "Price Per Unit Paisas"]
        result = svc._normalize_headers(headers)
        assert result == [
            "medicine_name",
            "stock_quantity",
            "price_per_unit_paisas",
        ]

    def test_required_column_validation_passes(self) -> None:
        svc = InventorySyncService()
        headers = ["medicine_name", "price_per_unit_paisas", "stock_quantity", "sku"]
        svc._validate_required_columns(headers)  # Should not raise

    def test_required_column_validation_fails(self) -> None:
        from app.core.exceptions import ValidationError

        svc = InventorySyncService()
        with pytest.raises(ValidationError, match="Missing required columns"):
            svc._validate_required_columns(["medicine_name", "sku"])


# ═══════════════════════════════════════════════════════════════════
# ROW VALIDATION
# ═══════════════════════════════════════════════════════════════════


class TestRowValidation:
    """Tests for individual row validation and type coercion."""

    def test_valid_row(self) -> None:
        svc = InventorySyncService()
        row = {
            "medicine_name": "Panadol",
            "price_per_unit_paisas": 1500,
            "stock_quantity": 100,
            "sku": "PAN-001",
            "category": "Pain Relief",
        }
        result = svc._validate_row(_DIST_ID, row, 2)
        assert isinstance(result, CatalogItemCreate)
        assert result.medicine_name == "Panadol"
        assert result.price_per_unit_paisas == 1500
        assert result.stock_quantity == 100
        assert result.sku == "PAN-001"

    def test_missing_medicine_name_fails(self) -> None:
        from app.core.exceptions import ValidationError

        svc = InventorySyncService()
        row = {"medicine_name": "", "price_per_unit_paisas": 1000, "stock_quantity": 10}
        with pytest.raises(ValidationError, match="medicine_name is required"):
            svc._validate_row(_DIST_ID, row, 3)

    def test_negative_price_fails(self) -> None:
        from app.core.exceptions import ValidationError

        svc = InventorySyncService()
        row = {"medicine_name": "Test", "price_per_unit_paisas": -100, "stock_quantity": 10}
        with pytest.raises(ValidationError, match="price_per_unit_paisas"):
            svc._validate_row(_DIST_ID, row, 4)

    def test_float_stock_coerced_to_int(self) -> None:
        svc = InventorySyncService()
        row = {
            "medicine_name": "Test Med",
            "price_per_unit_paisas": 500.0,
            "stock_quantity": 50.0,
        }
        result = svc._validate_row(_DIST_ID, row, 5)
        assert result.stock_quantity == 50
        assert result.price_per_unit_paisas == 500

    def test_string_numbers_coerced(self) -> None:
        svc = InventorySyncService()
        row = {
            "medicine_name": "Test Med",
            "price_per_unit_paisas": "1200",
            "stock_quantity": "75",
        }
        result = svc._validate_row(_DIST_ID, row, 6)
        assert result.price_per_unit_paisas == 1200
        assert result.stock_quantity == 75

    def test_search_keywords_comma_split(self) -> None:
        svc = InventorySyncService()
        row = {
            "medicine_name": "Paracetamol",
            "price_per_unit_paisas": 500,
            "stock_quantity": 100,
            "search_keywords": "fever, headache, pain",
        }
        result = svc._validate_row(_DIST_ID, row, 7)
        assert result.search_keywords == ["fever", "headache", "pain"]

    def test_boolean_coercion(self) -> None:
        svc = InventorySyncService()
        row = {
            "medicine_name": "Test",
            "price_per_unit_paisas": 500,
            "stock_quantity": 10,
            "requires_prescription": "yes",
            "is_controlled_substance": "no",
        }
        result = svc._validate_row(_DIST_ID, row, 8)
        assert result.requires_prescription is True
        assert result.is_controlled_substance is False


# ═══════════════════════════════════════════════════════════════════
# EXCEL PARSING
# ═══════════════════════════════════════════════════════════════════


class TestExcelParsing:
    """Tests for Excel file parsing via openpyxl."""

    def test_parse_valid_xlsx(self) -> None:
        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity"],
            rows=[
                ["Panadol", 1500, 100],
                ["Brufen", 2000, 50],
            ],
        )
        rows = svc._parse_excel(xlsx_bytes)
        assert len(rows) == 2
        assert rows[0]["medicine_name"] == "Panadol"
        assert rows[1]["stock_quantity"] == 50

    def test_parse_with_aliases(self) -> None:
        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["name", "price", "qty", "brand"],
            rows=[["Aspirin", 800, 200, "Bayer"]],
        )
        rows = svc._parse_excel(xlsx_bytes)
        assert len(rows) == 1
        assert rows[0]["medicine_name"] == "Aspirin"
        assert rows[0]["price_per_unit_paisas"] == 800
        assert rows[0]["brand_name"] == "Bayer"

    def test_skip_empty_rows(self) -> None:
        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity"],
            rows=[
                ["Panadol", 1500, 100],
                [None, None, None],
                ["Brufen", 2000, 50],
            ],
        )
        rows = svc._parse_excel(xlsx_bytes)
        assert len(rows) == 2

    def test_missing_required_column_raises(self) -> None:
        from app.core.exceptions import ValidationError

        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["medicine_name", "sku"],
            rows=[["Test", "TST-001"]],
        )
        with pytest.raises(ValidationError, match="Missing required columns"):
            svc._parse_excel(xlsx_bytes)


# ═══════════════════════════════════════════════════════════════════
# CSV PARSING
# ═══════════════════════════════════════════════════════════════════


class TestCSVParsing:
    """Tests for CSV file parsing."""

    def test_parse_valid_csv(self) -> None:
        svc = InventorySyncService()
        csv_bytes = _make_csv_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity"],
            rows=[
                ["Panadol", 1500, 100],
                ["Brufen", 2000, 50],
            ],
        )
        rows = svc._parse_csv(csv_bytes)
        assert len(rows) == 2
        assert rows[0]["medicine_name"] == "Panadol"

    def test_utf8_bom_handled(self) -> None:
        svc = InventorySyncService()
        csv_text = "medicine_name,price_per_unit_paisas,stock_quantity\nTest,500,10\n"
        csv_bytes = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
        rows = svc._parse_csv(csv_bytes)
        assert len(rows) == 1
        assert rows[0]["medicine_name"] == "Test"

    def test_aliases_in_csv(self) -> None:
        svc = InventorySyncService()
        csv_bytes = _make_csv_bytes(
            headers=["name", "price", "qty"],
            rows=[["Aspirin", 800, 200]],
        )
        rows = svc._parse_csv(csv_bytes)
        assert len(rows) == 1
        assert rows[0]["medicine_name"] == "Aspirin"


# ═══════════════════════════════════════════════════════════════════
# TYPE COERCION HELPERS
# ═══════════════════════════════════════════════════════════════════


class TestTypeCoercion:
    """Tests for static type coercion methods."""

    def test_str_value(self) -> None:
        assert InventorySyncService._str_value("hello") == "hello"
        assert InventorySyncService._str_value("  spaced  ") == "spaced"
        assert InventorySyncService._str_value(None) is None
        assert InventorySyncService._str_value("") is None
        assert InventorySyncService._str_value(123) == "123"

    def test_int_value(self) -> None:
        assert InventorySyncService._int_value(42) == 42
        assert InventorySyncService._int_value(42.7) == 42
        assert InventorySyncService._int_value("100") == 100
        assert InventorySyncService._int_value("100.5") == 100
        assert InventorySyncService._int_value(None) is None
        assert InventorySyncService._int_value("") is None
        assert InventorySyncService._int_value("abc") is None

    def test_bool_value(self) -> None:
        assert InventorySyncService._bool_value(True) is True
        assert InventorySyncService._bool_value(False) is False
        assert InventorySyncService._bool_value("yes") is True
        assert InventorySyncService._bool_value("no") is False
        assert InventorySyncService._bool_value("1") is True
        assert InventorySyncService._bool_value("0") is False
        assert InventorySyncService._bool_value("Y") is True
        assert InventorySyncService._bool_value("N") is False
        assert InventorySyncService._bool_value(None) is None
        assert InventorySyncService._bool_value("maybe") is None


# ═══════════════════════════════════════════════════════════════════
# GOOGLE DRIVE URL CONVERSION
# ═══════════════════════════════════════════════════════════════════


class TestGDriveURL:
    """Tests for Google Drive URL conversion."""

    def test_file_d_pattern(self) -> None:
        url = "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view"
        result = InventorySyncService._convert_gdrive_url(url)
        assert "uc?export=download" in result
        assert "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs" in result

    def test_open_id_pattern(self) -> None:
        url = "https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        result = InventorySyncService._convert_gdrive_url(url)
        assert "uc?export=download" in result

    def test_non_gdrive_url_unchanged(self) -> None:
        url = "https://example.com/inventory.xlsx"
        assert InventorySyncService._convert_gdrive_url(url) == url


# ═══════════════════════════════════════════════════════════════════
# SYNC FROM BYTES (full pipeline)
# ═══════════════════════════════════════════════════════════════════


class TestSyncFromBytes:
    """Integration tests for sync_from_bytes pipeline."""

    @pytest.mark.asyncio
    async def test_successful_xlsx_sync(self) -> None:
        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity", "sku"],
            rows=[
                ["Panadol", 1500, 100, "PAN-001"],
                ["Brufen", 2000, 50, "BRU-001"],
            ],
        )

        mock_log = _make_sync_log()
        mock_item = _make_catalog_item()

        with (
            patch("app.inventory.sync_service.sync_log_repo") as mock_sync_log_repo,
            patch("app.inventory.sync_service.catalog_repo") as mock_cat_repo,
        ):
            mock_sync_log_repo.create = AsyncMock(return_value=mock_log)
            mock_sync_log_repo.update = AsyncMock(return_value=mock_log)
            mock_cat_repo.upsert_by_sku_or_name = AsyncMock(
                return_value=(mock_item, True)
            )

            result = await svc.sync_from_bytes(
                distributor_id=_DIST_ID,
                file_bytes=xlsx_bytes,
                file_name="inventory.xlsx",
            )

        assert result.status == SyncStatus.COMPLETED
        assert result.rows_inserted == 2
        assert result.rows_failed == 0
        assert mock_cat_repo.upsert_by_sku_or_name.call_count == 2

    @pytest.mark.asyncio
    async def test_partial_sync_with_errors(self) -> None:
        from app.core.exceptions import ValidationError

        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity"],
            rows=[
                ["Good Med", 1000, 50],
                ["Bad Med", -999, 10],  # Invalid price → fails validation
                ["Another Good", 500, 20],
            ],
        )

        mock_log = _make_sync_log()
        mock_item = _make_catalog_item()

        with (
            patch("app.inventory.sync_service.sync_log_repo") as mock_sync_log_repo,
            patch("app.inventory.sync_service.catalog_repo") as mock_cat_repo,
        ):
            mock_sync_log_repo.create = AsyncMock(return_value=mock_log)
            mock_sync_log_repo.update = AsyncMock(return_value=mock_log)
            mock_cat_repo.upsert_by_sku_or_name = AsyncMock(
                return_value=(mock_item, True)
            )

            result = await svc.sync_from_bytes(
                distributor_id=_DIST_ID,
                file_bytes=xlsx_bytes,
                file_name="test.xlsx",
            )

        assert result.status == SyncStatus.PARTIAL
        assert result.rows_inserted == 2
        assert result.rows_failed == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_csv_sync(self) -> None:
        svc = InventorySyncService()
        csv_bytes = _make_csv_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity"],
            rows=[["Aspirin", 800, 200]],
        )

        mock_log = _make_sync_log()
        mock_item = _make_catalog_item()

        with (
            patch("app.inventory.sync_service.sync_log_repo") as mock_sync_log_repo,
            patch("app.inventory.sync_service.catalog_repo") as mock_cat_repo,
        ):
            mock_sync_log_repo.create = AsyncMock(return_value=mock_log)
            mock_sync_log_repo.update = AsyncMock(return_value=mock_log)
            mock_cat_repo.upsert_by_sku_or_name = AsyncMock(
                return_value=(mock_item, True)
            )

            result = await svc.sync_from_bytes(
                distributor_id=_DIST_ID,
                file_bytes=csv_bytes,
                file_name="catalog.csv",
            )

        assert result.status == SyncStatus.COMPLETED
        assert result.rows_inserted == 1

    @pytest.mark.asyncio
    async def test_unsupported_format_fails(self) -> None:
        svc = InventorySyncService()
        mock_log = _make_sync_log()

        with patch("app.inventory.sync_service.sync_log_repo") as mock_sync_log_repo:
            mock_sync_log_repo.create = AsyncMock(return_value=mock_log)
            mock_sync_log_repo.update = AsyncMock(return_value=mock_log)

            result = await svc.sync_from_bytes(
                distributor_id=_DIST_ID,
                file_bytes=b"some data",
                file_name="data.json",
            )

        assert result.status == SyncStatus.FAILED

    @pytest.mark.asyncio
    async def test_update_vs_insert_tracked(self) -> None:
        svc = InventorySyncService()
        xlsx_bytes = _make_xlsx_bytes(
            headers=["medicine_name", "price_per_unit_paisas", "stock_quantity"],
            rows=[
                ["Existing Med", 1000, 50],
                ["New Med", 2000, 100],
            ],
        )

        mock_log = _make_sync_log()
        mock_item = _make_catalog_item()

        # First call: update (was_inserted=False), second: insert (was_inserted=True)
        with (
            patch("app.inventory.sync_service.sync_log_repo") as mock_sync_log_repo,
            patch("app.inventory.sync_service.catalog_repo") as mock_cat_repo,
        ):
            mock_sync_log_repo.create = AsyncMock(return_value=mock_log)
            mock_sync_log_repo.update = AsyncMock(return_value=mock_log)
            mock_cat_repo.upsert_by_sku_or_name = AsyncMock(
                side_effect=[
                    (mock_item, False),  # updated
                    (mock_item, True),  # inserted
                ]
            )

            result = await svc.sync_from_bytes(
                distributor_id=_DIST_ID,
                file_bytes=xlsx_bytes,
                file_name="test.xlsx",
            )

        assert result.rows_updated == 1
        assert result.rows_inserted == 1
        assert result.rows_processed == 2
        assert result.status == SyncStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════
# STOCK SERVICE
# ═══════════════════════════════════════════════════════════════════


class TestStockService:
    """Tests for StockService stock checks and alert dispatch."""

    @pytest.mark.asyncio
    async def test_check_availability_sufficient(self) -> None:
        svc = StockService()
        item = _make_catalog_item(stock_quantity=100, reserved_quantity=10)

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_by_id_or_raise = AsyncMock(return_value=item)
            is_available, available = await svc.check_availability(
                _DIST_ID, _ITEM_ID, 50
            )

        assert is_available is True
        assert available == 90

    @pytest.mark.asyncio
    async def test_check_availability_insufficient(self) -> None:
        svc = StockService()
        item = _make_catalog_item(stock_quantity=20, reserved_quantity=15)

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_by_id_or_raise = AsyncMock(return_value=item)
            is_available, available = await svc.check_availability(
                _DIST_ID, _ITEM_ID, 10
            )

        assert is_available is False
        assert available == 5

    @pytest.mark.asyncio
    async def test_can_fulfil_when_allow_oos(self) -> None:
        svc = StockService()
        item = _make_catalog_item(
            stock_quantity=0,
            reserved_quantity=0,
            allow_order_when_out_of_stock=True,
        )

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_by_id_or_raise = AsyncMock(return_value=item)
            result = await svc.can_fulfil_order(_DIST_ID, _ITEM_ID, 100)

        assert result is True

    @pytest.mark.asyncio
    async def test_cannot_fulfil_when_disallow_oos(self) -> None:
        svc = StockService()
        item = _make_catalog_item(
            stock_quantity=0,
            reserved_quantity=0,
            allow_order_when_out_of_stock=False,
        )

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_by_id_or_raise = AsyncMock(return_value=item)
            result = await svc.can_fulfil_order(_DIST_ID, _ITEM_ID, 1)

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_in_stock_flags(self) -> None:
        svc = StockService()
        items = [
            _make_catalog_item(
                id=uuid4(), stock_quantity=0, is_in_stock=True
            ),  # Wrong → should be False
            _make_catalog_item(
                id=uuid4(), stock_quantity=50, is_in_stock=False
            ),  # Wrong → should be True
            _make_catalog_item(
                id=uuid4(), stock_quantity=10, is_in_stock=True
            ),  # Correct
        ]

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_active_catalog = AsyncMock(return_value=items)
            mock_repo.batch_update_in_stock_flags = AsyncMock()

            in_stock, out_of_stock = await svc.refresh_in_stock_flags(_DIST_ID)

        assert in_stock == 1  # One item set to in_stock
        assert out_of_stock == 1  # One item set to out_of_stock
        mock_repo.batch_update_in_stock_flags.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_detect_and_alert_low_stock(self) -> None:
        svc = StockService()
        low_items = [
            _make_catalog_item(
                id=uuid4(),
                medicine_name="Med A",
                stock_quantity=5,
                low_stock_threshold=20,
            ),
            _make_catalog_item(
                id=uuid4(),
                medicine_name="Med B",
                stock_quantity=2,
                low_stock_threshold=10,
            ),
        ]

        with (
            patch("app.inventory.stock_service.catalog_repo") as mock_repo,
            patch("app.inventory.stock_service.whatsapp_notifier") as mock_notifier,
        ):
            mock_repo.get_low_stock_items = AsyncMock(return_value=low_items)
            mock_notifier.notify_owner = AsyncMock(return_value="msg_123")

            alerts = await svc.detect_and_alert_low_stock(_DIST_ID)

        assert alerts == 2
        assert mock_notifier.notify_owner.call_count == 2

        # Verify template kwargs
        first_call = mock_notifier.notify_owner.call_args_list[0]
        assert first_call.kwargs["template_key"] == "OWNER_LOW_STOCK"
        assert first_call.kwargs["template_kwargs"]["medicine_name"] == "Med A"
        assert first_call.kwargs["template_kwargs"]["quantity"] == 5

    @pytest.mark.asyncio
    async def test_no_alerts_when_no_low_stock(self) -> None:
        svc = StockService()

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_low_stock_items = AsyncMock(return_value=[])

            alerts = await svc.detect_and_alert_low_stock(_DIST_ID)

        assert alerts == 0

    @pytest.mark.asyncio
    async def test_post_sync_stock_check_pipeline(self) -> None:
        svc = StockService()
        items = [
            _make_catalog_item(stock_quantity=0, is_in_stock=True),
        ]
        low_items = [
            _make_catalog_item(stock_quantity=5, low_stock_threshold=20),
        ]

        with (
            patch("app.inventory.stock_service.catalog_repo") as mock_repo,
            patch("app.inventory.stock_service.whatsapp_notifier") as mock_notifier,
        ):
            mock_repo.get_active_catalog = AsyncMock(return_value=items)
            mock_repo.batch_update_in_stock_flags = AsyncMock()
            mock_repo.get_low_stock_items = AsyncMock(return_value=low_items)
            mock_notifier.notify_owner = AsyncMock(return_value="msg_456")

            result = await svc.post_sync_stock_check(_DIST_ID)

        assert result["set_out_of_stock"] == 1
        assert result["alerts_sent"] == 1

    @pytest.mark.asyncio
    async def test_get_stock_summary(self) -> None:
        svc = StockService()
        items = [
            _make_catalog_item(
                id=uuid4(), stock_quantity=100, is_in_stock=True, low_stock_threshold=10
            ),
            _make_catalog_item(
                id=uuid4(), stock_quantity=0, is_in_stock=False, low_stock_threshold=10
            ),
            _make_catalog_item(
                id=uuid4(), stock_quantity=5, is_in_stock=True, low_stock_threshold=20
            ),
        ]

        with patch("app.inventory.stock_service.catalog_repo") as mock_repo:
            mock_repo.get_active_catalog = AsyncMock(return_value=items)

            summary = await svc.get_stock_summary(_DIST_ID)

        assert summary["total_items"] == 3
        assert summary["in_stock"] == 2
        assert summary["out_of_stock"] == 1
        assert summary["low_stock"] == 2  # item2 (0<=10) and item3 (5<=20)
        assert summary["total_stock_units"] == 105


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER SYNC JOB
# ═══════════════════════════════════════════════════════════════════


class TestSchedulerSyncJob:
    """Tests for the APScheduler inventory sync job."""

    @pytest.mark.asyncio
    async def test_sync_all_distributors(self) -> None:
        from app.scheduler.jobs.sync_jobs import run_inventory_sync

        dist = _make_distributor()
        sync_result = SyncResult(
            sync_log_id=_SYNC_LOG_ID,
            distributor_id=_DIST_ID,
            status=SyncStatus.COMPLETED,
            rows_processed=5,
            rows_inserted=3,
            rows_updated=2,
        )

        with (
            patch("app.scheduler.jobs.sync_jobs.get_settings") as mock_settings,
            patch("app.scheduler.jobs.sync_jobs.distributor_repo") as mock_dist_repo,
            patch("app.scheduler.jobs.sync_jobs.inventory_sync_service") as mock_sync_svc,
            patch("app.scheduler.jobs.sync_jobs.stock_service") as mock_stock_svc,
        ):
            mock_settings.return_value = MagicMock(enable_inventory_sync=True)
            mock_dist_repo.get_active_distributors = AsyncMock(return_value=[dist])
            mock_sync_svc.sync_from_url = AsyncMock(return_value=sync_result)
            mock_stock_svc.post_sync_stock_check = AsyncMock(
                return_value={"set_in_stock": 0, "set_out_of_stock": 0, "alerts_sent": 0}
            )
            mock_dist_repo.update = AsyncMock()

            await run_inventory_sync()

        mock_sync_svc.sync_from_url.assert_called_once()
        mock_stock_svc.post_sync_stock_check.assert_called_once_with(_DIST_ID)
        mock_dist_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_distributors_without_url(self) -> None:
        from app.scheduler.jobs.sync_jobs import run_inventory_sync

        dist = _make_distributor(catalog_sync_url=None)

        with (
            patch("app.scheduler.jobs.sync_jobs.get_settings") as mock_settings,
            patch("app.scheduler.jobs.sync_jobs.distributor_repo") as mock_dist_repo,
            patch("app.scheduler.jobs.sync_jobs.inventory_sync_service") as mock_sync_svc,
        ):
            mock_settings.return_value = MagicMock(enable_inventory_sync=True)
            mock_dist_repo.get_active_distributors = AsyncMock(return_value=[dist])
            mock_sync_svc.sync_from_url = AsyncMock()

            await run_inventory_sync()

        mock_sync_svc.sync_from_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_disabled_does_nothing(self) -> None:
        from app.scheduler.jobs.sync_jobs import run_inventory_sync

        with (
            patch("app.scheduler.jobs.sync_jobs.get_settings") as mock_settings,
            patch("app.scheduler.jobs.sync_jobs.distributor_repo") as mock_dist_repo,
        ):
            mock_settings.return_value = MagicMock(enable_inventory_sync=False)

            await run_inventory_sync()

        mock_dist_repo.get_active_distributors.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_sync_continues_to_next_distributor(self) -> None:
        from app.scheduler.jobs.sync_jobs import run_inventory_sync

        dist1 = _make_distributor()
        dist2_id = str(uuid4())
        dist2 = _make_distributor(id=UUID(dist2_id))

        fail_result = SyncResult(
            sync_log_id=str(uuid4()),
            distributor_id=_DIST_ID,
            status=SyncStatus.FAILED,
        )
        success_result = SyncResult(
            sync_log_id=str(uuid4()),
            distributor_id=dist2_id,
            status=SyncStatus.COMPLETED,
            rows_processed=3,
            rows_inserted=3,
        )

        with (
            patch("app.scheduler.jobs.sync_jobs.get_settings") as mock_settings,
            patch("app.scheduler.jobs.sync_jobs.distributor_repo") as mock_dist_repo,
            patch("app.scheduler.jobs.sync_jobs.inventory_sync_service") as mock_sync_svc,
            patch("app.scheduler.jobs.sync_jobs.stock_service") as mock_stock_svc,
        ):
            mock_settings.return_value = MagicMock(enable_inventory_sync=True)
            mock_dist_repo.get_active_distributors = AsyncMock(
                return_value=[dist1, dist2]
            )
            mock_sync_svc.sync_from_url = AsyncMock(
                side_effect=[fail_result, success_result]
            )
            mock_stock_svc.post_sync_stock_check = AsyncMock(
                return_value={"set_in_stock": 0, "set_out_of_stock": 0, "alerts_sent": 0}
            )
            mock_dist_repo.update = AsyncMock()

            await run_inventory_sync()

        # Should have been called for both distributors
        assert mock_sync_svc.sync_from_url.call_count == 2
        # Stock check only on successful sync
        mock_stock_svc.post_sync_stock_check.assert_called_once_with(dist2_id)


# ═══════════════════════════════════════════════════════════════════
# SYNC LOG REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class TestSyncLogRepo:
    """Tests for InventorySyncLogRepository CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_sync_log(self) -> None:
        from app.db.models.audit import InventorySyncLogCreate
        from app.db.repositories.sync_log_repo import InventorySyncLogRepository

        repo = InventorySyncLogRepository()
        mock_data = {
            "id": str(uuid4()),
            "distributor_id": _DIST_ID,
            "sync_source": "google_drive",
            "file_name": "test.xlsx",
            "status": "started",
            "rows_processed": 0,
            "rows_updated": 0,
            "rows_inserted": 0,
            "rows_failed": 0,
            "error_details": [],
            "started_at": _NOW.isoformat(),
        }

        mock_result = MagicMock()
        mock_result.data = [mock_data]

        # Build a synchronous mock chain that returns itself on every call
        mock_chain = MagicMock()
        mock_chain.insert.return_value = mock_chain
        mock_chain.execute = AsyncMock(return_value=mock_result)

        with patch("app.db.repositories.sync_log_repo.get_db_client") as mock_client:
            mock_client.return_value.table.return_value = mock_chain

            result = await repo.create(
                InventorySyncLogCreate(
                    distributor_id=UUID(_DIST_ID),
                    sync_source=SyncSource.GOOGLE_DRIVE,
                    file_name="test.xlsx",
                )
            )

        assert isinstance(result, InventorySyncLog)

    @pytest.mark.asyncio
    async def test_get_latest_for_distributor(self) -> None:
        from app.db.repositories.sync_log_repo import InventorySyncLogRepository

        repo = InventorySyncLogRepository()
        mock_data = {
            "id": str(uuid4()),
            "distributor_id": _DIST_ID,
            "sync_source": "google_drive",
            "file_name": "test.xlsx",
            "status": "completed",
            "rows_processed": 10,
            "rows_updated": 5,
            "rows_inserted": 5,
            "rows_failed": 0,
            "error_details": [],
            "started_at": _NOW.isoformat(),
            "completed_at": _NOW.isoformat(),
        }

        mock_result = MagicMock()
        mock_result.data = [mock_data]

        # Synchronous chain mock — each method returns self, execute is async
        mock_chain = MagicMock()
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.execute = AsyncMock(return_value=mock_result)

        with patch("app.db.repositories.sync_log_repo.get_db_client") as mock_client:
            mock_client.return_value.table.return_value = mock_chain

            results = await repo.get_latest_for_distributor(_DIST_ID)

        assert len(results) == 1
        assert isinstance(results[0], InventorySyncLog)


# ═══════════════════════════════════════════════════════════════════
# CATALOG REPO UPSERT
# ═══════════════════════════════════════════════════════════════════


class TestCatalogRepoUpsert:
    """Tests for CatalogRepository.upsert_by_sku_or_name."""

    @pytest.mark.asyncio
    async def test_upsert_inserts_new(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        repo = CatalogRepository()
        new_item = _make_catalog_item()
        create_data = CatalogItemCreate(
            distributor_id=UUID(_DIST_ID),
            medicine_name="New Medicine",
            price_per_unit_paisas=1000,
            stock_quantity=50,
        )

        # Mock: get_by_sku returns None, name search returns None → insert
        mock_result = MagicMock()
        mock_result.data = None

        mock_chain = MagicMock()
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.ilike.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_chain.execute = AsyncMock(return_value=mock_result)

        with (
            patch.object(repo, "get_by_sku", new_callable=AsyncMock, return_value=None),
            patch.object(repo, "create", new_callable=AsyncMock, return_value=new_item),
            patch("app.db.repositories.catalog_repo.get_db_client") as mock_client,
        ):
            mock_client.return_value.table.return_value = mock_chain

            item, was_inserted = await repo.upsert_by_sku_or_name(
                _DIST_ID, create_data
            )

        assert was_inserted is True
        assert item == new_item

    @pytest.mark.asyncio
    async def test_upsert_updates_by_sku(self) -> None:
        from app.db.repositories.catalog_repo import CatalogRepository

        repo = CatalogRepository()
        existing = _make_catalog_item(sku="PAN-001")
        updated = _make_catalog_item(sku="PAN-001", stock_quantity=200)

        create_data = CatalogItemCreate(
            distributor_id=UUID(_DIST_ID),
            medicine_name="Panadol",
            price_per_unit_paisas=1500,
            stock_quantity=200,
            sku="PAN-001",
        )

        with (
            patch.object(repo, "get_by_sku", new_callable=AsyncMock, return_value=existing),
            patch.object(repo, "update", new_callable=AsyncMock, return_value=updated),
        ):
            item, was_inserted = await repo.upsert_by_sku_or_name(
                _DIST_ID, create_data
            )

        assert was_inserted is False
        assert item == updated
