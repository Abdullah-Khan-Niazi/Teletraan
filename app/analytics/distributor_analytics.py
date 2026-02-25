"""Distributor analytics — health metrics, subscription analytics.

Computes distributor-level business health indicators used by
the owner dashboard and weekly/monthly reports.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from loguru import logger

from app.db.models.analytics import DailyAnalytics
from app.db.repositories.daily_analytics_repo import DailyAnalyticsRepository


async def compute_period_summary(
    distributor_id: str,
    start_date: date,
    end_date: date,
    *,
    repo: DailyAnalyticsRepository | None = None,
) -> dict[str, Any]:
    """Aggregate daily analytics rows into a period summary.

    Used for weekly and monthly report generation.

    Args:
        distributor_id: Tenant scope.
        start_date: Period start (inclusive).
        end_date: Period end (inclusive).
        repo: Optional repo override for testing.

    Returns:
        Dict with aggregated metrics and derived stats.
    """
    from app.db.repositories.daily_analytics_repo import daily_analytics_repo
    r = repo or daily_analytics_repo

    rows = await r.get_range(distributor_id, start_date, end_date)
    if not rows:
        return _empty_summary(start_date, end_date)

    total_confirmed = sum(r.orders_confirmed for r in rows)
    total_pending = sum(r.orders_pending for r in rows)
    total_cancelled = sum(r.orders_cancelled for r in rows)
    total_revenue = sum(r.orders_total_paisas for r in rows)
    total_customers = sum(r.unique_customers for r in rows)
    total_new = sum(r.new_customers for r in rows)
    total_returning = sum(r.returning_customers for r in rows)
    total_payments = sum(r.payments_received_paisas for r in rows)
    total_messages = sum(r.messages_processed for r in rows)
    total_ai_cost = sum(r.ai_cost_paisas for r in rows)
    total_fallbacks = sum(r.fallback_responses for r in rows)

    avg_order = total_revenue // total_confirmed if total_confirmed else 0

    # Best day by revenue
    best_day = max(rows, key=lambda r: r.orders_total_paisas)

    # Response time average (weighted by messages_processed)
    weighted_ms = sum(r.avg_response_ms * r.messages_processed for r in rows)
    total_msgs_for_avg = sum(r.messages_processed for r in rows)
    avg_response_ms = weighted_ms // total_msgs_for_avg if total_msgs_for_avg else 0

    logger.info(
        "analytics.period_summary_computed",
        distributor_id=distributor_id,
        start=str(start_date),
        end=str(end_date),
        orders=total_confirmed,
        revenue_paisas=total_revenue,
    )

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "days": len(rows),
        "orders_confirmed": total_confirmed,
        "orders_pending": total_pending,
        "orders_cancelled": total_cancelled,
        "orders_total_paisas": total_revenue,
        "avg_order_paisas": avg_order,
        "unique_customers": total_customers,
        "new_customers": total_new,
        "returning_customers": total_returning,
        "payments_received_paisas": total_payments,
        "messages_processed": total_messages,
        "ai_cost_paisas": total_ai_cost,
        "fallback_responses": total_fallbacks,
        "avg_response_ms": avg_response_ms,
        "best_day_date": str(best_day.date),
        "best_day_revenue_paisas": best_day.orders_total_paisas,
        "best_day_orders": best_day.orders_confirmed,
    }


async def compute_month_over_month(
    distributor_id: str,
    current_month_start: date,
    *,
    repo: DailyAnalyticsRepository | None = None,
) -> dict[str, Any]:
    """Compare current month metrics against the previous month.

    Args:
        distributor_id: Tenant scope.
        current_month_start: First day of current month.
        repo: Optional repo override.

    Returns:
        Dict with current, previous, and percentage change values.
    """
    current_end = _month_end(current_month_start)
    prev_start = (current_month_start - timedelta(days=1)).replace(day=1)
    prev_end = current_month_start - timedelta(days=1)

    current = await compute_period_summary(
        distributor_id, current_month_start, current_end, repo=repo,
    )
    previous = await compute_period_summary(
        distributor_id, prev_start, prev_end, repo=repo,
    )

    def pct_change(cur: int, prev: int) -> float:
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round(((cur - prev) / prev) * 100, 1)

    return {
        "current": current,
        "previous": previous,
        "revenue_change_pct": pct_change(
            current["orders_total_paisas"],
            previous["orders_total_paisas"],
        ),
        "orders_change_pct": pct_change(
            current["orders_confirmed"],
            previous["orders_confirmed"],
        ),
        "customers_change_pct": pct_change(
            current["unique_customers"],
            previous["unique_customers"],
        ),
    }


async def compute_distributor_health_score(
    distributor_id: str,
    *,
    repo: DailyAnalyticsRepository | None = None,
) -> dict[str, Any]:
    """Compute a simple health score for a distributor.

    Score 0–100 based on:
    - Order consistency (30 pts): orders placed most days in the last 30d
    - Revenue trend (30 pts): this month vs last month
    - Error rate (20 pts): low fallback/error rate
    - Customer growth (20 pts): new customers trend

    Args:
        distributor_id: Tenant scope.
        repo: Optional repo override.

    Returns:
        Dict with ``score``, ``grade``, and breakdown.
    """
    from app.db.repositories.daily_analytics_repo import daily_analytics_repo
    r = repo or daily_analytics_repo

    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    rows = await r.get_range(distributor_id, thirty_days_ago, today)

    if not rows:
        return {"score": 0, "grade": "N/A", "breakdown": {}}

    # Order consistency: what fraction of days had confirmed orders
    days_with_orders = sum(1 for row in rows if row.orders_confirmed > 0)
    consistency_score = min(30, int((days_with_orders / 30) * 30))

    # Revenue trend: compare last 15d with prior 15d
    mid = today - timedelta(days=15)
    recent = [r for r in rows if r.date > mid]
    earlier = [r for r in rows if r.date <= mid]
    recent_rev = sum(r.orders_total_paisas for r in recent)
    earlier_rev = sum(r.orders_total_paisas for r in earlier)
    if earlier_rev > 0:
        rev_growth = (recent_rev - earlier_rev) / earlier_rev
        revenue_score = min(30, max(0, int(15 + rev_growth * 15)))
    else:
        revenue_score = 15 if recent_rev > 0 else 0

    # Error rate: lower fallbacks = higher score
    total_msgs = sum(r.messages_processed for r in rows)
    total_fallbacks = sum(r.fallback_responses for r in rows)
    if total_msgs > 0:
        error_rate = total_fallbacks / total_msgs
        error_score = max(0, int(20 * (1 - error_rate * 10)))
    else:
        error_score = 10

    # Customer growth
    total_new = sum(r.new_customers for r in rows)
    new_score = min(20, total_new * 2)

    total_score = consistency_score + revenue_score + error_score + new_score
    grade = _score_to_grade(total_score)

    logger.info(
        "analytics.health_score_computed",
        distributor_id=distributor_id,
        score=total_score,
        grade=grade,
    )

    return {
        "score": total_score,
        "grade": grade,
        "breakdown": {
            "consistency": consistency_score,
            "revenue_trend": revenue_score,
            "error_rate": error_score,
            "customer_growth": new_score,
        },
        "details": {
            "days_with_orders": days_with_orders,
            "total_messages": total_msgs,
            "total_fallbacks": total_fallbacks,
            "new_customers_30d": total_new,
        },
    }


# ── Helpers ─────────────────────────────────────────────────────────


def _score_to_grade(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 35:
        return "D"
    else:
        return "F"


def _month_end(first_day: date) -> date:
    """Get the last day of the month containing first_day."""
    if first_day.month == 12:
        return first_day.replace(day=31)
    return first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1)


def _empty_summary(start: date, end: date) -> dict:
    """Return an empty summary dict."""
    return {
        "start_date": str(start),
        "end_date": str(end),
        "days": 0,
        "orders_confirmed": 0,
        "orders_pending": 0,
        "orders_cancelled": 0,
        "orders_total_paisas": 0,
        "avg_order_paisas": 0,
        "unique_customers": 0,
        "new_customers": 0,
        "returning_customers": 0,
        "payments_received_paisas": 0,
        "messages_processed": 0,
        "ai_cost_paisas": 0,
        "fallback_responses": 0,
        "avg_response_ms": 0,
        "best_day_date": None,
        "best_day_revenue_paisas": 0,
        "best_day_orders": 0,
    }
