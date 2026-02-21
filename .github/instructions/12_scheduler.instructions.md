---
applyTo: "app/scheduler/**,app/**/*scheduler*.py,app/**/*jobs*.py,app/**/*cron*.py"
---

# SKILL 12 — SCHEDULER
## Source: `docs/skills/SKILL_scheduler.md`

---

## FRAMEWORK: APScheduler

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
```

Scheduler initialized in `app/scheduler/setup.py`.
Started in FastAPI lifespan (startup), shut down on app exit.

---

## INITIALIZATION

```python
# app/scheduler/setup.py

def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone="Asia/Karachi")
    _register_all_jobs(scheduler)
    return scheduler

def _register_all_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register all recurring jobs. One function per job category."""
    _register_session_cleanup_jobs(scheduler)
    _register_order_reminder_jobs(scheduler)
    _register_subscription_jobs(scheduler)
    _register_reporting_jobs(scheduler)
    _register_health_check_jobs(scheduler)
```

---

## REQUIRED JOBS

| Job | Schedule | Description |
|---|---|---|
| `expire_stale_sessions` | Every 15 min | Set sessions to `timed_out` after 60 min inactivity |
| `send_abandoned_order_reminders` | Every 30 min | Remind customers with >30 min inactive carts |
| `send_subscription_expiry_warnings` | Daily 09:00 | Warn distributors 7 days, 3 days, 1 day before expiry |
| `suspend_expired_distributors` | Daily 00:05 | Suspend distributors with expired subscriptions |
| `generate_daily_sales_report` | Daily 22:00 | Send distributor their daily sales summary |
| `generate_weekly_report` | Sunday 21:00 | Weekly analytics report to distributor |
| `cleanup_old_logs` | Daily 03:00 | Delete processed webhook logs older than 30 days |
| `scheduler_health_check` | Every 5 min | Verify scheduler is alive, log heartbeat |

---

## JOB FUNCTION PATTERN

```python
async def expire_stale_sessions() -> None:
    """Expire sessions that have been inactive for more than 60 minutes.

    Called every 15 minutes. Safe to run concurrently with other jobs.
    """
    logger.info("scheduler.expire_stale_sessions.start")
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=60)
        expired_count = await session_repo.expire_sessions_before(cutoff)
        logger.info("scheduler.expire_stale_sessions.complete", expired_count=expired_count)
    except Exception as exc:
        logger.error("scheduler.expire_stale_sessions.failed", error=str(exc))
        # Do NOT re-raise — scheduler must continue running other jobs
```

**KEY RULE: Job functions must never raise exceptions to the scheduler.**
Catch all exceptions, log them, and return. One failing job must not crash others.

---

## FASTAPI LIFESPAN INTEGRATION

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("scheduler.started", job_count=len(scheduler.get_jobs()))
    yield
    # Shutdown
    scheduler.shutdown(wait=True)
    logger.info("scheduler.stopped")
```

---

## TIMEZONE

All schedules in `Asia/Karachi` (PKT, UTC+5).
Store all timestamps in UTC in the database.
Convert to PKT only for display and scheduling.

---

## IDEMPOTENCY

All scheduled jobs must be safe to run multiple times (idempotent).
If a job fails halfway and restarts, it should not double-send messages
or double-process records. Use `processed_at` flags or status checks.
