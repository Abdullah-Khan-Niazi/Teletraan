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
    _register_health_check_jobs(scheduler)


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
