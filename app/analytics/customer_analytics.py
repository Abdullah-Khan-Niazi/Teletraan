"""Customer analytics — retention, new vs returning, churn detection.

Computes customer lifecycle metrics for the daily aggregation and
provides churn detection utilities run weekly.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from app.db.client import get_db_client
from app.db.models.analytics import CustomerEventCreate


# ═══════════════════════════════════════════════════════════════════
# Churn thresholds
# ═══════════════════════════════════════════════════════════════════

CHURN_THRESHOLDS = {
    "warning": 21,    # days since last order → send gentle alert
    "critical": 42,   # days since last order → strong churn risk alert
}


async def compute_customer_metrics(
    distributor_id: str,
    target_date: date,
    customer_ids: list[str],
) -> dict:
    """Compute customer-related metrics for a single date.

    Determines how many customers are new (first order ever) vs
    returning (ordered before target_date).

    Args:
        distributor_id: Tenant scope.
        target_date: Calendar date.
        customer_ids: Customer UUIDs who placed confirmed orders today.

    Returns:
        Dict with ``new_customers`` and ``returning_customers``.
    """
    if not customer_ids:
        return {"new_customers": 0, "returning_customers": 0}

    client = get_db_client()
    start_ts = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)

    new_count = 0
    returning_count = 0

    for cid in customer_ids:
        try:
            result = (
                await client.table("orders")
                .select("id", count="exact")
                .eq("distributor_id", distributor_id)
                .eq("customer_id", cid)
                .lt("created_at", start_ts.isoformat())
                .limit(1)
                .execute()
            )
            prior_orders = result.count if result.count is not None else len(result.data)
            if prior_orders == 0:
                new_count += 1
            else:
                returning_count += 1
        except Exception as exc:
            logger.warning(
                "analytics.customer_check_failed",
                customer_id=cid,
                error=str(exc),
            )
            # Count as returning to be conservative
            returning_count += 1

    logger.info(
        "analytics.customers_computed",
        distributor_id=distributor_id,
        date=str(target_date),
        new=new_count,
        returning=returning_count,
    )

    return {
        "new_customers": new_count,
        "returning_customers": returning_count,
    }


async def detect_churning_customers(
    distributor_id: str,
) -> list[CustomerEventCreate]:
    """Identify customers at churn risk.

    Compares each active customer's last order date against
    churn thresholds.  Returns CustomerEventCreate payloads
    for customers who exceed the warning or critical threshold.

    Args:
        distributor_id: Tenant scope.

    Returns:
        List of CustomerEventCreate payloads to persist.
    """
    client = get_db_client()
    today = date.today()
    dist_uuid = UUID(distributor_id)
    events: list[CustomerEventCreate] = []

    try:
        # Get all customers for this distributor with their last order date
        customers = (
            await client.table("customers")
            .select("id, name, last_order_at")
            .eq("distributor_id", distributor_id)
            .not_.is_("last_order_at", "null")
            .execute()
        )
    except Exception as exc:
        logger.error(
            "analytics.churn_query_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return []

    for row in customers.data:
        last_order_str = row.get("last_order_at")
        if not last_order_str:
            continue

        try:
            last_order = datetime.fromisoformat(last_order_str).date()
        except (ValueError, TypeError):
            continue

        days_inactive = (today - last_order).days
        customer_id = UUID(row["id"])

        if days_inactive >= CHURN_THRESHOLDS["critical"]:
            events.append(CustomerEventCreate(
                distributor_id=dist_uuid,
                customer_id=customer_id,
                event_type="churn_risk",
                event_data={
                    "level": "critical",
                    "days_inactive": days_inactive,
                    "customer_name": row.get("name", "Unknown"),
                    "last_order_date": str(last_order),
                },
            ))
            logger.info(
                "analytics.churn_critical",
                customer_id=str(customer_id),
                days_inactive=days_inactive,
            )
        elif days_inactive >= CHURN_THRESHOLDS["warning"]:
            events.append(CustomerEventCreate(
                distributor_id=dist_uuid,
                customer_id=customer_id,
                event_type="churn_risk",
                event_data={
                    "level": "warning",
                    "days_inactive": days_inactive,
                    "customer_name": row.get("name", "Unknown"),
                    "last_order_date": str(last_order),
                },
            ))
            logger.info(
                "analytics.churn_warning",
                customer_id=str(customer_id),
                days_inactive=days_inactive,
            )

    logger.info(
        "analytics.churn_detection_complete",
        distributor_id=distributor_id,
        events_created=len(events),
    )

    return events
