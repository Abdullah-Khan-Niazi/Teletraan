"""Reporting analytics service — combines analytics data for reports.

Provides formatted data for daily WhatsApp summaries, weekly Excel
reports, and monthly PDF reports.  Reads from pre-aggregated
analytics_daily and analytics_top_items tables.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger

from app.analytics.distributor_analytics import (
    compute_month_over_month,
    compute_period_summary,
)
from app.analytics.order_analytics import paisas_to_pkr
from app.db.models.analytics import DailyAnalytics, TopItem
from app.db.repositories.daily_analytics_repo import (
    DailyAnalyticsRepository,
    daily_analytics_repo,
)
from app.db.repositories.top_items_repo import (
    TopItemRepository,
    top_item_repo,
)


class AnalyticsReportService:
    """Combines analytics data into report-ready structures.

    Reads from pre-aggregated tables only — never computes live.
    """

    def __init__(
        self,
        *,
        daily_repo: DailyAnalyticsRepository | None = None,
        items_repo: TopItemRepository | None = None,
    ) -> None:
        self._daily = daily_repo or daily_analytics_repo
        self._items = items_repo or top_item_repo

    # ── Daily WhatsApp Summary ──────────────────────────────────────

    async def get_daily_summary(
        self,
        distributor_id: str,
        target_date: date,
    ) -> dict[str, Any]:
        """Build data for the nightly WhatsApp summary message.

        Args:
            distributor_id: Tenant scope.
            target_date: Calendar date.

        Returns:
            Dict suitable for formatting into the daily summary template.
        """
        daily = await self._daily.get_for_date(distributor_id, target_date)
        top_items = await self._items.get_for_date(
            distributor_id, target_date, limit=5,
        )

        if not daily:
            return {
                "date": str(target_date),
                "has_data": False,
                "message": "Aaj ka data abhi available nahi hai.",
            }

        top_item_name = top_items[0].medicine_name if top_items else "N/A"

        return {
            "date": str(target_date),
            "has_data": True,
            "orders_confirmed": daily.orders_confirmed,
            "orders_pending": daily.orders_pending,
            "orders_cancelled": daily.orders_cancelled,
            "revenue": paisas_to_pkr(daily.orders_total_paisas),
            "revenue_paisas": daily.orders_total_paisas,
            "avg_order": paisas_to_pkr(daily.avg_order_paisas),
            "unique_customers": daily.unique_customers,
            "new_customers": daily.new_customers,
            "top_item": top_item_name,
            "messages_processed": daily.messages_processed,
            "ai_cost": paisas_to_pkr(daily.ai_cost_paisas),
        }

    def format_daily_whatsapp(self, data: dict[str, Any]) -> str:
        """Format daily summary as a WhatsApp message.

        Args:
            data: Output from ``get_daily_summary()``.

        Returns:
            Formatted WhatsApp text message.
        """
        if not data.get("has_data"):
            return f"📊 *{data['date']}*\n{data.get('message', 'No data')}"

        return (
            f"📊 *Aaj* ({data['date']})\n"
            f"Orders: {data['orders_confirmed']} ✅ | "
            f"Revenue: {data['revenue']}\n"
            f"New customers: {data['new_customers']}\n"
            f"Top item: {data['top_item']}"
        )

    # ── Weekly Summary ──────────────────────────────────────────────

    async def get_weekly_summary(
        self,
        distributor_id: str,
        week_end: date,
    ) -> dict[str, Any]:
        """Build data for the weekly report.

        Args:
            distributor_id: Tenant scope.
            week_end: Last day of the week (typically Sunday).

        Returns:
            Dict with weekly aggregated metrics.
        """
        week_start = week_end - timedelta(days=6)
        summary = await compute_period_summary(
            distributor_id, week_start, week_end, repo=self._daily,
        )

        # Get top items across the week
        items = await self._items.get_range(
            distributor_id, week_start, week_end, limit=50,
        )
        # Aggregate items by medicine_name
        aggregated = _aggregate_top_items(items)

        summary["top_items"] = aggregated[:10]
        summary["week_start"] = str(week_start)
        summary["week_end"] = str(week_end)

        return summary

    def format_weekly_whatsapp(self, data: dict[str, Any]) -> str:
        """Format weekly summary as a WhatsApp message.

        Args:
            data: Output from ``get_weekly_summary()``.

        Returns:
            Formatted WhatsApp text message.
        """
        top_item = data["top_items"][0]["name"] if data.get("top_items") else "N/A"
        return (
            f"📊 *Is Hafta* ({data.get('week_start')} → {data.get('week_end')})\n"
            f"Orders: {data['orders_confirmed']} | "
            f"Revenue: {paisas_to_pkr(data['orders_total_paisas'])}\n"
            f"Best day: {data.get('best_day_date', 'N/A')}\n"
            f"Top item: {top_item}\n"
            f"New customers: {data['new_customers']}"
        )

    # ── Monthly Summary ─────────────────────────────────────────────

    async def get_monthly_summary(
        self,
        distributor_id: str,
        month_start: date,
    ) -> dict[str, Any]:
        """Build data for the monthly report.

        Includes month-over-month comparison.

        Args:
            distributor_id: Tenant scope.
            month_start: First day of the month.

        Returns:
            Dict with monthly metrics and MoM comparison.
        """
        mom = await compute_month_over_month(
            distributor_id, month_start, repo=self._daily,
        )

        # Get month's top items
        month_end = _month_end(month_start)
        items = await self._items.get_range(
            distributor_id, month_start, month_end, limit=100,
        )
        aggregated = _aggregate_top_items(items)

        return {
            **mom["current"],
            "top_items": aggregated[:10],
            "mom_revenue_change": mom["revenue_change_pct"],
            "mom_orders_change": mom["orders_change_pct"],
            "mom_customers_change": mom["customers_change_pct"],
        }

    def format_monthly_whatsapp(self, data: dict[str, Any]) -> str:
        """Format monthly summary for WhatsApp.

        Args:
            data: Output from ``get_monthly_summary()``.

        Returns:
            Formatted WhatsApp text message.
        """
        top_items_text = ""
        for i, item in enumerate(data.get("top_items", [])[:5], 1):
            top_items_text += (
                f"\n{i}. {item['name']} — "
                f"{item['units']} units — "
                f"{paisas_to_pkr(item['revenue'])}"
            )

        return (
            f"📊 *Is Mahina* ({data.get('start_date')} → {data.get('end_date')})\n"
            f"Orders: {data['orders_confirmed']} | "
            f"Revenue: {paisas_to_pkr(data['orders_total_paisas'])}\n"
            f"Month-over-month: {data.get('mom_revenue_change', 0):+.1f}%\n"
            f"\n💊 *Top Medicines*{top_items_text}"
        )

    # ── Top Customers ───────────────────────────────────────────────

    async def get_top_customers(
        self,
        distributor_id: str,
        start_date: date,
        end_date: date,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get top customers by order value for a period.

        Queries orders table directly (not pre-aggregated).

        Args:
            distributor_id: Tenant scope.
            start_date: Period start.
            end_date: Period end.
            limit: Maximum customers.

        Returns:
            List of customer dicts with name, order_count, total_paisas.
        """
        from app.db.client import get_db_client

        client = get_db_client()
        start_ts = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_ts = datetime.combine(
            end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc,
        )

        try:
            result = (
                await client.table("orders")
                .select("customer_id, total_paisas")
                .eq("distributor_id", distributor_id)
                .eq("status", "confirmed")
                .gte("created_at", start_ts.isoformat())
                .lt("created_at", end_ts.isoformat())
                .execute()
            )
        except Exception as exc:
            logger.error(
                "reporting.top_customers_failed",
                error=str(exc),
            )
            return []

        # Aggregate by customer_id
        customer_totals: dict[str, int] = {}
        customer_counts: dict[str, int] = {}
        for row in result.data:
            cid = row.get("customer_id")
            if not cid:
                continue
            customer_totals[cid] = customer_totals.get(cid, 0) + row.get("total_paisas", 0)
            customer_counts[cid] = customer_counts.get(cid, 0) + 1

        # Sort by total descending
        sorted_customers = sorted(
            customer_totals.items(), key=lambda x: x[1], reverse=True,
        )[:limit]

        # Fetch customer names
        customers = []
        for cid, total in sorted_customers:
            try:
                cust_result = (
                    await client.table("customers")
                    .select("name, shop_name")
                    .eq("id", cid)
                    .limit(1)
                    .execute()
                )
                name = cust_result.data[0].get("name", "Unknown") if cust_result.data else "Unknown"
                shop = cust_result.data[0].get("shop_name", "") if cust_result.data else ""
            except Exception:
                name = "Unknown"
                shop = ""

            customers.append({
                "customer_id": cid,
                "name": name,
                "shop_name": shop,
                "order_count": customer_counts.get(cid, 0),
                "total_paisas": total,
                "total_pkr": paisas_to_pkr(total),
            })

        return customers


# ── Helpers ─────────────────────────────────────────────────────────


def _aggregate_top_items(items: list[TopItem]) -> list[dict]:
    """Aggregate top item rows across multiple dates.

    Returns sorted list of dicts with name, units, revenue, orders.
    """
    agg: dict[str, dict] = {}
    for item in items:
        name = item.medicine_name
        if name not in agg:
            agg[name] = {"units": 0, "revenue": 0, "orders": 0}
        agg[name]["units"] += item.units_sold
        agg[name]["revenue"] += item.revenue_paisas
        agg[name]["orders"] += item.order_count

    return sorted(
        [
            {"name": name, **data}
            for name, data in agg.items()
        ],
        key=lambda x: x["revenue"],
        reverse=True,
    )


def _month_end(first_day: date) -> date:
    """Get the last day of the month."""
    if first_day.month == 12:
        return first_day.replace(day=31)
    return first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1)


# Module-level singleton
analytics_report_service = AnalyticsReportService()
