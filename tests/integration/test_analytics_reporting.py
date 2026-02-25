"""Tests for Phase 11 — analytics, reporting, email dispatch, scheduler jobs.

Covers:
- Analytics models (DailyAnalytics, TopItem, CustomerEvent)
- Order analytics (compute_order_metrics, compute_top_items, paisas_to_pkr)
- Customer analytics (compute_customer_metrics, detect_churning_customers)
- System analytics (compute_system_metrics, compute_gateway_summary)
- Distributor analytics (compute_period_summary, compute_month_over_month,
  compute_distributor_health_score)
- Aggregator (DailyAnalyticsAggregator)
- Reporting service (AnalyticsReportService, format methods)
- Report scheduler (get_report_date_range, should_send_daily_summary)
- Email dispatch (EmailDispatcher, HTML builders)
- Scheduler jobs (report_jobs)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.constants import OrderStatus
from app.db.models.analytics import (
    CustomerEvent,
    CustomerEventCreate,
    DailyAnalytics,
    DailyAnalyticsCreate,
    TopItem,
    TopItemCreate,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

_DIST_ID = uuid4()
_DIST_ID_STR = str(_DIST_ID)
_CUST_ID = uuid4()
_CUST_ID_2 = uuid4()
_TODAY = date.today()
_NOW = datetime.now(tz=timezone.utc)


def _mock_execute(data: list[dict] | None = None, count: int | None = None) -> AsyncMock:
    """Build an async mock that returns a Supabase-like response."""
    response = MagicMock()
    response.data = data or []
    response.count = count
    execute = AsyncMock(return_value=response)
    return execute


def _mock_db_chain(data: list[dict] | None = None, count: int | None = None) -> MagicMock:
    """Build a full Supabase mock chain returning given data."""
    mock = MagicMock()
    execute = _mock_execute(data, count)

    # Every chained method returns the same mock, and .execute is async
    for method in [
        "table", "select", "insert", "upsert", "delete", "update",
        "eq", "neq", "lt", "lte", "gt", "gte",
        "in_", "limit", "order",
    ]:
        getattr(mock, method).return_value = mock

    # not_ returns a sub-mock that also chains
    not_mock = MagicMock()
    not_mock.is_ = MagicMock(return_value=mock)
    mock.not_ = not_mock

    mock.execute = execute
    return mock


def _make_daily(
    *,
    dist_id: UUID = _DIST_ID,
    target_date: date = _TODAY,
    orders_confirmed: int = 10,
    orders_total_paisas: int = 500000,
    **kwargs: Any,
) -> DailyAnalytics:
    """Create a DailyAnalytics instance for tests."""
    defaults = {
        "id": uuid4(),
        "distributor_id": dist_id,
        "date": target_date,
        "orders_confirmed": orders_confirmed,
        "orders_pending": 2,
        "orders_cancelled": 1,
        "orders_total_paisas": orders_total_paisas,
        "avg_order_paisas": orders_total_paisas // max(orders_confirmed, 1),
        "unique_customers": 8,
        "new_customers": 3,
        "returning_customers": 5,
        "payments_received_paisas": 400000,
        "outstanding_delta_paisas": 100000,
        "messages_processed": 50,
        "voice_notes_count": 5,
        "ai_calls_count": 20,
        "ai_cost_paisas": 500,
        "fallback_responses": 2,
        "avg_response_ms": 350,
        "fuzzy_match_count": 8,
        "unlisted_requests": 3,
        "out_of_stock_events": 1,
        "computed_at": _NOW,
    }
    defaults.update(kwargs)
    return DailyAnalytics(**defaults)


def _make_top_item(
    name: str = "Paracetamol 500mg",
    units: int = 50,
    revenue: int = 100000,
    orders: int = 8,
) -> TopItem:
    """Create a TopItem instance."""
    return TopItem(
        id=uuid4(),
        distributor_id=_DIST_ID,
        date=_TODAY,
        catalog_id=uuid4(),
        medicine_name=name,
        units_sold=units,
        revenue_paisas=revenue,
        order_count=orders,
    )


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS MODELS
# ═══════════════════════════════════════════════════════════════════


class TestAnalyticsModels:
    """Test analytics Pydantic models."""

    def test_daily_analytics_create(self) -> None:
        data = DailyAnalyticsCreate(
            distributor_id=_DIST_ID,
            date=_TODAY,
            orders_confirmed=5,
            orders_total_paisas=250000,
        )
        assert data.distributor_id == _DIST_ID
        assert data.date == _TODAY
        assert data.orders_confirmed == 5
        assert data.orders_pending == 0  # default

    def test_top_item_create(self) -> None:
        data = TopItemCreate(
            distributor_id=_DIST_ID,
            date=_TODAY,
            medicine_name="Amoxicillin 250mg",
            units_sold=20,
            revenue_paisas=60000,
            order_count=5,
        )
        assert data.medicine_name == "Amoxicillin 250mg"
        assert data.units_sold == 20

    def test_customer_event_create(self) -> None:
        data = CustomerEventCreate(
            distributor_id=_DIST_ID,
            customer_id=_CUST_ID,
            event_type="churn_risk",
            event_data={"level": "warning", "days_inactive": 25},
        )
        assert data.event_type == "churn_risk"
        assert data.event_data["level"] == "warning"

    def test_daily_analytics_from_dict(self) -> None:
        d = _make_daily()
        assert d.orders_confirmed == 10
        assert d.orders_total_paisas == 500000

    def test_top_item_defaults(self) -> None:
        item = TopItemCreate(
            distributor_id=_DIST_ID,
            date=_TODAY,
            medicine_name="Test",
        )
        assert item.units_sold == 0
        assert item.revenue_paisas == 0
        assert item.order_count == 0


# ═══════════════════════════════════════════════════════════════════
# ORDER ANALYTICS
# ═══════════════════════════════════════════════════════════════════


class TestOrderAnalytics:
    """Tests for order_analytics module."""

    @pytest.mark.asyncio
    async def test_compute_order_metrics_basic(self) -> None:
        mock_client = _mock_db_chain(data=[
            {"id": "o1", "status": OrderStatus.CONFIRMED, "total_paisas": 100000, "customer_id": "c1", "created_at": _NOW.isoformat()},
            {"id": "o2", "status": OrderStatus.CONFIRMED, "total_paisas": 200000, "customer_id": "c2", "created_at": _NOW.isoformat()},
            {"id": "o3", "status": OrderStatus.PENDING, "total_paisas": 50000, "customer_id": "c3", "created_at": _NOW.isoformat()},
            {"id": "o4", "status": OrderStatus.CANCELLED, "total_paisas": 80000, "customer_id": "c1", "created_at": _NOW.isoformat()},
        ])

        with patch("app.analytics.order_analytics.get_db_client", return_value=mock_client):
            from app.analytics.order_analytics import compute_order_metrics

            result = await compute_order_metrics(_DIST_ID_STR, _TODAY)

        assert result["orders_confirmed"] == 2
        assert result["orders_pending"] == 1
        assert result["orders_cancelled"] == 1
        assert result["orders_total_paisas"] == 300000
        assert result["avg_order_paisas"] == 150000
        assert result["unique_customers"] == 2
        assert len(result["_confirmed_order_ids"]) == 2

    @pytest.mark.asyncio
    async def test_compute_order_metrics_empty(self) -> None:
        mock_client = _mock_db_chain(data=[])

        with patch("app.analytics.order_analytics.get_db_client", return_value=mock_client):
            from app.analytics.order_analytics import compute_order_metrics

            result = await compute_order_metrics(_DIST_ID_STR, _TODAY)

        assert result["orders_confirmed"] == 0
        assert result["orders_total_paisas"] == 0
        assert result["avg_order_paisas"] == 0

    @pytest.mark.asyncio
    async def test_compute_order_metrics_query_failure(self) -> None:
        mock_client = _mock_db_chain()
        mock_client.execute = AsyncMock(side_effect=Exception("DB error"))

        with patch("app.analytics.order_analytics.get_db_client", return_value=mock_client):
            from app.analytics.order_analytics import compute_order_metrics

            result = await compute_order_metrics(_DIST_ID_STR, _TODAY)

        assert result == {}

    @pytest.mark.asyncio
    async def test_compute_top_items(self) -> None:
        mock_client = _mock_db_chain(data=[
            {"catalog_id": str(uuid4()), "medicine_name": "Paracetamol", "quantity": 10, "line_total_paisas": 50000},
            {"catalog_id": str(uuid4()), "medicine_name": "Paracetamol", "quantity": 5, "line_total_paisas": 25000},
            {"catalog_id": str(uuid4()), "medicine_name": "Amoxicillin", "quantity": 3, "line_total_paisas": 30000},
        ])

        with patch("app.analytics.order_analytics.get_db_client", return_value=mock_client):
            from app.analytics.order_analytics import compute_top_items

            result = await compute_top_items(_DIST_ID_STR, _TODAY, ["o1", "o2"])

        assert len(result) == 2
        # Paracetamol has highest revenue
        assert result[0].medicine_name == "Paracetamol"
        assert result[0].units_sold == 15
        assert result[0].revenue_paisas == 75000

    @pytest.mark.asyncio
    async def test_compute_top_items_empty_ids(self) -> None:
        from app.analytics.order_analytics import compute_top_items

        result = await compute_top_items(_DIST_ID_STR, _TODAY, [])
        assert result == []

    def test_paisas_to_pkr(self) -> None:
        from app.analytics.order_analytics import paisas_to_pkr

        assert paisas_to_pkr(0) == "PKR 0"
        assert paisas_to_pkr(100) == "PKR 1"
        assert paisas_to_pkr(198500) == "PKR 1,985"
        assert paisas_to_pkr(10000000) == "PKR 100,000"


# ═══════════════════════════════════════════════════════════════════
# CUSTOMER ANALYTICS
# ═══════════════════════════════════════════════════════════════════


class TestCustomerAnalytics:
    """Tests for customer_analytics module."""

    @pytest.mark.asyncio
    async def test_compute_customer_metrics_new_and_returning(self) -> None:
        """New customer has 0 prior orders, returning has 1+."""
        # First customer: no prior orders → new
        # Second customer: 1 prior order → returning
        responses = [
            MagicMock(data=[], count=0),  # c1 → new
            MagicMock(data=[{"id": "x"}], count=1),  # c2 → returning
        ]
        mock_client = MagicMock()
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.eq.return_value = mock_client
        mock_client.lt.return_value = mock_client
        mock_client.limit.return_value = mock_client
        mock_client.execute = AsyncMock(side_effect=responses)

        with patch("app.analytics.customer_analytics.get_db_client", return_value=mock_client):
            from app.analytics.customer_analytics import compute_customer_metrics

            result = await compute_customer_metrics(
                _DIST_ID_STR, _TODAY, ["c1", "c2"],
            )

        assert result["new_customers"] == 1
        assert result["returning_customers"] == 1

    @pytest.mark.asyncio
    async def test_compute_customer_metrics_empty(self) -> None:
        from app.analytics.customer_analytics import compute_customer_metrics

        result = await compute_customer_metrics(_DIST_ID_STR, _TODAY, [])
        assert result == {"new_customers": 0, "returning_customers": 0}

    @pytest.mark.asyncio
    async def test_detect_churning_customers(self) -> None:
        """Detect warning (21+) and critical (42+) churn."""
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)
        fifty_days_ago = today - timedelta(days=50)

        mock_client = _mock_db_chain(data=[
            {"id": str(_CUST_ID), "name": "Ali", "last_order_at": thirty_days_ago.isoformat()},
            {"id": str(_CUST_ID_2), "name": "Bilal", "last_order_at": fifty_days_ago.isoformat()},
        ])

        with patch("app.analytics.customer_analytics.get_db_client", return_value=mock_client):
            from app.analytics.customer_analytics import detect_churning_customers

            events = await detect_churning_customers(_DIST_ID_STR)

        assert len(events) == 2
        # 30 days → warning
        warning_events = [e for e in events if e.event_data.get("level") == "warning"]
        critical_events = [e for e in events if e.event_data.get("level") == "critical"]
        assert len(warning_events) == 1
        assert len(critical_events) == 1

    @pytest.mark.asyncio
    async def test_detect_churning_no_inactive(self) -> None:
        """No churn if customers ordered recently."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        mock_client = _mock_db_chain(data=[
            {"id": str(_CUST_ID), "name": "Recent", "last_order_at": yesterday.isoformat()},
        ])

        with patch("app.analytics.customer_analytics.get_db_client", return_value=mock_client):
            from app.analytics.customer_analytics import detect_churning_customers

            events = await detect_churning_customers(_DIST_ID_STR)

        assert len(events) == 0


