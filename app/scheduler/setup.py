"""APScheduler setup — creates, configures, and exposes the scheduler singleton.

The scheduler is created via ``create_scheduler()`` and started/stopped
in the FastAPI lifespan.  All jobs are registered by
``_register_all_jobs()`` which delegates to per-category registration
functions.

Timezone: Asia/Karachi (PKT, UTC+5) for all scheduling.
Database timestamps stay UTC.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.core.config import get_settings


# ── Module-level scheduler reference ────────────────────────────────
# Set by ``create_scheduler()`` and used by health checks.
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the current scheduler instance, or None if not yet created."""
    return _scheduler


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Registers all recurring jobs.  The caller (FastAPI lifespan) is
    responsible for calling ``.start()`` and ``.shutdown()``.

    Returns:
        Configured AsyncIOScheduler ready to be started.
    """
    global _scheduler  # noqa: PLW0603

    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    _register_all_jobs(scheduler)

    _scheduler = scheduler
    logger.info(
        "scheduler.created",
        timezone=settings.scheduler_timezone,
        job_count=len(scheduler.get_jobs()),
    )
    return scheduler


def _register_all_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register all recurring jobs.  One function per job category.

    Args:
        scheduler: The APScheduler instance to register jobs with.
    """
    _register_inventory_sync_jobs(scheduler)
    _register_reminder_jobs(scheduler)
    _register_cleanup_jobs(scheduler)
    _register_health_check_jobs(scheduler)
    _register_system_health_jobs(scheduler)
    _register_message_sender_jobs(scheduler)


# ── Inventory Sync ──────────────────────────────────────────────────


def _register_inventory_sync_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the periodic inventory sync job.

    Reads ``INVENTORY_SYNC_INTERVAL_MINUTES`` from settings.
    Only registered if ``ENABLE_INVENTORY_SYNC`` is True.

    Args:
        scheduler: The APScheduler instance.
    """
    settings = get_settings()

    if not settings.enable_inventory_sync:
        logger.info("scheduler.inventory_sync_disabled")
        return

    from app.scheduler.jobs.sync_jobs import run_inventory_sync

    scheduler.add_job(
        run_inventory_sync,
        trigger=IntervalTrigger(
            minutes=settings.inventory_sync_interval_minutes,
        ),
        id="inventory_sync",
        name="Inventory Sync — all distributors",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "scheduler.job_registered",
        job_id="inventory_sync",
        interval_minutes=settings.inventory_sync_interval_minutes,
    )


# ── Health Check ────────────────────────────────────────────────────


def _register_health_check_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the scheduler heartbeat job.

    Runs every 5 minutes to log that the scheduler is alive.

    Args:
        scheduler: The APScheduler instance.
    """
    from app.scheduler.jobs.sync_jobs import scheduler_health_check

    scheduler.add_job(
        scheduler_health_check,
        trigger=IntervalTrigger(minutes=5),
        id="scheduler_health_check",
        name="Scheduler Health Check",
        replace_existing=True,
        max_instances=1,
    )


# ── Reminder Jobs ───────────────────────────────────────────────────


def _register_reminder_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register subscription reminder and lifecycle check jobs.

    Runs at the interval defined by ``REMINDER_CHECK_INTERVAL_HOURS``.

    Args:
        scheduler: The APScheduler instance.
    """
    settings = get_settings()

    from app.scheduler.jobs.reminder_jobs import run_reminder_check

    scheduler.add_job(
        run_reminder_check,
        trigger=IntervalTrigger(
            hours=settings.reminder_check_interval_hours,
        ),
        id="reminder_check",
        name="Subscription Reminder Check",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "scheduler.job_registered",
        job_id="reminder_check",
        interval_hours=settings.reminder_check_interval_hours,
    )


# ── Cleanup Jobs ────────────────────────────────────────────────────


def _register_cleanup_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register session cleanup and expired payment cleanup jobs.

    Session cleanup runs at ``SESSION_CLEANUP_INTERVAL_HOURS``.
    Payment cleanup runs alongside session cleanup.

    Args:
        scheduler: The APScheduler instance.
    """
    settings = get_settings()

    from app.scheduler.jobs.cleanup_jobs import (
        run_expired_payment_cleanup,
        run_session_cleanup,
    )

    scheduler.add_job(
        run_session_cleanup,
        trigger=IntervalTrigger(
            hours=settings.session_cleanup_interval_hours,
        ),
        id="session_cleanup",
        name="Expired Session Cleanup",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "scheduler.job_registered",
        job_id="session_cleanup",
        interval_hours=settings.session_cleanup_interval_hours,
    )

    scheduler.add_job(
        run_expired_payment_cleanup,
        trigger=IntervalTrigger(
            hours=settings.session_cleanup_interval_hours,
        ),
        id="expired_payment_cleanup",
        name="Expired Payment Link Cleanup",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "scheduler.job_registered",
        job_id="expired_payment_cleanup",
        interval_hours=settings.session_cleanup_interval_hours,
    )


# ── System Health Jobs ──────────────────────────────────────────────


def _register_system_health_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register system health check job (AI, gateways, DB).

    Runs every 15 minutes to surface infrastructure failures.

    Args:
        scheduler: The APScheduler instance.
    """
    from app.scheduler.jobs.health_jobs import run_system_health_check

    scheduler.add_job(
        run_system_health_check,
        trigger=IntervalTrigger(minutes=15),
        id="system_health_check",
        name="System Health Check (AI, Gateways, DB)",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "scheduler.job_registered",
        job_id="system_health_check",
        interval_minutes=15,
    )


# ── Scheduled Message Sender ───────────────────────────────────────


def _register_message_sender_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the scheduled message sender job.

    Runs every 2 minutes to pick up and send due scheduled_messages.

    Args:
        scheduler: The APScheduler instance.
    """
    from app.scheduler.jobs.reminder_jobs import run_send_scheduled_messages

    scheduler.add_job(
        run_send_scheduled_messages,
        trigger=IntervalTrigger(minutes=2),
        id="send_scheduled_messages",
        name="Send Due Scheduled Messages",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "scheduler.job_registered",
        job_id="send_scheduled_messages",
        interval_minutes=2,
    )
