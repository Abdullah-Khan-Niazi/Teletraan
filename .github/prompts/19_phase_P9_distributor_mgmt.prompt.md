# Phase 9 — Distributor Management System

**Prerequisites:** Phase 8 complete and verified.
**Verify before P10:** Reminder sequence fires correctly; suspension + grace period flow tested.

## Steps (execute in order, commit after each)

1. Implement `app/distributor_mgmt/subscription_manager.py` — subscription lifecycle FSM  
   States: trial → active → expiring → suspended (with grace period) → cancelled  
   Grace period: read from `distributors.grace_period_days` (default 3)  
   → Commit: `"distributor-mgmt: implement subscription lifecycle FSM with grace period handling"`

2. Implement `app/distributor_mgmt/reminder_service.py` — payment reminder generation  
   Schedule: 7 days before expiry, 3 days, 1 day, on expiry day  
   Deduplication via `scheduled_messages.idempotency_key` — no duplicate reminders  
   → Commit: `"distributor-mgmt: implement payment reminder generation with deduplication via idempotency keys"`

3. Implement `app/distributor_mgmt/notification_service.py` — batch notification system  
   (announcements, system updates, feature releases — sent to all active distributors)  
   → Commit: `"distributor-mgmt: implement batch notification system for updates and announcements"`

4. Implement `app/distributor_mgmt/onboarding_service.py` — multi-step onboarding sequence  
   Steps: payment confirmed → welcome message → setup guide → test order → catalog upload → go-live  
   → Commit: `"distributor-mgmt: implement multi-step onboarding sequence from payment to go-live"`

5. Implement `app/distributor_mgmt/support_service.py` — support ticket system  
   (create ticket, assign priority, notify owner, handle resolution, send resolution confirmation)  
   → Commit: `"distributor-mgmt: implement support ticket system with owner notification and resolution flow"`

6. Implement all scheduler jobs in `app/scheduler/jobs/`:  
   - `reminder_jobs.py` — daily reminder check  
   - `cleanup_jobs.py` — session cleanup, expired payment link cleanup  
   - `health_jobs.py` — AI provider health, gateway health, DB health  
   → Commit: `"scheduler: add reminder, cleanup, and health check jobs"`

7. Test reminder sequence: create distributor expiring in 7 days → verify reminder at 7d, 3d, 1d, expiry  
   Test suspension flow: let grace period expire → verify suspension + messaging  
   → Commit: `"tests: integration tests for subscription reminder sequence and suspension lifecycle"`

8. **PHASE 9 COMPLETE** Commit: `"phase-9: automated distributor management complete and tested"`