# ═══════════════════════════════════════════════════════════════════
# SYSTEM ANALYTICS
# ═══════════════════════════════════════════════════════════════════


class TestSystemAnalytics:
    """Tests for system_analytics module."""

    @pytest.mark.asyncio
    async def test_compute_system_metrics(self) -> None:
        ai_data = [
            {"ai_provider": "gemini", "ai_tokens_used": 100, "ai_cost_paisas": 50, "duration_ms": 200},
            {"ai_provider": "gemini", "ai_tokens_used": 200, "ai_cost_paisas": 100, "duration_ms": 300},
        ]
        session_data = [
            {"event_type": "message.processed", "duration_ms": 250},
            {"event_type": "message.processed", "duration_ms": 350},
            {"event_type": "voice_note.received", "duration_ms": None},
            {"event_type": "fallback.triggered", "duration_ms": None},
        ]

        # Two separate queries: AI metrics + session metrics
        responses = [
            MagicMock(data=ai_data),
            MagicMock(data=session_data),
        ]
        mock_client = MagicMock()
        for method in ["table", "select", "eq", "gte", "lt", "limit", "order"]:
            getattr(mock_client, method).return_value = mock_client
        mock_client.not_ = MagicMock()
        mock_client.not_.is_ = MagicMock(return_value=mock_client)
        mock_client.execute = AsyncMock(side_effect=responses)

        with patch("app.analytics.system_analytics.get_db_client", return_value=mock_client):
            from app.analytics.system_analytics import compute_system_metrics

            result = await compute_system_metrics(_DIST_ID_STR, _TODAY)

        assert result["ai_calls_count"] == 2
        assert result["ai_cost_paisas"] == 150
        assert result["messages_processed"] == 2
        assert result["voice_notes_count"] == 1
        assert result["fallback_responses"] == 1
        assert result["avg_response_ms"] == 300  # (250+350)/2

    @pytest.mark.asyncio
    async def test_compute_gateway_summary(self) -> None:
        gateway_data = [
            {"payment_gateway": "jazzcash", "duration_ms": 500},
            {"payment_gateway": "jazzcash", "duration_ms": 700},
            {"payment_gateway": "easypaisa", "duration_ms": 300},
        ]
        mock_client = _mock_db_chain(data=gateway_data)

        with patch("app.analytics.system_analytics.get_db_client", return_value=mock_client):
            from app.analytics.system_analytics import compute_gateway_summary

            result = await compute_gateway_summary(_DIST_ID_STR, _TODAY, _TODAY)

        assert len(result) == 2
        jc = [g for g in result if g["gateway"] == "jazzcash"][0]
        assert jc["count"] == 2
        assert jc["avg_ms"] == 600


