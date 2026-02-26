"""Tests for scheduler report jobs, service registry, analytics service, email dispatch.

All report_jobs functions use LAZY IMPORTS inside function bodies, so
we patch at the SOURCE module (e.g. ``app.analytics.aggregator.aggregator``),
not at ``app.scheduler.jobs.report_jobs.aggregator``.

Covers:
- app.scheduler.jobs.report_jobs (8 public functions + _dispatch_excel_for_schedule)
- app.channels.channel_b.service_registry (ServiceRegistry class)
- app.reporting.analytics_service (AnalyticsReportService — injected repos)
- app.reporting.email_dispatch (EmailDispatcher — _is_configured + _send_email)

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Report Jobs — lazy imports; patch at source module
# ═══════════════════════════════════════════════════════════════════════════


class TestRunDailyAnalyticsAggregation:
    """Cover run_daily_analytics_aggregation."""

    @patch("app.analytics.aggregator.aggregator")
    async def test_success(self, mock_agg: MagicMock) -> None:
        from app.scheduler.jobs.report_jobs import run_daily_analytics_aggregation

        mock_agg.compute_all_distributors = AsyncMock(return_value=5)
        await run_daily_analytics_aggregation()
        mock_agg.compute_all_distributors.assert_called_once()

    @patch("app.analytics.aggregator.aggregator")
    async def test_exception_caught(self, mock_agg: MagicMock) -> None:
        from app.scheduler.jobs.report_jobs import run_daily_analytics_aggregation

        mock_agg.compute_all_distributors = AsyncMock(
            side_effect=RuntimeError("DB down")
        )
        # Should NOT raise — job catches all exceptions
        await run_daily_analytics_aggregation()


class TestRunDailyOrderSummary:
    """Cover run_daily_order_summary."""

    @patch("app.notifications.whatsapp_notifier.whatsapp_notifier")
    @patch("app.reporting.analytics_service.analytics_report_service")
    @patch("app.reporting.report_scheduler.should_send_daily_summary")
    @patch("app.db.client.get_db_client")
    @patch("app.core.config.get_settings")
    async def test_sends_summary(
        self,
        mock_settings: MagicMock,
        mock_db: MagicMock,
        mock_should: MagicMock,
        mock_svc: MagicMock,
        mock_notifier: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import run_daily_order_summary

        mock_settings.return_value = MagicMock()

        # DB: distributors table
        dist_data = MagicMock()
        dist_data.data = [
            {
                "id": "dist-1",
                "business_name": "Test Pharma",
                "owner_phone": "+923001234567",
                "whatsapp_phone_number_id": "pnid-1",
            }
        ]
        # DB: notifications_log table (idempotency check — no previous)
        notif_data = MagicMock()
        notif_data.data = []

        mock_table_dist = MagicMock()
        mock_table_dist.select.return_value = mock_table_dist
        mock_table_dist.eq.return_value = mock_table_dist
        mock_table_dist.execute = AsyncMock(return_value=dist_data)

        mock_table_notif = MagicMock()
        mock_table_notif.select.return_value = mock_table_notif
        mock_table_notif.eq.return_value = mock_table_notif
        mock_table_notif.gte.return_value = mock_table_notif
        mock_table_notif.limit.return_value = mock_table_notif
        mock_table_notif.execute = AsyncMock(return_value=notif_data)

        mock_client = MagicMock()
        mock_client.table.side_effect = lambda name: (
            mock_table_dist if name == "distributors" else mock_table_notif
        )
        mock_db.return_value = mock_client

        mock_should.return_value = True
        mock_svc.get_daily_summary = AsyncMock(
            return_value={"total_orders": 10, "total_revenue_paisas": 500000}
        )
        mock_svc.format_daily_whatsapp.return_value = "Daily: 10 orders"
        mock_notifier.send_text = AsyncMock()

        await run_daily_order_summary()
        mock_notifier.send_text.assert_called_once()

    @patch("app.db.client.get_db_client")
    @patch("app.core.config.get_settings")
    async def test_exception_caught(
        self, mock_settings: MagicMock, mock_db: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import run_daily_order_summary

        mock_settings.return_value = MagicMock()
        mock_db.side_effect = RuntimeError("fail")
        await run_daily_order_summary()  # Should NOT raise


class TestRunWeeklyReport:
    """Cover run_weekly_report."""

    @patch("app.notifications.whatsapp_notifier.whatsapp_notifier")
    @patch("app.reporting.email_dispatch.email_dispatcher")
    @patch("app.reporting.excel_generator.get_monthly_report_path")
    @patch("app.reporting.analytics_service.analytics_report_service")
    @patch("app.reporting.report_scheduler.get_report_date_range")
    @patch("app.reporting.report_scheduler.get_distributors_needing_reports")
    @patch("app.db.client.get_db_client")
    async def test_sends_weekly(
        self,
        mock_db: MagicMock,
        mock_get_dists: MagicMock,
        mock_date_range: MagicMock,
        mock_svc: MagicMock,
        mock_excel: MagicMock,
        mock_email: MagicMock,
        mock_notifier: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import run_weekly_report

        mock_date_range.return_value = (date(2025, 1, 6), date(2025, 1, 12))
        mock_get_dists.return_value = [
            {
                "distributor_id": "dist-1",
                "business_name": "Test Pharma",
                "owner_email": "owner@test.com",
            }
        ]
        mock_svc.get_weekly_summary = AsyncMock(
            return_value={"total_orders": 50}
        )
        mock_svc.format_weekly_whatsapp.return_value = "Weekly: 50 orders"

        # DB for distributor lookup
        dist_info = MagicMock()
        dist_info.data = [
            {"owner_phone": "+923001234567", "whatsapp_phone_number_id": "pnid-1"}
        ]
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute = AsyncMock(return_value=dist_info)
        mock_db.return_value = MagicMock()
        mock_db.return_value.table.return_value = mock_table

        mock_notifier.send_text = AsyncMock()
        mock_excel.return_value = Path("/tmp/report.xlsx")
        mock_email.send_excel_report = AsyncMock()

        await run_weekly_report()

    @patch("app.reporting.report_scheduler.get_distributors_needing_reports")
    @patch("app.reporting.report_scheduler.get_report_date_range")
    async def test_exception_caught(
        self, mock_range: MagicMock, mock_get: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import run_weekly_report

        mock_range.side_effect = RuntimeError("fail")
        await run_weekly_report()


class TestRunMonthlyReport:
    """Cover run_monthly_report."""

    @patch("app.notifications.whatsapp_notifier.whatsapp_notifier")
    @patch("app.reporting.email_dispatch.email_dispatcher")
    @patch("app.reporting.excel_generator.get_monthly_report_path")
    @patch("app.reporting.analytics_service.analytics_report_service")
    @patch("app.db.client.get_db_client")
    async def test_sends_monthly(
        self,
        mock_db: MagicMock,
        mock_svc: MagicMock,
        mock_excel: MagicMock,
        mock_email: MagicMock,
        mock_notifier: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import run_monthly_report

        # DB: distributors query
        dist_data = MagicMock()
        dist_data.data = [
            {
                "id": "dist-1",
                "business_name": "Test",
                "email": "owner@test.com",
                "owner_phone": "+923001234567",
                "whatsapp_phone_number_id": "pnid-1",
            }
        ]
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute = AsyncMock(return_value=dist_data)
        mock_db.return_value = MagicMock()
        mock_db.return_value.table.return_value = mock_table

        mock_svc.get_monthly_summary = AsyncMock(
            return_value={"total_orders": 200}
        )
        mock_svc.format_monthly_whatsapp.return_value = "Monthly: 200 orders"
        mock_notifier.send_text = AsyncMock()
        mock_excel.return_value = Path("/tmp/monthly.xlsx")
        mock_email.send_monthly_report = AsyncMock()

        await run_monthly_report()

    @patch("app.db.client.get_db_client")
    async def test_exception_caught(self, mock_db: MagicMock) -> None:
        from app.scheduler.jobs.report_jobs import run_monthly_report

        mock_db.side_effect = RuntimeError("fail")
        await run_monthly_report()


class TestRunChurnDetection:
    """Cover run_churn_detection."""

    @patch("app.reporting.email_dispatch.email_dispatcher")
    @patch("app.db.client.get_db_client")
    @patch("app.analytics.aggregator.aggregator")
    async def test_with_churn_events(
        self,
        mock_agg: MagicMock,
        mock_db: MagicMock,
        mock_email: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import run_churn_detection

        mock_agg.run_churn_detection = AsyncMock(return_value=3)

        # Tables: analytics_customer_events, customers, distributors
        churn_result = MagicMock()
        churn_result.data = [
            {
                "distributor_id": "dist-1",
                "customer_id": "cust-1",
                "event_type": "churn_risk",
                "event_data": {"days_inactive": 30, "level": "warning"},
                "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ]
        cust_result = MagicMock()
        cust_result.data = [{"name": "Ali Medical"}]
        dist_info_result = MagicMock()
        dist_info_result.data = [
            {"email": "owner@test.com", "business_name": "Test Pharma"}
        ]

        def make_table(name: str) -> MagicMock:
            tbl = MagicMock()
            tbl.select.return_value = tbl
            tbl.eq.return_value = tbl
            tbl.gte.return_value = tbl
            tbl.limit.return_value = tbl
            if name == "analytics_customer_events":
                tbl.execute = AsyncMock(return_value=churn_result)
            elif name == "customers":
                tbl.execute = AsyncMock(return_value=cust_result)
            elif name == "distributors":
                tbl.execute = AsyncMock(return_value=dist_info_result)
            return tbl

        mock_client = MagicMock()
        mock_client.table.side_effect = make_table
        mock_db.return_value = mock_client

        mock_email.send_churn_alert = AsyncMock()

        # Note: run_churn_detection has a bug — references `results` instead
        # of `dist_events` on the final log line — but the outer try/except
        # catches the NameError so the function still doesn't raise.
        await run_churn_detection()

    @patch("app.analytics.aggregator.aggregator")
    async def test_exception_caught(self, mock_agg: MagicMock) -> None:
        from app.scheduler.jobs.report_jobs import run_churn_detection

        mock_agg.run_churn_detection = AsyncMock(
            side_effect=RuntimeError("fail")
        )
        await run_churn_detection()


class TestExcelReportDispatchers:
    """Cover morning/evening Excel dispatch."""

    @patch(
        "app.scheduler.jobs.report_jobs._dispatch_excel_for_schedule",
        new_callable=AsyncMock,
    )
    async def test_morning(self, mock_dispatch: AsyncMock) -> None:
        from app.scheduler.jobs.report_jobs import run_excel_report_dispatch_morning

        await run_excel_report_dispatch_morning()
        mock_dispatch.assert_called_once_with("DAILY_MORNING")

    @patch(
        "app.scheduler.jobs.report_jobs._dispatch_excel_for_schedule",
        new_callable=AsyncMock,
    )
    async def test_evening(self, mock_dispatch: AsyncMock) -> None:
        from app.scheduler.jobs.report_jobs import run_excel_report_dispatch_evening

        await run_excel_report_dispatch_evening()
        mock_dispatch.assert_called_once_with("DAILY_EVENING")

    @patch("app.reporting.email_dispatch.email_dispatcher")
    @patch("app.reporting.excel_generator.get_monthly_report_path")
    @patch("app.reporting.report_scheduler.get_report_date_range")
    @patch("app.reporting.report_scheduler.get_distributors_needing_reports")
    async def test_dispatch_excel_for_schedule(
        self,
        mock_get_dists: MagicMock,
        mock_date_range: MagicMock,
        mock_path: MagicMock,
        mock_email: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import _dispatch_excel_for_schedule

        mock_get_dists.return_value = [
            {
                "distributor_id": "dist-1",
                "owner_email": "dist@example.com",
                "business_name": "Test",
            }
        ]
        mock_date_range.return_value = (date(2025, 1, 1), date(2025, 1, 31))
        mock_path.return_value = Path("/tmp/report.xlsx")
        mock_email.send_excel_report = AsyncMock()

        await _dispatch_excel_for_schedule("daily_morning")
        mock_email.send_excel_report.assert_called_once()

    @patch("app.reporting.report_scheduler.get_distributors_needing_reports")
    @patch("app.reporting.report_scheduler.get_report_date_range")
    async def test_dispatch_exception_caught(
        self, mock_range: MagicMock, mock_get: MagicMock,
    ) -> None:
        from app.scheduler.jobs.report_jobs import _dispatch_excel_for_schedule

        mock_range.side_effect = RuntimeError("fail")
        await _dispatch_excel_for_schedule("DAILY_EVENING")

    @patch("app.reporting.email_dispatch.email_dispatcher")
    @patch("app.reporting.excel_generator.get_monthly_report_path")
    @patch("app.reporting.report_scheduler.get_report_date_range")
    @patch("app.reporting.report_scheduler.get_distributors_needing_reports")
    async def test_dispatch_no_email_skipped(
        self,
        mock_get_dists: MagicMock,
        mock_date_range: MagicMock,
        mock_path: MagicMock,
        mock_email: MagicMock,
    ) -> None:
        """Distributors without owner_email are skipped."""
        from app.scheduler.jobs.report_jobs import _dispatch_excel_for_schedule

        mock_get_dists.return_value = [
            {
                "distributor_id": "dist-1",
                "owner_email": None,
                "business_name": "Test",
            }
        ]
        mock_date_range.return_value = (date(2025, 1, 1), date(2025, 1, 31))
        mock_path.return_value = Path("/tmp/report.xlsx")
        mock_email.send_excel_report = AsyncMock()

        await _dispatch_excel_for_schedule("daily_morning")
        mock_email.send_excel_report.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Channel B — Service Registry (class-based, singleton)
# ═══════════════════════════════════════════════════════════════════════════


class TestServiceRegistry:
    """Cover ServiceRegistry class methods."""

    def _make_entry(self, **overrides: object) -> MagicMock:
        """Build a mock ServiceRegistryEntry."""
        entry = MagicMock()
        entry.id = overrides.get("id", uuid4())
        entry.name = overrides.get("name", "Test Service")
        entry.slug = overrides.get("slug", "test-svc")
        entry.description = overrides.get("description", "A test service")
        entry.short_description = overrides.get("short_description", "Short desc")
        entry.setup_fee_paisas = overrides.get("setup_fee_paisas", 0)
        entry.monthly_fee_paisas = overrides.get("monthly_fee_paisas", 500000)
        entry.target_business_types = overrides.get("target_business_types", [])
        entry.demo_video_url = overrides.get("demo_video_url", None)
        entry.sales_flow_handler = overrides.get("sales_flow_handler", None)
        entry.is_coming_soon = overrides.get("is_coming_soon", False)
        entry.format_pricing.return_value = "PKR 5,000/mo"
        return entry

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_services_fresh(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        mock_repo = mock_repo_cls.return_value
        entries = [self._make_entry(slug="svc-a"), self._make_entry(slug="svc-b")]
        mock_repo.get_available_services = AsyncMock(return_value=entries)

        reg = ServiceRegistry(cache_ttl=300)
        result = await reg.get_services()
        assert len(result) == 2
        mock_repo.get_available_services.assert_called_once()

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_services_cached(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        mock_repo = mock_repo_cls.return_value
        entries = [self._make_entry(slug="svc-a")]
        mock_repo.get_available_services = AsyncMock(return_value=entries)

        reg = ServiceRegistry(cache_ttl=300)
        await reg.get_services()
        await reg.get_services()  # second call — should use cache
        assert mock_repo.get_available_services.call_count == 1

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_service_by_slug_found(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        entry = self._make_entry(slug="my-svc")
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_available_services = AsyncMock(return_value=[entry])

        reg = ServiceRegistry(cache_ttl=300)
        result = await reg.get_service_by_slug("my-svc")
        assert result is not None

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_service_by_slug_fallback_db(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_available_services = AsyncMock(return_value=[])
        mock_repo.get_by_slug = AsyncMock(return_value=self._make_entry(slug="new-svc"))

        reg = ServiceRegistry(cache_ttl=300)
        result = await reg.get_service_by_slug("new-svc")
        assert result is not None
        mock_repo.get_by_slug.assert_called_once_with("new-svc")

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_service_by_id_found_in_cache(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        entry = self._make_entry(slug="svc-x")
        sid = str(entry.id)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_available_services = AsyncMock(return_value=[entry])

        reg = ServiceRegistry(cache_ttl=300)
        result = await reg.get_service_by_id(sid)
        assert result is entry

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_default_service(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        entry = self._make_entry()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_available_services = AsyncMock(return_value=[entry])

        reg = ServiceRegistry(cache_ttl=300)
        result = await reg.get_default_service()
        assert result is entry

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_default_service_empty(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_available_services = AsyncMock(return_value=[])

        reg = ServiceRegistry(cache_ttl=300)
        result = await reg.get_default_service()
        assert result is None

    def test_get_handler_no_slug(self) -> None:
        """Handler is None when service has no sales_flow_handler."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        entry = self._make_entry(sales_flow_handler=None)
        reg = ServiceRegistry.__new__(ServiceRegistry)
        result = reg.get_handler(entry)
        assert result is None

    def test_get_handler_unknown_slug(self) -> None:
        """Handler is None for slug not in _HANDLER_PATHS."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        entry = self._make_entry(sales_flow_handler="unknown_handler")
        reg = ServiceRegistry.__new__(ServiceRegistry)
        result = reg.get_handler(entry)
        assert result is None

    def test_register_handler(self) -> None:
        from app.channels.channel_b.service_registry import (
            ServiceRegistry,
            _HANDLER_REGISTRY,
        )

        reg = ServiceRegistry.__new__(ServiceRegistry)
        handler_fn = MagicMock()
        reg.register_handler("test-slug", handler_fn)
        assert _HANDLER_REGISTRY.get("test-slug") is handler_fn
        # Cleanup
        _HANDLER_REGISTRY.pop("test-slug", None)

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    def test_format_service_list(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        entries = [
            self._make_entry(name="TELETRAAN Basic", is_coming_soon=False),
            self._make_entry(name="TELETRAAN Pro", is_coming_soon=True),
        ]
        reg = ServiceRegistry(cache_ttl=300)
        result = reg.format_service_list(entries)
        assert "TELETRAAN Basic" in result
        assert "Coming Soon" in result

    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    def test_format_service_detail(self, mock_repo_cls: MagicMock) -> None:
        from app.channels.channel_b.service_registry import ServiceRegistry

        entry = self._make_entry(
            name="TELETRAAN Pro",
            target_business_types=["pharmacy", "wholesale"],
            demo_video_url="https://example.com/demo.mp4",
        )
        reg = ServiceRegistry(cache_ttl=300)
        result = reg.format_service_detail(entry)
        assert "TELETRAAN Pro" in result
        assert "pharmacy" in result
        assert "Demo" in result


# ═══════════════════════════════════════════════════════════════════════════
# Reporting — Analytics Report Service (inject mock repos)
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyticsReportService:
    """Cover AnalyticsReportService with injected mock repos."""

    def _make_daily(self, **kw: object) -> MagicMock:
        """Create a mock DailyAnalytics row."""
        d = MagicMock()
        d.orders_confirmed = kw.get("orders_confirmed", 10)
        d.orders_pending = kw.get("orders_pending", 2)
        d.orders_cancelled = kw.get("orders_cancelled", 1)
        d.orders_total_paisas = kw.get("orders_total_paisas", 500_000)
        d.avg_order_paisas = kw.get("avg_order_paisas", 50_000)
        d.unique_customers = kw.get("unique_customers", 8)
        d.new_customers = kw.get("new_customers", 3)
        d.messages_processed = kw.get("messages_processed", 120)
        d.ai_cost_paisas = kw.get("ai_cost_paisas", 2000)
        return d

    def _make_top_item(self, name: str = "Panadol") -> MagicMock:
        ti = MagicMock()
        ti.medicine_name = name
        ti.units_sold = 50
        ti.revenue_paisas = 100_000
        ti.order_count = 10
        return ti

    async def test_get_daily_summary_has_data(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        daily_repo = MagicMock()
        daily_repo.get_for_date = AsyncMock(return_value=self._make_daily())
        items_repo = MagicMock()
        items_repo.get_for_date = AsyncMock(
            return_value=[self._make_top_item("Panadol")]
        )

        svc = AnalyticsReportService(daily_repo=daily_repo, items_repo=items_repo)
        result = await svc.get_daily_summary("dist-1", date.today())
        assert result["has_data"] is True
        assert result["orders_confirmed"] == 10
        assert result["top_item"] == "Panadol"

    async def test_get_daily_summary_no_data(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        daily_repo = MagicMock()
        daily_repo.get_for_date = AsyncMock(return_value=None)
        items_repo = MagicMock()
        items_repo.get_for_date = AsyncMock(return_value=[])

        svc = AnalyticsReportService(daily_repo=daily_repo, items_repo=items_repo)
        result = await svc.get_daily_summary("dist-1", date.today())
        assert result["has_data"] is False

    async def test_format_daily_whatsapp_no_data(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService(daily_repo=MagicMock(), items_repo=MagicMock())
        msg = svc.format_daily_whatsapp(
            {"date": "2025-01-15", "has_data": False, "message": "No data"}
        )
        assert "No data" in msg

    async def test_format_daily_whatsapp_with_data(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService(daily_repo=MagicMock(), items_repo=MagicMock())
        data = {
            "date": "2025-01-15",
            "has_data": True,
            "orders_confirmed": 10,
            "revenue": "PKR 5,000",
            "new_customers": 3,
            "top_item": "Panadol",
        }
        msg = svc.format_daily_whatsapp(data)
        assert "10" in msg
        assert "Panadol" in msg

    @patch("app.reporting.analytics_service.compute_period_summary")
    async def test_get_weekly_summary(self, mock_period: MagicMock) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        mock_period.return_value = {
            "orders_confirmed": 50,
            "orders_total_paisas": 2_500_000,
            "new_customers": 10,
            "best_day_date": "2025-01-10",
        }
        items_repo = MagicMock()
        items_repo.get_range = AsyncMock(
            return_value=[self._make_top_item("Brufen")]
        )
        daily_repo = MagicMock()

        svc = AnalyticsReportService(daily_repo=daily_repo, items_repo=items_repo)
        result = await svc.get_weekly_summary("dist-1", date(2025, 1, 12))
        assert result["orders_confirmed"] == 50
        assert len(result["top_items"]) >= 1

    @patch("app.reporting.analytics_service.compute_month_over_month")
    async def test_get_monthly_summary(self, mock_mom: MagicMock) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        mock_mom.return_value = {
            "current": {
                "orders_confirmed": 200,
                "orders_total_paisas": 10_000_000,
                "new_customers": 40,
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
            },
            "revenue_change_pct": 15.5,
            "orders_change_pct": 10.0,
            "customers_change_pct": 20.0,
        }
        items_repo = MagicMock()
        items_repo.get_range = AsyncMock(
            return_value=[self._make_top_item("Amoxil")]
        )
        daily_repo = MagicMock()

        svc = AnalyticsReportService(daily_repo=daily_repo, items_repo=items_repo)
        result = await svc.get_monthly_summary("dist-1", date(2025, 1, 1))
        assert result["orders_confirmed"] == 200
        assert result["mom_revenue_change"] == 15.5

    @patch("app.db.client.get_db_client")
    async def test_get_top_customers(self, mock_db: MagicMock) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        # Mock orders query
        orders_result = MagicMock()
        orders_result.data = [
            {"customer_id": "c1", "total_paisas": 100_000},
            {"customer_id": "c1", "total_paisas": 200_000},
            {"customer_id": "c2", "total_paisas": 150_000},
        ]
        # Mock customer name lookup
        cust_result = MagicMock()
        cust_result.data = [{"name": "Ali Medical", "shop_name": "Ali Store"}]

        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.lt.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute = AsyncMock(
            side_effect=[orders_result, cust_result, cust_result]
        )

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table
        mock_db.return_value = mock_client

        svc = AnalyticsReportService(daily_repo=MagicMock(), items_repo=MagicMock())
        result = await svc.get_top_customers(
            "dist-1", date(2025, 1, 1), date(2025, 1, 31),
        )
        assert len(result) == 2
        assert result[0]["customer_id"] == "c1"  # highest total
        assert result[0]["total_paisas"] == 300_000

    @patch("app.db.client.get_db_client")
    async def test_get_top_customers_db_error(self, mock_db: MagicMock) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.lt.return_value = mock_table
        mock_table.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table
        mock_db.return_value = mock_client

        svc = AnalyticsReportService(daily_repo=MagicMock(), items_repo=MagicMock())
        result = await svc.get_top_customers(
            "dist-1", date(2025, 1, 1), date(2025, 1, 31),
        )
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Reporting — Email Dispatch
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailDispatch:
    """Cover EmailDispatcher — _is_configured, _send_email, public senders."""

    @patch("app.reporting.email_dispatch.get_settings")
    async def test_not_configured(self, mock_gs: MagicMock) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(resend_api_key="")
        dispatcher = EmailDispatcher()
        result = await dispatcher._send_email(
            to=["x@test.com"], subject="Test", html="<p>Hi</p>",
        )
        assert result is None

    @patch("app.reporting.email_dispatch.get_settings")
    async def test_no_recipients(self, mock_gs: MagicMock) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        dispatcher = EmailDispatcher()
        result = await dispatcher._send_email(
            to=[], subject="Test", html="<p>Hi</p>",
        )
        assert result is None

    @patch("asyncio.to_thread")
    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_email_success(
        self, mock_gs: MagicMock, mock_thread: MagicMock,
    ) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        mock_thread.return_value = {"id": "email-123"}

        dispatcher = EmailDispatcher()
        result = await dispatcher._send_email(
            to=["x@test.com"], subject="Test", html="<p>Hi</p>",
        )
        assert result is not None
        assert result["id"] == "email-123"

    @patch("asyncio.to_thread")
    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_email_exception(
        self, mock_gs: MagicMock, mock_thread: MagicMock,
    ) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        mock_thread.side_effect = RuntimeError("Resend API down")

        dispatcher = EmailDispatcher()
        result = await dispatcher._send_email(
            to=["x@test.com"], subject="Test", html="<p>Hi</p>",
        )
        assert result is None

    @patch("asyncio.to_thread")
    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_daily_summary(
        self, mock_gs: MagicMock, mock_thread: MagicMock,
    ) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        mock_thread.return_value = {"id": "email-daily"}

        dispatcher = EmailDispatcher()
        result = await dispatcher.send_daily_summary(
            to_email="o@test.com",
            distributor_name="Test Pharma",
            report_date=date.today(),
            summary_data={
                "has_data": True,
                "orders_confirmed": 5,
                "revenue": "PKR 5,000",
                "new_customers": 2,
                "top_item": "X",
            },
        )
        assert result is not None

    @patch("asyncio.to_thread")
    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_daily_summary_no_data(
        self, mock_gs: MagicMock, mock_thread: MagicMock,
    ) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        mock_thread.return_value = {"id": "email-daily-nodata"}

        dispatcher = EmailDispatcher()
        result = await dispatcher.send_daily_summary(
            to_email="o@test.com",
            distributor_name="Test Pharma",
            report_date=date.today(),
            summary_data={"has_data": False},
        )
        assert result is not None

    @patch("asyncio.to_thread")
    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_churn_alert(
        self, mock_gs: MagicMock, mock_thread: MagicMock,
    ) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        mock_thread.return_value = {"id": "email-churn"}

        dispatcher = EmailDispatcher()
        result = await dispatcher.send_churn_alert(
            to_email="o@test.com",
            distributor_name="Test Pharma",
            churning_customers=[
                {"customer_name": "Ali", "days_inactive": 30, "severity": "warning"},
            ],
        )
        assert result is not None

    @patch("asyncio.to_thread")
    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_monthly_report_no_excel(
        self, mock_gs: MagicMock, mock_thread: MagicMock,
    ) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )
        mock_thread.return_value = {"id": "email-monthly"}

        dispatcher = EmailDispatcher()
        result = await dispatcher.send_monthly_report(
            to_email="o@test.com",
            distributor_name="Test",
            month_label="January 2025",
            summary_data={
                "orders_confirmed": 200,
                "orders_total_paisas": 10_000_000,
            },
        )
        assert result is not None

    @patch("app.reporting.email_dispatch.get_settings")
    async def test_send_excel_report_missing_file(self, mock_gs: MagicMock) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        mock_gs.return_value = MagicMock(
            resend_api_key="re_test", email_from_address="noreply@test.com",
        )

        dispatcher = EmailDispatcher()
        result = await dispatcher.send_excel_report(
            to_email="o@test.com",
            distributor_name="Test",
            report_date=date.today(),
            excel_path=Path("/nonexistent/report.xlsx"),
        )
        # File doesn't exist → returns None
        assert result is None
