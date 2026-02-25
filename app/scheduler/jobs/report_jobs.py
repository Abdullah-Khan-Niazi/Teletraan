"""Report and analytics scheduler jobs.

Contains APScheduler jobs for:
- ``run_daily_analytics_aggregation`` — aggregate analytics for all distributors.
- ``run_daily_order_summary`` — send nightly WhatsApp summary (20:00 PKT).
- ``run_weekly_report`` — send weekly report email (Monday 09:00 PKT).
- ``run_monthly_report`` — send monthly report email (1st of month 07:00 PKT).
- ``run_churn_detection`` — detect churning customers (Monday 08:00 PKT).
- ``run_excel_report_dispatch`` — send Excel reports per schedule.

Job functions **never raise exceptions** to the scheduler.
Timezone: Asia/Karachi (PKT, UTC+5) — cron triggers set in setup.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from loguru import logger


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS AGGREGATION JOB (every 60 min)
# ═══════════════════════════════════════════════════════════════════


async def run_daily_analytics_aggregation() -> None:
    """Aggregate analytics for all active distributors for today.

    Called every 60 minutes.  Delegates to the aggregator which
    is idempotent (upserts daily rows).

    This function never raises.
    """
    logger.info("scheduler.analytics_aggregate.start")

    try:
        from app.analytics.aggregator import aggregator

        today = date.today()
        processed = await aggregator.compute_all_distributors(today)

        logger.info(
            "scheduler.analytics_aggregate.complete",
            date=str(today),
            distributors_processed=processed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.analytics_aggregate.fatal",
            error=str(exc),
        )


# ═══════════════════════════════════════════════════════════════════
# DAILY WHATSAPP SUMMARY (cron 20:00 PKT)
# ═══════════════════════════════════════════════════════════════════


async def run_daily_order_summary() -> None:
    """Send nightly WhatsApp order summary to all opted-in distributors.

    For each active distributor that has not opted out of the daily
    summary, fetches today's analytics and sends a formatted WhatsApp
    message to the owner.

    Idempotency: checks notifications_log for today's summary.

    This function never raises.
    """
    logger.info("scheduler.daily_summary.start")

    try:
        from app.core.config import get_settings
        from app.db.client import get_db_client
        from app.notifications.whatsapp_notifier import whatsapp_notifier
        from app.reporting.analytics_service import analytics_report_service
        from app.reporting.report_scheduler import should_send_daily_summary
        from app.whatsapp.message_types import build_text_message

        settings = get_settings()
        client = get_db_client()
        today = date.today()

        # Get all active distributors
        dist_result = (
            await client.table("distributors")
            .select("id, business_name, owner_phone, whatsapp_phone_number_id")
            .eq("is_active", True)
            .execute()
        )

        sent = 0
        skipped = 0
        failed = 0

        for dist in dist_result.data:
            dist_id = dist["id"]
            try:
                # Check opt-in
                should_send = await should_send_daily_summary(dist_id)
                if not should_send:
                    skipped += 1
                    continue

                # Check idempotency — already sent today?
                existing = (
                    await client.table("notifications_log")
                    .select("id")
                    .eq("distributor_id", dist_id)
                    .eq("notification_type", "daily_summary")
                    .gte("created_at", datetime.combine(
                        today, datetime.min.time(), tzinfo=timezone.utc,
                    ).isoformat())
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    skipped += 1
                    continue

                # Generate summary
                summary = await analytics_report_service.get_daily_summary(
                    dist_id, today,
                )
                message = analytics_report_service.format_daily_whatsapp(summary)

                # Send via WhatsApp
                phone_number_id = dist.get("whatsapp_phone_number_id")
                owner_phone = dist.get("owner_phone")
                if phone_number_id and owner_phone:
                    await whatsapp_notifier.send_text(
                        phone_number_id=phone_number_id,
                        to=owner_phone,
                        text=message,
                        distributor_id=dist_id,
                        notification_type="daily_summary",
                    )
                    sent += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error(
                    "scheduler.daily_summary.distributor_failed",
                    distributor_id=dist_id,
                    error=str(exc),
                )
                failed += 1

        logger.info(
            "scheduler.daily_summary.complete",
            sent=sent,
            skipped=skipped,
            failed=failed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.daily_summary.fatal",
            error=str(exc),
        )


# ═══════════════════════════════════════════════════════════════════
# WEEKLY REPORT EMAIL (cron Monday 09:00 PKT)
# ═══════════════════════════════════════════════════════════════════


async def run_weekly_report() -> None:
    """Send weekly analytics report email to distributors with WEEKLY schedule.

    Fetches last week's summary and sends a WhatsApp message and
    optionally an email if the owner has an email address.

    This function never raises.
    """
    logger.info("scheduler.weekly_report.start")

    try:
        from app.core.constants import ExcelReportSchedule
        from app.db.client import get_db_client
        from app.notifications.whatsapp_notifier import whatsapp_notifier
        from app.reporting.analytics_service import analytics_report_service
        from app.reporting.email_dispatch import email_dispatcher
        from app.reporting.excel_generator import get_monthly_report_path
        from app.reporting.report_scheduler import (
            get_distributors_needing_reports,
            get_report_date_range,
        )

        start_date, end_date = get_report_date_range(ExcelReportSchedule.WEEKLY)
        distributors = await get_distributors_needing_reports(
            ExcelReportSchedule.WEEKLY,
        )

        sent = 0
        failed = 0

        for dist in distributors:
            dist_id = dist["distributor_id"]
            try:
                # Weekly analytics summary
                summary = await analytics_report_service.get_weekly_summary(
                    dist_id, end_date,
                )
                wa_message = analytics_report_service.format_weekly_whatsapp(
                    summary,
                )

                # Send WhatsApp summary
                client = get_db_client()
                dist_info = (
                    await client.table("distributors")
                    .select("owner_phone, whatsapp_phone_number_id")
                    .eq("id", dist_id)
                    .limit(1)
                    .execute()
                )
                if dist_info.data:
                    info = dist_info.data[0]
                    phone_number_id = info.get("whatsapp_phone_number_id")
                    owner_phone = info.get("owner_phone")
                    if phone_number_id and owner_phone:
                        await whatsapp_notifier.send_text(
                            phone_number_id=phone_number_id,
                            to=owner_phone,
                            text=wa_message,
                            distributor_id=dist_id,
                            notification_type="weekly_report",
                        )

                # Send email with Excel attachment if email provided
                owner_email = dist.get("owner_email")
                if owner_email:
                    now = datetime.now(tz=timezone.utc)
                    excel_path = await get_monthly_report_path(
                        dist_id, now.year, now.month,
                    )
                    if excel_path:
                        await email_dispatcher.send_excel_report(
                            to_email=owner_email,
                            distributor_name=dist.get("business_name", ""),
                            report_date=end_date,
                            excel_path=excel_path,
                            period_label="Weekly",
                        )

                sent += 1
            except Exception as exc:
                logger.error(
                    "scheduler.weekly_report.distributor_failed",
                    distributor_id=dist_id,
                    error=str(exc),
                )
                failed += 1

        logger.info(
            "scheduler.weekly_report.complete",
            sent=sent,
            failed=failed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.weekly_report.fatal",
            error=str(exc),
        )


# ═══════════════════════════════════════════════════════════════════
# MONTHLY REPORT EMAIL (cron 1st of month 07:00 PKT)
# ═══════════════════════════════════════════════════════════════════


async def run_monthly_report() -> None:
    """Send monthly analytics report to all active distributors.

    Generates a monthly summary with month-over-month comparison
    and attaches the Excel order log if available.

    This function never raises.
    """
    logger.info("scheduler.monthly_report.start")

    try:
        from app.db.client import get_db_client
        from app.reporting.analytics_service import analytics_report_service
        from app.reporting.email_dispatch import email_dispatcher
        from app.reporting.excel_generator import get_monthly_report_path

        today = date.today()
        # Report for last month
        if today.month == 1:
            last_month_start = today.replace(year=today.year - 1, month=12, day=1)
        else:
            last_month_start = today.replace(month=today.month - 1, day=1)

        month_label = last_month_start.strftime("%B %Y")

        client = get_db_client()
        dist_result = (
            await client.table("distributors")
            .select("id, business_name, email, owner_phone, whatsapp_phone_number_id")
            .eq("is_active", True)
            .execute()
        )

        sent = 0
        failed = 0

        for dist in dist_result.data:
            dist_id = dist["id"]
            try:
                summary = await analytics_report_service.get_monthly_summary(
                    dist_id, last_month_start,
                )

                # WhatsApp message
                wa_message = analytics_report_service.format_monthly_whatsapp(
                    summary,
                )
                phone_number_id = dist.get("whatsapp_phone_number_id")
                owner_phone = dist.get("owner_phone")
                if phone_number_id and owner_phone:
                    from app.notifications.whatsapp_notifier import whatsapp_notifier

                    await whatsapp_notifier.send_text(
                        phone_number_id=phone_number_id,
                        to=owner_phone,
                        text=wa_message,
                        distributor_id=dist_id,
                        notification_type="monthly_report",
                    )

                # Email with Excel attachment
                owner_email = dist.get("email")
                if owner_email:
                    excel_path = await get_monthly_report_path(
                        dist_id,
                        last_month_start.year,
                        last_month_start.month,
                    )
                    await email_dispatcher.send_monthly_report(
                        to_email=owner_email,
                        distributor_name=dist.get("business_name", ""),
                        month_label=month_label,
                        summary_data=summary,
                        excel_path=excel_path,
                    )

                sent += 1
            except Exception as exc:
                logger.error(
                    "scheduler.monthly_report.distributor_failed",
                    distributor_id=dist_id,
                    error=str(exc),
                )
                failed += 1

        logger.info(
            "scheduler.monthly_report.complete",
            sent=sent,
            failed=failed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.monthly_report.fatal",
            error=str(exc),
        )


# ═══════════════════════════════════════════════════════════════════
# CHURN DETECTION (cron Monday 08:00 PKT)
# ═══════════════════════════════════════════════════════════════════


async def run_churn_detection() -> None:
    """Detect churning customers and send alerts.

    Delegages to the aggregator's churn detection which
    creates customer events and optionally notifies the
    distributor via email.

    This function never raises.
    """
    logger.info("scheduler.churn_detection.start")

    try:
        from app.analytics.aggregator import aggregator
        from app.db.client import get_db_client
        from app.reporting.email_dispatch import email_dispatcher

        total_events = await aggregator.run_churn_detection()

        logger.info(
            "scheduler.churn_detection.events_created",
            total_events=total_events,
        )

        # Send email alerts for distributors with recent churn events
        client = get_db_client()
        alerts_sent = 0

        # Fetch today's churn events grouped by distributor
        try:
            churn_result = (
                await client.table("analytics_customer_events")
                .select("distributor_id, customer_id, event_type, event_data, occurred_at")
                .eq("event_type", "churn_risk")
                .gte("occurred_at", datetime.combine(
                    date.today(), datetime.min.time(), tzinfo=timezone.utc,
                ).isoformat())
                .execute()
            )
        except Exception as exc:
            logger.error(
                "scheduler.churn_detection.events_query_failed",
                error=str(exc),
            )
            return

        # Group by distributor
        dist_events: dict[str, list] = {}
        for row in churn_result.data:
            did = row.get("distributor_id")
            if did:
                dist_events.setdefault(did, []).append(row)

        for dist_id, events in dist_events.items():
            if not events:
                continue

            # Build customer info for the alert
            churning = []
            for event in events:
                customer_name = "Unknown"
                event_data = event.get("event_data", {}) or {}
                customer_id = event.get("customer_id")
                try:
                    cust = (
                        await client.table("customers")
                        .select("name")
                        .eq("id", customer_id)
                        .limit(1)
                        .execute()
                    )
                    if cust.data:
                        customer_name = cust.data[0].get("name", "Unknown")
                except Exception:
                    pass

                # Use event_data for days_inactive if available
                days_inactive = event_data.get("days_inactive", 0)
                level = event_data.get("level", "warning")

                churning.append({
                    "customer_name": customer_name,
                    "days_inactive": days_inactive,
                    "severity": level,
                })

            if not churning:
                continue

            # Get distributor email
            try:
                dist_info = (
                    await client.table("distributors")
                    .select("email, business_name")
                    .eq("id", dist_id)
                    .limit(1)
                    .execute()
                )
                if dist_info.data and dist_info.data[0].get("email"):
                    await email_dispatcher.send_churn_alert(
                        to_email=dist_info.data[0]["email"],
                        distributor_name=dist_info.data[0].get("business_name", "",),
                        churning_customers=churning,
                    )
                    alerts_sent += 1
            except Exception as exc:
                logger.error(
                    "scheduler.churn_detection.alert_failed",
                    distributor_id=dist_id,
                    error=str(exc),
                )

        logger.info(
            "scheduler.churn_detection.complete",
            distributors_checked=len(results),
            alerts_sent=alerts_sent,
        )
    except Exception as exc:
        logger.error(
            "scheduler.churn_detection.fatal",
            error=str(exc),
        )


# ═══════════════════════════════════════════════════════════════════
# EXCEL REPORT DISPATCH (cron triggers per schedule)
# ═══════════════════════════════════════════════════════════════════


async def run_excel_report_dispatch_morning() -> None:
    """Dispatch daily morning Excel reports (DAILY_MORNING schedule).

    Sends yesterday's Excel order log to distributors configured
    for DAILY_MORNING schedule.

    This function never raises.
    """
    await _dispatch_excel_for_schedule("DAILY_MORNING")


async def run_excel_report_dispatch_evening() -> None:
    """Dispatch daily evening Excel reports (DAILY_EVENING schedule).

    Sends today's Excel order log to distributors configured
    for DAILY_EVENING schedule.

    This function never raises.
    """
    await _dispatch_excel_for_schedule("DAILY_EVENING")


async def _dispatch_excel_for_schedule(schedule_value: str) -> None:
    """Send Excel reports for a specific schedule.

    Args:
        schedule_value: ExcelReportSchedule enum value string.
    """
    logger.info(
        "scheduler.excel_dispatch.start",
        schedule=schedule_value,
    )

    try:
        from app.core.constants import ExcelReportSchedule
        from app.reporting.email_dispatch import email_dispatcher
        from app.reporting.excel_generator import get_monthly_report_path
        from app.reporting.report_scheduler import (
            get_distributors_needing_reports,
            get_report_date_range,
        )

        schedule = ExcelReportSchedule(schedule_value)
        start_date, end_date = get_report_date_range(schedule)
        distributors = await get_distributors_needing_reports(schedule)

        sent = 0
        failed = 0

        for dist in distributors:
            dist_id = dist["distributor_id"]
            try:
                owner_email = dist.get("owner_email")
                if not owner_email:
                    continue

                now = datetime.now(tz=timezone.utc)
                excel_path = await get_monthly_report_path(
                    dist_id, now.year, now.month,
                )
                if not excel_path:
                    logger.debug(
                        "scheduler.excel_dispatch.no_file",
                        distributor_id=dist_id,
                    )
                    continue

                await email_dispatcher.send_excel_report(
                    to_email=owner_email,
                    distributor_name=dist.get("business_name", ""),
                    report_date=end_date,
                    excel_path=excel_path,
                    period_label="Daily",
                )
                sent += 1
            except Exception as exc:
                logger.error(
                    "scheduler.excel_dispatch.distributor_failed",
                    distributor_id=dist_id,
                    error=str(exc),
                )
                failed += 1

        logger.info(
            "scheduler.excel_dispatch.complete",
            schedule=schedule_value,
            sent=sent,
            failed=failed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.excel_dispatch.fatal",
            schedule=schedule_value,
            error=str(exc),
        )
