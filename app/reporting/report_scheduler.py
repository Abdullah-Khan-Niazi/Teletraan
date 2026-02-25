"""Report scheduler — determines when and what reports to generate.

Reads ``bot_configuration.excel_report_schedule`` to decide the cadence
for each distributor and provides helper functions for the scheduler
jobs to call.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.core.constants import ExcelReportSchedule
from app.db.client import get_db_client


async def get_distributors_needing_reports(
    schedule: ExcelReportSchedule,
) -> list[dict[str, Any]]:
    """Get distributors whose report is due for the given schedule.

    Checks ``bot_configuration.excel_report_schedule`` to find
    distributors matching the requested cadence.

    Args:
        schedule: The schedule frequency to match.

    Returns:
        List of dicts with distributor_id, business_name, owner_email.
    """
    client = get_db_client()
    try:
        result = (
            await client.table("bot_configuration")
            .select("distributor_id, excel_report_schedule")
            .eq("excel_report_schedule", schedule.value)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "reporting.schedule_query_failed",
            schedule=schedule.value,
            error=str(exc),
        )
        return []

    dist_ids = [row["distributor_id"] for row in result.data]
    if not dist_ids:
        return []

    # Fetch distributor details
    distributors = []
    for dist_id in dist_ids:
        try:
            dist_result = (
                await client.table("distributors")
                .select("id, business_name, email, owner_name, is_active")
                .eq("id", dist_id)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if dist_result.data:
                d = dist_result.data[0]
                distributors.append({
                    "distributor_id": d["id"],
                    "business_name": d.get("business_name", ""),
                    "owner_name": d.get("owner_name", ""),
                    "owner_email": d.get("email"),
                })
        except Exception as exc:
            logger.warning(
                "reporting.distributor_fetch_failed",
                distributor_id=dist_id,
                error=str(exc),
            )

    logger.info(
        "reporting.distributors_for_schedule",
        schedule=schedule.value,
        count=len(distributors),
    )

    return distributors


def get_report_date_range(
    schedule: ExcelReportSchedule,
    reference_date: date | None = None,
) -> tuple[date, date]:
    """Calculate the date range for a report schedule.

    Args:
        schedule: Report cadence.
        reference_date: Optional reference date (default: today).

    Returns:
        Tuple of (start_date, end_date).
    """
    ref = reference_date or date.today()

    if schedule == ExcelReportSchedule.DAILY_MORNING:
        # Yesterday's data
        yesterday = ref - timedelta(days=1)
        return (yesterday, yesterday)

    elif schedule == ExcelReportSchedule.DAILY_EVENING:
        # Today's data so far
        return (ref, ref)

    elif schedule == ExcelReportSchedule.WEEKLY:
        # Last 7 days (Mon-Sun if triggered on Monday)
        end = ref - timedelta(days=1)
        start = end - timedelta(days=6)
        return (start, end)

    elif schedule == ExcelReportSchedule.REALTIME:
        # Real-time reports cover today
        return (ref, ref)

    else:
        return (ref, ref)


async def should_send_daily_summary(
    distributor_id: str,
) -> bool:
    """Check if a distributor should receive the nightly WhatsApp summary.

    All active distributors receive the daily summary unless they've
    explicitly disabled ``notifications.daily_summary`` in their
    bot configuration metadata.

    Args:
        distributor_id: Tenant scope.

    Returns:
        True if the summary should be sent.
    """
    client = get_db_client()
    try:
        result = (
            await client.table("bot_configuration")
            .select("metadata")
            .eq("distributor_id", distributor_id)
            .limit(1)
            .execute()
        )
        if result.data:
            meta = result.data[0].get("metadata", {}) or {}
            notifications = meta.get("notifications", {})
            if notifications.get("daily_summary") is False:
                return False
        return True
    except Exception as exc:
        logger.warning(
            "reporting.summary_check_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return True  # Default to sending
