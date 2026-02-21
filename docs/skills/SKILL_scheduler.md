# SKILL: Scheduler Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before implementing any background job.

---

## IDENTITY

This skill defines how background jobs are implemented, registered, and operated
in TELETRAAN using APScheduler. Background jobs are the nervous system of the
distributor management system. They must be: idempotent, failure-safe, observable,
and timezone-correct. A misfiring scheduler can send 50 payment reminders to one
distributor. Get this right.

---

## SETUP — ASYNCIOSCHEDULER

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone="Asia/Karachi",  # Pakistan Standard Time — ALL jobs in PKT
    job_defaults={
        "coalesce": True,        # If missed multiple runs, execute once on resume
        "max_instances": 1,      # Never run the same job twice concurrently
        "misfire_grace_time": 300,  # 5 minutes — allow late runs after service restart
    }
)
```

Scheduler started in `app/main.py` lifespan `startup` event.
Scheduler shut down gracefully in `lifespan` `shutdown` event.

---

## ALL REGISTERED JOBS

| Job ID | Trigger | Schedule (PKT) | Module |
|---|---|---|---|
| `subscription_reminder_check` | interval | Every 12 hours | reminder_jobs.py |
| `session_cleanup` | interval | Every 6 hours | cleanup_jobs.py |
| `inventory_sync_all` | interval | Every 2 hours (configurable) | sync_jobs.py |
| `scheduled_msg_dispatch` | interval | Every 5 minutes | cleanup_jobs.py |
| `daily_order_summary` | cron | Daily 20:00 PKT | report_jobs.py |
| `weekly_report` | cron | Monday 09:00 PKT | report_jobs.py |
| `monthly_excel_export` | cron | 1st of month 07:00 PKT | report_jobs.py |
| `health_check` | interval | Every 30 minutes | health_jobs.py |
| `analytics_aggregate` | interval | Every 60 minutes | report_jobs.py |
| `stale_prospect_followup` | cron | Daily 10:00 PKT | reminder_jobs.py |
| `churn_detection` | cron | Weekly Monday 08:00 PKT | cleanup_jobs.py |
| `storage_cleanup` | cron | Monthly 1st 06:00 PKT | cleanup_jobs.py |
| `dummy_gateway_confirm` | interval | Every 10 seconds (dev only) | scheduler.py |

---

## IDEMPOTENCY — NON-NEGOTIABLE RULE

Every job that sends a message or modifies data MUST be idempotent.
"If this job runs twice in 5 minutes, the effect is identical to running once."

### Enforcement for reminder jobs
Before sending any reminder message:
1. Check `scheduled_messages` table for existing record with same `idempotency_key`
2. `idempotency_key` format: `{job_type}:{distributor_id}:{billing_cycle_end_date}`
3. If record exists with `status = sent` → skip, return
4. If record exists with `status = pending` → attempt send (previous send may have failed)
5. If no record → create record with `status = pending`, then send, then update to `sent`

```python
idempotency_key = f"payment_reminder_7d:{distributor_id}:{subscription_end.date()}"
```

### Enforcement for report jobs
Check `notifications_log` for existing message sent today with same `notification_type`
and `recipient_number`. If found → skip.

---

## FAILURE HANDLING PER JOB

Every job must be wrapped in a top-level try/except:

```python
async def run_subscription_reminder_check() -> None:
    """Check all distributors and dispatch payment reminders as needed."""
    logger.info("Job started", job="subscription_reminder_check")
    try:
        await reminder_service.check_and_dispatch_all()
        logger.info("Job completed", job="subscription_reminder_check")
    except Exception as e:
        logger.error("Job failed", job="subscription_reminder_check", error=str(e))
        await _increment_job_failure_counter("subscription_reminder_check")
        await _alert_owner_if_consecutive_failures("subscription_reminder_check", threshold=3)
