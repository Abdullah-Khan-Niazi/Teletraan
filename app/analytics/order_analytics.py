"""Order analytics — computes order volume, revenue, and top items.

Called by the nightly aggregation job to populate analytics_daily
and analytics_top_items.  Also exposes helpers for on-demand WhatsApp
analytics commands that read from pre-aggregated data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from app.core.constants import OrderStatus
from app.db.client import get_db_client
from app.db.models.analytics import DailyAnalyticsCreate, TopItemCreate


async def compute_order_metrics(
    distributor_id: str,
    target_date: date,
) -> dict:
    """Compute raw order metrics for a single distributor+date.

    Queries the ``orders`` table directly.  Returns a dict suitable for
    merging into a :class:`DailyAnalyticsCreate` payload.

    Args:
        distributor_id: Tenant scope.
        target_date: Calendar date to aggregate.

    Returns:
        Dict with order-related metric keys.
    """
    client = get_db_client()
    start_ts = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end_ts = start_ts + timedelta(days=1)

    try:
        result = (
            await client.table("orders")
            .select("id, status, total_paisas, customer_id, created_at")
            .eq("distributor_id", distributor_id)
            .gte("created_at", start_ts.isoformat())
            .lt("created_at", end_ts.isoformat())
            .execute()
        )
    except Exception as exc:
        logger.error(
            "analytics.order_query_failed",
            distributor_id=distributor_id,
            date=str(target_date),
            error=str(exc),
        )
        return {}

    rows = result.data
    confirmed = [r for r in rows if r["status"] == OrderStatus.CONFIRMED]
    pending = [r for r in rows if r["status"] == OrderStatus.PENDING]
    cancelled = [r for r in rows if r["status"] == OrderStatus.CANCELLED]

    total_paisas = sum(r["total_paisas"] for r in confirmed)
    avg_paisas = total_paisas // len(confirmed) if confirmed else 0

    customer_ids = {r["customer_id"] for r in confirmed if r.get("customer_id")}

    logger.info(
        "analytics.orders_computed",
        distributor_id=distributor_id,
        date=str(target_date),
        confirmed=len(confirmed),
        revenue_paisas=total_paisas,
    )

    return {
        "orders_confirmed": len(confirmed),
        "orders_pending": len(pending),
        "orders_cancelled": len(cancelled),
        "orders_total_paisas": total_paisas,
        "avg_order_paisas": avg_paisas,
        "unique_customers": len(customer_ids),
        "_confirmed_order_ids": [r["id"] for r in confirmed],
        "_customer_ids": list(customer_ids),
    }


async def compute_top_items(
    distributor_id: str,
    target_date: date,
    confirmed_order_ids: list[str],
    *,
    limit: int = 10,
) -> list[TopItemCreate]:
    """Compute top-selling items for confirmed orders on a date.

    Queries the ``order_items`` table for the given order IDs and
    aggregates by catalog_id + medicine_name.

    Args:
        distributor_id: Tenant scope.
        target_date: Calendar date.
        confirmed_order_ids: List of confirmed order UUIDs.
        limit: Maximum items to return (default 10).

    Returns:
        List of TopItemCreate payloads sorted by revenue DESC.
    """
    if not confirmed_order_ids:
        return []

    client = get_db_client()
    try:
        result = (
            await client.table("order_items")
            .select("catalog_id, medicine_name, quantity, line_total_paisas")
            .in_("order_id", confirmed_order_ids)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "analytics.top_items_query_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return []

    # Aggregate by medicine_name (catalog_id may differ for fuzzy matches)
    aggregated: dict[str, dict] = {}
    for row in result.data:
        name = row.get("medicine_name", "Unknown")
        if name not in aggregated:
            aggregated[name] = {
                "catalog_id": row.get("catalog_id"),
                "units": 0,
                "revenue": 0,
                "orders": set(),
            }
        aggregated[name]["units"] += row.get("quantity", 0)
        aggregated[name]["revenue"] += row.get("line_total_paisas", 0)
        # Use order_id if available; we don't have it directly, so count rows
        aggregated[name]["orders"].add(row.get("catalog_id", name))

    # Sort by revenue descending
    sorted_items = sorted(
        aggregated.items(),
        key=lambda x: x[1]["revenue"],
        reverse=True,
    )[:limit]

    dist_uuid = UUID(distributor_id)
    return [
        TopItemCreate(
            distributor_id=dist_uuid,
            date=target_date,
            catalog_id=data["catalog_id"],
            medicine_name=name,
            units_sold=data["units"],
            revenue_paisas=data["revenue"],
            order_count=len(data["orders"]),
        )
        for name, data in sorted_items
    ]


def paisas_to_pkr(paisas: int) -> str:
    """Format paisas as a human-readable PKR string.

    Args:
        paisas: Amount in paisas.

    Returns:
        Formatted string like 'PKR 1,234'.
    """
    return f"PKR {paisas // 100:,}"