# ═══════════════════════════════════════════════════════════════════
# DISTRIBUTOR ANALYTICS
# ═══════════════════════════════════════════════════════════════════


class TestDistributorAnalytics:
    """Tests for distributor_analytics module."""

    @pytest.mark.asyncio
    async def test_compute_period_summary(self) -> None:
        daily1 = _make_daily(
            target_date=_TODAY - timedelta(days=1),
            orders_confirmed=5,
            orders_total_paisas=250000,
        )
        daily2 = _make_daily(
            target_date=_TODAY,
            orders_confirmed=8,
            orders_total_paisas=400000,
        )

        mock_repo = AsyncMock()
        mock_repo.get_range = AsyncMock(return_value=[daily1, daily2])

        from app.analytics.distributor_analytics import compute_period_summary

        result = await compute_period_summary(
            _DIST_ID_STR,
            _TODAY - timedelta(days=1),
            _TODAY,
            repo=mock_repo,
        )

        assert result["orders_confirmed"] == 13
        assert result["orders_total_paisas"] == 650000
        assert result["days"] == 2
        assert result["best_day_orders"] == 8

    @pytest.mark.asyncio
    async def test_compute_period_summary_empty(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_range = AsyncMock(return_value=[])

        from app.analytics.distributor_analytics import compute_period_summary

        result = await compute_period_summary(
            _DIST_ID_STR, _TODAY, _TODAY, repo=mock_repo,
        )

        assert result["orders_confirmed"] == 0
        assert result["days"] == 0

    @pytest.mark.asyncio
    async def test_compute_month_over_month(self) -> None:
        # Current month: 10 confirmed, 500k revenue
        # Previous month: 5 confirmed, 250k revenue
        current_daily = _make_daily(orders_confirmed=10, orders_total_paisas=500000)
        prev_daily = _make_daily(orders_confirmed=5, orders_total_paisas=250000)

        mock_repo = AsyncMock()
        mock_repo.get_range = AsyncMock(side_effect=[
            [current_daily],  # current month
            [prev_daily],  # previous month
        ])

        from app.analytics.distributor_analytics import compute_month_over_month

        current_month_start = _TODAY.replace(day=1)
        result = await compute_month_over_month(
            _DIST_ID_STR, current_month_start, repo=mock_repo,
        )

        assert result["revenue_change_pct"] == 100.0  # doubled
        assert result["orders_change_pct"] == 100.0  # doubled

    @pytest.mark.asyncio
    async def test_compute_distributor_health_score(self) -> None:
        # Create 15 daily rows with varying data
        rows = []
        for i in range(15):
            rows.append(_make_daily(
                target_date=_TODAY - timedelta(days=i),
                orders_confirmed=3 if i < 10 else 0,
                orders_total_paisas=150000 if i < 10 else 0,
                new_customers=1,
                messages_processed=10,
                fallback_responses=0,
            ))

        mock_repo = AsyncMock()
        mock_repo.get_range = AsyncMock(return_value=rows)

        from app.analytics.distributor_analytics import compute_distributor_health_score

        result = await compute_distributor_health_score(
            _DIST_ID_STR, repo=mock_repo,
        )

        assert 0 <= result["score"] <= 100
        assert result["grade"] in ("A", "B", "C", "D", "F")
        assert "consistency" in result["breakdown"]
        assert "revenue_trend" in result["breakdown"]

    @pytest.mark.asyncio
    async def test_health_score_no_data(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_range = AsyncMock(return_value=[])

        from app.analytics.distributor_analytics import compute_distributor_health_score

        result = await compute_distributor_health_score(
            _DIST_ID_STR, repo=mock_repo,
        )

        assert result["score"] == 0
        assert result["grade"] == "N/A"


# ═══════════════════════════════════════════════════════════════════
# AGGREGATOR
# ═══════════════════════════════════════════════════════════════════


class TestAggregator:
    """Tests for the DailyAnalyticsAggregator."""

    @pytest.mark.asyncio
    async def test_compute_for_date(self) -> None:
        """Aggregator orchestrates order + customer + system metrics."""
        mock_daily_repo = AsyncMock()
        mock_daily_repo.upsert = AsyncMock(return_value=_make_daily())
        mock_items_repo = AsyncMock()
        mock_items_repo.replace_for_date = AsyncMock(return_value=[])
        mock_events_repo = AsyncMock()

        from app.analytics.aggregator import DailyAnalyticsAggregator

        agg = DailyAnalyticsAggregator(
            daily_repo=mock_daily_repo,
            items_repo=mock_items_repo,
            events_repo=mock_events_repo,
        )

        with (
            patch("app.analytics.order_analytics.get_db_client", return_value=_mock_db_chain(data=[
                {"id": "o1", "status": "confirmed", "total_paisas": 100000, "customer_id": "c1", "created_at": _NOW.isoformat()},
            ])),
            patch("app.analytics.customer_analytics.get_db_client", return_value=_mock_db_chain(data=[], count=0)),
            patch("app.analytics.system_analytics.get_db_client", return_value=_mock_db_chain(data=[])),
        ):
            await agg.compute_for_date(_DIST_ID_STR, _TODAY)

        mock_daily_repo.upsert.assert_awaited_once()
        # Top items query: order_items query
        # items repo might not be called if no order items data
        assert mock_daily_repo.upsert.call_count == 1

    @pytest.mark.asyncio
    async def test_compute_all_distributors(self) -> None:
        """Processes all active distributors."""
        mock_daily_repo = AsyncMock()
        mock_daily_repo.upsert = AsyncMock(return_value=_make_daily())
        mock_items_repo = AsyncMock()
        mock_items_repo.replace_for_date = AsyncMock(return_value=[])
        mock_events_repo = AsyncMock()

        from app.analytics.aggregator import DailyAnalyticsAggregator

        agg = DailyAnalyticsAggregator(
            daily_repo=mock_daily_repo,
            items_repo=mock_items_repo,
            events_repo=mock_events_repo,
        )

        mock_client = _mock_db_chain(data=[
            {"id": _DIST_ID_STR},
        ])

        with (
            patch("app.db.client.get_db_client", return_value=mock_client),
            patch("app.analytics.order_analytics.get_db_client", return_value=_mock_db_chain(data=[])),
            patch("app.analytics.customer_analytics.get_db_client", return_value=_mock_db_chain(data=[], count=0)),
            patch("app.analytics.system_analytics.get_db_client", return_value=_mock_db_chain(data=[])),
        ):
            count = await agg.compute_all_distributors(_TODAY)

        assert count == 1

    @pytest.mark.asyncio
    async def test_run_churn_detection(self) -> None:
        """Churn detection processes all distributors."""
        mock_events_repo = AsyncMock()
        mock_events_repo.create = AsyncMock()

        from app.analytics.aggregator import DailyAnalyticsAggregator

        agg = DailyAnalyticsAggregator(events_repo=mock_events_repo)

        dist_client = _mock_db_chain(data=[{"id": _DIST_ID_STR}])
        churn_client = _mock_db_chain(data=[])

        with (
            patch("app.db.client.get_db_client", return_value=dist_client),
            patch("app.analytics.customer_analytics.get_db_client", return_value=churn_client),
        ):
            total = await agg.run_churn_detection()

        assert total == 0  # no churning customers found


# ═══════════════════════════════════════════════════════════════════
# REPORTING SERVICE
# ═══════════════════════════════════════════════════════════════════


class TestAnalyticsReportService:
    """Tests for AnalyticsReportService."""

    @pytest.mark.asyncio
    async def test_get_daily_summary_with_data(self) -> None:
        daily = _make_daily()
        top_items = [_make_top_item()]

        mock_daily_repo = AsyncMock()
        mock_daily_repo.get_for_date = AsyncMock(return_value=daily)
        mock_items_repo = AsyncMock()
        mock_items_repo.get_for_date = AsyncMock(return_value=top_items)

        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService(
            daily_repo=mock_daily_repo, items_repo=mock_items_repo,
        )
        result = await svc.get_daily_summary(_DIST_ID_STR, _TODAY)

        assert result["has_data"] is True
        assert result["orders_confirmed"] == 10
        assert result["top_item"] == "Paracetamol 500mg"

    @pytest.mark.asyncio
    async def test_get_daily_summary_no_data(self) -> None:
        mock_daily_repo = AsyncMock()
        mock_daily_repo.get_for_date = AsyncMock(return_value=None)
        mock_items_repo = AsyncMock()
        mock_items_repo.get_for_date = AsyncMock(return_value=[])

        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService(
            daily_repo=mock_daily_repo, items_repo=mock_items_repo,
        )
        result = await svc.get_daily_summary(_DIST_ID_STR, _TODAY)

        assert result["has_data"] is False

    def test_format_daily_whatsapp_with_data(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService()
        data = {
            "has_data": True,
            "date": str(_TODAY),
            "orders_confirmed": 10,
            "revenue": "PKR 5,000",
            "new_customers": 3,
            "top_item": "Paracetamol",
        }
        msg = svc.format_daily_whatsapp(data)
        assert "10" in msg
        assert "PKR 5,000" in msg
        assert "Paracetamol" in msg

    def test_format_daily_whatsapp_no_data(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService()
        data = {"has_data": False, "date": str(_TODAY), "message": "No data"}
        msg = svc.format_daily_whatsapp(data)
        assert "No data" in msg

    @pytest.mark.asyncio
    async def test_get_weekly_summary(self) -> None:
        daily = _make_daily()
        mock_daily_repo = AsyncMock()
        mock_daily_repo.get_range = AsyncMock(return_value=[daily])
        mock_items_repo = AsyncMock()
        mock_items_repo.get_range = AsyncMock(return_value=[_make_top_item()])

        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService(
            daily_repo=mock_daily_repo, items_repo=mock_items_repo,
        )
        result = await svc.get_weekly_summary(_DIST_ID_STR, _TODAY)

        assert "orders_confirmed" in result
        assert "top_items" in result
        assert len(result["top_items"]) == 1

    def test_format_weekly_whatsapp(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService()
        data = {
            "week_start": str(_TODAY - timedelta(days=6)),
            "week_end": str(_TODAY),
            "orders_confirmed": 50,
            "orders_total_paisas": 2500000,
            "best_day_date": str(_TODAY),
            "new_customers": 10,
            "top_items": [{"name": "Paracetamol", "units": 100, "revenue": 500000}],
        }
        msg = svc.format_weekly_whatsapp(data)
        assert "50" in msg
        assert "Paracetamol" in msg

    @pytest.mark.asyncio
    async def test_get_monthly_summary(self) -> None:
        daily = _make_daily()
        mock_daily_repo = AsyncMock()
        mock_daily_repo.get_range = AsyncMock(return_value=[daily])
        mock_items_repo = AsyncMock()
        mock_items_repo.get_range = AsyncMock(return_value=[_make_top_item()])

        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService(
            daily_repo=mock_daily_repo, items_repo=mock_items_repo,
        )
        month_start = _TODAY.replace(day=1)
        result = await svc.get_monthly_summary(_DIST_ID_STR, month_start)

        assert "orders_confirmed" in result
        assert "mom_revenue_change" in result
        assert "top_items" in result

    def test_format_monthly_whatsapp(self) -> None:
        from app.reporting.analytics_service import AnalyticsReportService

        svc = AnalyticsReportService()
        data = {
            "start_date": str(_TODAY.replace(day=1)),
            "end_date": str(_TODAY),
            "orders_confirmed": 200,
            "orders_total_paisas": 10000000,
            "mom_revenue_change": 15.5,
            "mom_orders_change": 10.0,
            "mom_customers_change": 5.0,
            "new_customers": 20,
            "top_items": [
                {"name": "Paracetamol", "units": 500, "revenue": 2500000},
                {"name": "Amoxicillin", "units": 300, "revenue": 1500000},
            ],
        }
        msg = svc.format_monthly_whatsapp(data)
        assert "200" in msg
        assert "+15.5%" in msg
        assert "Paracetamol" in msg


# ═══════════════════════════════════════════════════════════════════
# REPORT SCHEDULER HELPERS
# ═══════════════════════════════════════════════════════════════════


class TestReportScheduler:
    """Tests for report_scheduler module."""

    def test_get_report_date_range_daily_morning(self) -> None:
        from app.core.constants import ExcelReportSchedule
        from app.reporting.report_scheduler import get_report_date_range

        ref = date(2025, 3, 15)
        start, end = get_report_date_range(
            ExcelReportSchedule.DAILY_MORNING, ref,
        )
        assert start == date(2025, 3, 14)
        assert end == date(2025, 3, 14)

    def test_get_report_date_range_daily_evening(self) -> None:
        from app.core.constants import ExcelReportSchedule
        from app.reporting.report_scheduler import get_report_date_range

        ref = date(2025, 3, 15)
        start, end = get_report_date_range(
            ExcelReportSchedule.DAILY_EVENING, ref,
        )
        assert start == date(2025, 3, 15)
        assert end == date(2025, 3, 15)

    def test_get_report_date_range_weekly(self) -> None:
        from app.core.constants import ExcelReportSchedule
        from app.reporting.report_scheduler import get_report_date_range

        ref = date(2025, 3, 15)  # Saturday
        start, end = get_report_date_range(
            ExcelReportSchedule.WEEKLY, ref,
        )
        assert end == date(2025, 3, 14)
        assert start == date(2025, 3, 8)

    @pytest.mark.asyncio
    async def test_should_send_daily_summary_default_true(self) -> None:
        mock_client = _mock_db_chain(data=[
            {"metadata": {}},
        ])

        with patch("app.reporting.report_scheduler.get_db_client", return_value=mock_client):
            from app.reporting.report_scheduler import should_send_daily_summary

            result = await should_send_daily_summary(_DIST_ID_STR)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_send_daily_summary_opted_out(self) -> None:
        mock_client = _mock_db_chain(data=[
            {"metadata": {"notifications": {"daily_summary": False}}},
        ])

        with patch("app.reporting.report_scheduler.get_db_client", return_value=mock_client):
            from app.reporting.report_scheduler import should_send_daily_summary

            result = await should_send_daily_summary(_DIST_ID_STR)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_send_on_error_defaults_true(self) -> None:
        mock_client = _mock_db_chain()
        mock_client.execute = AsyncMock(side_effect=Exception("DB down"))

        with patch("app.reporting.report_scheduler.get_db_client", return_value=mock_client):
            from app.reporting.report_scheduler import should_send_daily_summary

            result = await should_send_daily_summary(_DIST_ID_STR)

        assert result is True


# ═══════════════════════════════════════════════════════════════════
# EMAIL DISPATCH
# ═══════════════════════════════════════════════════════════════════


class TestEmailDispatch:
    """Tests for EmailDispatcher."""

    def test_not_configured_without_api_key(self) -> None:
        mock_settings = MagicMock()
        mock_settings.resend_api_key = None
        mock_settings.email_from_address = "test@teletraan.pk"

        with patch("app.reporting.email_dispatch.get_settings", return_value=mock_settings):
            from app.reporting.email_dispatch import EmailDispatcher

            dispatcher = EmailDispatcher()
            assert dispatcher._is_configured() is False

    def test_configured_with_api_key(self) -> None:
        mock_settings = MagicMock()
        mock_settings.resend_api_key = "re_test_12345"
        mock_settings.email_from_address = "test@teletraan.pk"

        with patch("app.reporting.email_dispatch.get_settings", return_value=mock_settings):
            from app.reporting.email_dispatch import EmailDispatcher

            dispatcher = EmailDispatcher()
            assert dispatcher._is_configured() is True

    @pytest.mark.asyncio
    async def test_send_daily_summary_unconfigured(self) -> None:
        mock_settings = MagicMock()
        mock_settings.resend_api_key = None
        mock_settings.email_from_address = "test@teletraan.pk"

        with patch("app.reporting.email_dispatch.get_settings", return_value=mock_settings):
            from app.reporting.email_dispatch import EmailDispatcher

            dispatcher = EmailDispatcher()
            result = await dispatcher.send_daily_summary(
                to_email="owner@test.com",
                distributor_name="Test Pharma",
                report_date=_TODAY,
                summary_data={"has_data": True, "orders_confirmed": 5},
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_send_daily_summary_configured(self) -> None:
        mock_settings = MagicMock()
        mock_settings.resend_api_key = "re_test_12345"
        mock_settings.email_from_address = "noreply@teletraan.pk"

        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        with (
            patch("app.reporting.email_dispatch.get_settings", return_value=mock_settings),
            patch.dict("sys.modules", {"resend": mock_resend}),
        ):
            from app.reporting.email_dispatch import EmailDispatcher

            dispatcher = EmailDispatcher()
            dispatcher._configured = True

            result = await dispatcher._send_email(
                to=["owner@test.com"],
                subject="Test",
                html="<p>Test</p>",
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_send_churn_alert(self) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        dispatcher = EmailDispatcher()
        dispatcher._configured = False

        result = await dispatcher.send_churn_alert(
            to_email="owner@test.com",
            distributor_name="Test",
            churning_customers=[],
        )
        # Empty list → returns None immediately
        assert result is None

    @pytest.mark.asyncio
    async def test_file_to_attachment_missing_file(self) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        result = await EmailDispatcher._file_to_attachment(
            Path("/nonexistent/file.xlsx"),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_send_excel_report_no_file(self) -> None:
        from app.reporting.email_dispatch import EmailDispatcher

        dispatcher = EmailDispatcher()
        dispatcher._configured = True

        result = await dispatcher.send_excel_report(
            to_email="owner@test.com",
            distributor_name="Test",
            report_date=_TODAY,
            excel_path=Path("/nonexistent/file.xlsx"),
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# HTML BUILDERS
# ═══════════════════════════════════════════════════════════════════


class TestHTMLBuilders:
    """Test HTML template builder functions."""

    def test_html_wrapper(self) -> None:
        from app.reporting.email_dispatch import _html_wrapper

        html = _html_wrapper("Test Title", "<p>Body</p>")
        assert "Test Title" in html
        assert "<p>Body</p>" in html
        assert "<!DOCTYPE html>" in html
        assert "TELETRAAN" in html

    def test_build_daily_summary_html(self) -> None:
        from app.reporting.email_dispatch import _build_daily_summary_html

        data = {
            "date": str(_TODAY),
            "orders_confirmed": 10,
            "revenue": "PKR 5,000",
            "new_customers": 3,
            "orders_pending": 2,
            "orders_cancelled": 1,
            "avg_order": "PKR 500",
            "unique_customers": 8,
            "top_item": "Paracetamol",
            "messages_processed": 50,
            "ai_cost": "PKR 5",
        }
        html = _build_daily_summary_html(data, "Test Pharma")
        assert "Test Pharma" in html
        assert "10" in html

    def test_build_no_data_html(self) -> None:
        from app.reporting.email_dispatch import _build_no_data_html

        html = _build_no_data_html(_TODAY, "Test Pharma")
        assert "Test Pharma" in html
        assert "nahi mila" in html

    def test_build_churn_alert_html(self) -> None:
        from app.reporting.email_dispatch import _build_churn_alert_html

        html = _build_churn_alert_html("Test Pharma", [
            {"customer_name": "Ali", "days_inactive": 30, "severity": "warning"},
            {"customer_name": "Bilal", "days_inactive": 50, "severity": "critical"},
        ])
        assert "Ali" in html
        assert "Bilal" in html
        assert "WARNING" in html
        assert "CRITICAL" in html

    def test_esc_html(self) -> None:
        from app.reporting.email_dispatch import _esc

        assert _esc("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" or \
               "&lt;script&gt;" in _esc("<script>alert('xss')</script>")


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER JOBS
# ═══════════════════════════════════════════════════════════════════


class TestReportJobs:
    """Tests for scheduler report jobs."""

    @pytest.mark.asyncio
    async def test_run_daily_analytics_aggregation(self) -> None:
        mock_aggregator = AsyncMock()
        mock_aggregator.compute_all_distributors = AsyncMock(return_value=3)

        with patch(
            "app.analytics.aggregator.aggregator",
            mock_aggregator,
        ):
            from app.scheduler.jobs.report_jobs import run_daily_analytics_aggregation

            await run_daily_analytics_aggregation()

        mock_aggregator.compute_all_distributors.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_daily_analytics_aggregation_error(self) -> None:
        """Job must not raise on failure."""
        with patch(
            "app.analytics.aggregator.aggregator",
            side_effect=Exception("import fail"),
        ):
            from app.scheduler.jobs.report_jobs import run_daily_analytics_aggregation

            # Should not raise
            await run_daily_analytics_aggregation()

    @pytest.mark.asyncio
    async def test_run_daily_order_summary(self) -> None:
        mock_client = _mock_db_chain(data=[
            {
                "id": _DIST_ID_STR,
                "business_name": "Test",
                "owner_phone": "+923001234567",
                "whatsapp_phone_number_id": "12345",
            },
        ])

        # Second call: notifications_log check (empty = not sent today)
        notifications_mock = _mock_db_chain(data=[])

        mock_settings = MagicMock()
        mock_settings.resend_api_key = None

        mock_notifier = MagicMock()
        mock_notifier.send_text = AsyncMock(return_value="msg_id")

        mock_report_service = MagicMock()
        mock_report_service.get_daily_summary = AsyncMock(return_value={
            "has_data": True,
            "orders_confirmed": 5,
        })
        mock_report_service.format_daily_whatsapp = MagicMock(return_value="Summary text")

        # Multiple DB calls — first gets distributors, then per-distributor checks
        call_count = [0]
        original_execute = mock_client.execute

        async def multi_execute():
            call_count[0] += 1
            if call_count[0] == 1:
                # Distributors list
                return MagicMock(data=[{
                    "id": _DIST_ID_STR,
                    "business_name": "Test",
                    "owner_phone": "+923001234567",
                    "whatsapp_phone_number_id": "12345",
                }])
            else:
                # notifications_log check — empty
                return MagicMock(data=[])

        mock_client.execute = multi_execute

        with (
            patch("app.db.client.get_db_client", return_value=mock_client),
            patch("app.reporting.report_scheduler.get_db_client", return_value=_mock_db_chain(data=[{"metadata": {}}])),
            patch("app.notifications.whatsapp_notifier.whatsapp_notifier", mock_notifier),
            patch("app.reporting.analytics_service.analytics_report_service", mock_report_service),
            patch("app.core.config.get_settings", return_value=mock_settings),
        ):
            from app.scheduler.jobs.report_jobs import run_daily_order_summary

            await run_daily_order_summary()

    @pytest.mark.asyncio
    async def test_run_daily_order_summary_no_raise(self) -> None:
        """Job never raises even if everything fails."""
        mock_client = MagicMock()
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.eq.return_value = mock_client
        mock_client.execute = AsyncMock(side_effect=Exception("DB down"))

        with patch("app.db.client.get_db_client", return_value=mock_client):
            from app.scheduler.jobs.report_jobs import run_daily_order_summary

            # Must not raise
            await run_daily_order_summary()

    @pytest.mark.asyncio
    async def test_run_churn_detection_no_raise(self) -> None:
        """Churn detection job must not raise."""
        mock_aggregator = MagicMock()
        mock_aggregator.run_churn_detection = AsyncMock(return_value=0)

        mock_client = _mock_db_chain(data=[])

        with (
            patch("app.analytics.aggregator.aggregator", mock_aggregator),
            patch("app.db.client.get_db_client", return_value=mock_client),
        ):
            from app.scheduler.jobs.report_jobs import run_churn_detection

            await run_churn_detection()

    @pytest.mark.asyncio
    async def test_run_excel_dispatch_morning(self) -> None:
        """Excel dispatch morning should not raise."""
        mock_client = _mock_db_chain(data=[])

        with (
            patch("app.db.client.get_db_client", return_value=mock_client),
            patch("app.reporting.report_scheduler.get_db_client", return_value=mock_client),
        ):
            from app.scheduler.jobs.report_jobs import run_excel_report_dispatch_morning

            await run_excel_report_dispatch_morning()

    @pytest.mark.asyncio
    async def test_run_weekly_report_no_raise(self) -> None:
        """Weekly report job must not raise."""
        mock_client = _mock_db_chain(data=[])

        with (
            patch("app.db.client.get_db_client", return_value=mock_client),
            patch("app.reporting.report_scheduler.get_db_client", return_value=mock_client),
        ):
            from app.scheduler.jobs.report_jobs import run_weekly_report

            await run_weekly_report()

    @pytest.mark.asyncio
    async def test_run_monthly_report_no_raise(self) -> None:
        """Monthly report job must not raise."""
        mock_client = _mock_db_chain(data=[])

        with patch("app.db.client.get_db_client", return_value=mock_client):
            from app.scheduler.jobs.report_jobs import run_monthly_report

            await run_monthly_report()


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER SETUP — JOB REGISTRATION
# ═══════════════════════════════════════════════════════════════════


class TestSchedulerSetup:
    """Tests that analytics/report jobs are registered in setup.py."""

    def test_analytics_jobs_registered(self) -> None:
        """Analytics aggregate and churn detection should be registered."""
        from unittest.mock import call

        mock_settings = MagicMock()
        mock_settings.scheduler_timezone = "Asia/Karachi"
        mock_settings.enable_analytics = True
        mock_settings.enable_excel_reports = True
        mock_settings.enable_inventory_sync = False
        mock_settings.inventory_sync_interval_minutes = 120
        mock_settings.session_cleanup_interval_hours = 6
        mock_settings.reminder_check_interval_hours = 12

        with patch("app.scheduler.setup.get_settings", return_value=mock_settings):
            from app.scheduler.setup import create_scheduler

            scheduler = create_scheduler()

        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "analytics_aggregate" in job_ids
        assert "churn_detection" in job_ids
        assert "daily_order_summary" in job_ids
        assert "weekly_report" in job_ids
        assert "monthly_report" in job_ids
        assert "excel_dispatch_morning" in job_ids
        assert "excel_dispatch_evening" in job_ids

    def test_analytics_jobs_disabled(self) -> None:
        """Analytics jobs not registered when enable_analytics=False."""
        mock_settings = MagicMock()
        mock_settings.scheduler_timezone = "Asia/Karachi"
        mock_settings.enable_analytics = False
        mock_settings.enable_excel_reports = True
        mock_settings.enable_inventory_sync = False
        mock_settings.inventory_sync_interval_minutes = 120
        mock_settings.session_cleanup_interval_hours = 6
        mock_settings.reminder_check_interval_hours = 12

        with patch("app.scheduler.setup.get_settings", return_value=mock_settings):
            from app.scheduler.setup import create_scheduler

            scheduler = create_scheduler()

        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "analytics_aggregate" not in job_ids
        assert "churn_detection" not in job_ids
        # Report jobs should still be registered
        assert "daily_order_summary" in job_ids

    def test_excel_jobs_disabled(self) -> None:
        """Excel dispatch not registered when enable_excel_reports=False."""
        mock_settings = MagicMock()
        mock_settings.scheduler_timezone = "Asia/Karachi"
        mock_settings.enable_analytics = True
        mock_settings.enable_excel_reports = False
        mock_settings.enable_inventory_sync = False
        mock_settings.inventory_sync_interval_minutes = 120
        mock_settings.session_cleanup_interval_hours = 6
        mock_settings.reminder_check_interval_hours = 12

        with patch("app.scheduler.setup.get_settings", return_value=mock_settings):
            from app.scheduler.setup import create_scheduler

            scheduler = create_scheduler()

        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "excel_dispatch_morning" not in job_ids
        assert "excel_dispatch_evening" not in job_ids
        # Other report jobs still present
        assert "daily_order_summary" in job_ids


# ═══════════════════════════════════════════════════════════════════
# AGGREGATE TOP ITEMS HELPER
# ═══════════════════════════════════════════════════════════════════


class TestAggregateTopItems:
    """Test the _aggregate_top_items helper in analytics_service."""

    def test_aggregate_merges_same_name(self) -> None:
        from app.reporting.analytics_service import _aggregate_top_items

        items = [
            _make_top_item("Paracetamol 500mg", units=10, revenue=50000, orders=3),
            _make_top_item("Paracetamol 500mg", units=15, revenue=75000, orders=5),
            _make_top_item("Amoxicillin 250mg", units=8, revenue=40000, orders=2),
        ]
        result = _aggregate_top_items(items)
        assert len(result) == 2
        # Paracetamol should be first (higher total revenue)
        assert result[0]["name"] == "Paracetamol 500mg"
        assert result[0]["units"] == 25
        assert result[0]["revenue"] == 125000
        assert result[0]["orders"] == 8

    def test_aggregate_empty(self) -> None:
        from app.reporting.analytics_service import _aggregate_top_items

        result = _aggregate_top_items([])
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# MONTH END HELPER
# ═══════════════════════════════════════════════════════════════════


class TestMonthEnd:
    """Test _month_end helper."""

    def test_month_end_jan(self) -> None:
        from app.reporting.analytics_service import _month_end

        assert _month_end(date(2025, 1, 1)) == date(2025, 1, 31)

    def test_month_end_feb_non_leap(self) -> None:
        from app.reporting.analytics_service import _month_end

        assert _month_end(date(2025, 2, 1)) == date(2025, 2, 28)

    def test_month_end_dec(self) -> None:
        from app.reporting.analytics_service import _month_end

        assert _month_end(date(2025, 12, 1)) == date(2025, 12, 31)
