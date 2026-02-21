# Phase 11 — Analytics, Reports, and All Scheduler Jobs

**Prerequisites:** Phase 10 complete and verified.
**Verify before P12:** All scheduler jobs manually triggered and verified; daily report email received.

## Steps (execute in order, commit after each)

1. Implement all analytics services:  
   - `app/analytics/order_analytics.py` — order volume, revenue, popular items, peak hours  
   - `app/analytics/customer_analytics.py` — customer activity, retention, top customers  
   - `app/analytics/distributor_analytics.py` — distributor health metrics, subscription analytics  
   - `app/analytics/system_analytics.py` — AI usage/cost, gateway performance, error rates  
   → Commit: `"analytics: implement order, customer, distributor, and system analytics services"`

2. Implement `app/reporting/analytics_service.py` — combine analytics data for reports  
   Implement `app/reporting/report_scheduler.py` — schedule generation timing  
   → Commit: `"reporting: implement analytics aggregation and report scheduling logic"`

3. Implement report generation and email delivery (Resend.com for Excel delivery)  
   Schedules: realtime, daily_morning, daily_evening, weekly — per `bot_configuration.excel_report_schedule`  
   → Commit: `"reporting: implement daily/weekly/monthly report generation and email dispatch"`

4. Implement all remaining scheduler jobs in `app/scheduler/jobs/`:  
   - `report_jobs.py` — report generation and delivery  
   - `health_jobs.py` — AI providers + payment gateways + DB + WhatsApp API health checks  
   Register all jobs in `app/scheduler/scheduler.py`  
   → Commit: `"scheduler: complete all job definitions with error handling and failure alerting"`

5. Test all scheduler jobs by manually triggering them — verify execution and error handling  
   → Commit: `"tests: verify all scheduler jobs execute correctly and handle failures"`

6. **PHASE 11 COMPLETE** Commit: `"phase-11: analytics, reporting, and scheduler jobs complete"`