```

### Failure counter logic
Store job failure counts in Supabase `metadata` on a `system_health` record.
After 3 consecutive failures of the same job → send WhatsApp alert to owner number.
Counter resets on next successful run.

---

## TIMEZONE — ALWAYS PKT

All cron schedules defined in Asia/Karachi (PKT = UTC+5).
All datetime comparisons for scheduling use PKT-localized datetimes.
Never use naive datetime objects. Always use `datetime.now(tz=pytz.timezone("Asia/Karachi"))`.

---

## SCHEDULED_MESSAGES TABLE — THE DISPATCH QUEUE

The `scheduled_messages_dispatch` job polls the `scheduled_messages` table every 5 minutes.

Query: `WHERE status = 'pending' AND scheduled_for <= NOW() ORDER BY scheduled_for ASC LIMIT 50`

For each message:
1. Attempt WhatsApp send
2. On success: update `status = sent`, `sent_at = now()`
3. On failure: increment `retry_count`. If `retry_count >= max_retries`: update `status = failed`, log error.
4. Each message send is idempotent via `idempotency_key` on `notifications_log`

### Inserting into scheduled_messages
Always set `idempotency_key = f"{message_type}:{recipient_number}:{reference_id}:{cycle}"`.
Before inserting, check if a record with same `idempotency_key` already exists.
If exists: skip insert (already scheduled).

---

## INVENTORY SYNC JOB

```python
async def run_inventory_sync_all() -> None:
    """Sync inventory for all distributors with sync enabled."""
    distributors = await distributor_repo.get_all_with_sync_enabled()
    for distributor in distributors:
        try:
            await sync_service.sync_for_distributor(distributor.id)
        except Exception as e:
            logger.error("Sync failed for distributor", distributor_id=str(distributor.id), error=str(e))
            # Continue to next distributor — one failure doesn't block others
```

Key: each distributor's sync is independent. One failure must not block others.
Log each sync attempt to `inventory_sync_log` table — started_at, completed_at, status, rows.

---

## HEALTH CHECK JOB

Checks:
1. Supabase: execute `SELECT 1` — pass if completes within 3s
2. Gemini API: execute minimal text completion with 1 token — pass if responds
3. WhatsApp API: check Meta API health endpoint — pass if 200
4. Scheduler: verify all jobs have `next_run_time` within expected window
5. Disk/memory: check available memory (warn if < 100MB free)

On any check failure:
- Log error with component name
- If same component failed 2+ consecutive checks → send WhatsApp alert to `OWNER_WHATSAPP_NUMBER`
- Include component name, error, and timestamp in alert message

---

## DUMMY GATEWAY JOB (development only)

When `APP_ENV != production` and `ACTIVE_PAYMENT_GATEWAY = dummy`:
- APScheduler registers a job that runs every `DUMMY_GATEWAY_CONFIRM_DELAY_SECONDS`
- Job finds all payments with `gateway = dummy`, `status = pending`, created more than N seconds ago
- For each: simulate callback by calling internal payment callback handler directly
- Amount ending in 999 paisas → simulate failure

This job is ONLY registered when `APP_ENV in ('development', 'staging')`.
Hard check in scheduler.py — never register this in production.

---

## COALESCE AND MISFIRE

`coalesce = True` means: if the scheduler was down and missed 5 runs of a job,
it will execute the job ONCE when it comes back up, not 5 times.
This is critical for reminder jobs — you never want 5 payment reminders sent at once.

`misfire_grace_time = 300` means: if a job was scheduled for 10:00 but the process
was restarting and it couldn't run until 10:04, it will still run (within 5 min grace).
If it missed by more than 5 minutes, it will wait for the next scheduled time.

---

## JOB LOGGING

Every job must log:
- Start: `logger.info("Job started", job="{job_id}")`
- Success: `logger.info("Job completed", job="{job_id}", duration_ms=elapsed, records_processed=n)`
- Failure: `logger.error("Job failed", job="{job_id}", error=str(e))`

Duration should be measured with `time.monotonic()` start/end.
