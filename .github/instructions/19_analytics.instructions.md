---
applyTo: "app/analytics/**,app/**/reporting/**,app/**/*analytics*.py,app/**/*report*.py"
---

# SKILL 19 — ANALYTICS & REPORTING
## Source: `docs/skills/SKILL_analytics.md`

---

## GUIDING PRINCIPLE

Every meaningful business event must be captured at transaction time.
Analytics come from structured DB records — NOT from log parsing.

---

## WHAT GETS TRACKED

### Orders & Revenue
- Order count by status (confirmed, pending, cancelled)
- Revenue by day/week/month
- Average order value, order value distribution
- Orders by time of day (heatmap)
- Top ordering customers (by volume and value)

### Inventory & Catalog
- Top 10 medicines by units sold and by revenue
- Out-of-stock events: frequency, duration, lost order estimate
- Fuzzy match rate (% of orders needing fuzzy lookup)
- Unlisted item requests (demand for items not in catalog)

### Payments
- Payment method distribution
- Average days to payment
- Outstanding balance trend, payment completion rate

### Customer Behavior
- New customers per week/month; retention rate
- Voice note usage rate, escalation rate

### AI & System Performance
- AI provider cost per day/month
- Average response time per message
- Tool call success rate, error/fallback rate

---

## ANALYTICS DATABASE TABLES

```sql
-- Daily aggregated metrics (primary reporting table)
CREATE TABLE analytics_daily (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id  UUID NOT NULL REFERENCES distributors(id),
    date            DATE NOT NULL,
    orders_confirmed    INTEGER DEFAULT 0,
    orders_cancelled    INTEGER DEFAULT 0,
    orders_total_paisas BIGINT DEFAULT 0,
    avg_order_paisas    BIGINT DEFAULT 0,
    unique_customers    INTEGER DEFAULT 0,
    new_customers       INTEGER DEFAULT 0,
    UNIQUE (distributor_id, date)
);

-- Individual event log (source of truth for aggregation)
CREATE TABLE analytics_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id  UUID NOT NULL REFERENCES distributors(id),
    event_type      VARCHAR(100) NOT NULL,   -- "order.confirmed", "payment.received", etc.
    customer_id     UUID,
    order_id        UUID,
    amount_paisas   BIGINT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## ANALYTICS SERVICE (app/analytics/service.py)

```python
async def record_event(
    distributor_id: str,
    event_type: str,          # e.g., "order.confirmed"
    customer_id: str | None = None,
    order_id: str | None = None,
    amount_paisas: int | None = None,
    metadata: dict | None = None,
) -> None:
    """Record an analytics event. Never raises — analytics must not block business logic."""
    try:
        await analytics_repo.create_event(...)
    except Exception as exc:
        logger.error("analytics.event_record_failed", event_type=event_type, error=str(exc))
        # Do not re-raise — analytics failure must not break the order flow
```

**Analytics recording must NEVER block or break business logic.**
Wrap in try/except, log errors, return silently.

---

## DAILY AGGREGATION JOB

Runs at 22:00 PKT daily via scheduler:
- Aggregate `analytics_events` for the day into `analytics_daily`
- Upsert (not insert) — idempotent if re-run

---

## REPORTS

### Daily Sales Report (sent to distributor via WhatsApp at 22:00)
```
📊 Aaj ka Summary — [Date]

Orders:    12 confirmed | 2 pending
Revenue:   PKR 45,800
New customers: 3
Top seller: Paracetamol 500mg (23 strips)

Full report: [link or "respond REPORT"]
```

### Weekly Report (Sunday 21:00)
Aggregated weekly metrics with week-over-week comparison.

---

## REPORTING FILE STRUCTURE

```
app/analytics/
├── service.py          # record_event(), get_daily_stats()
├── aggregator.py       # Daily aggregation job
├── reports/
│   ├── daily.py        # Daily report generator
│   └── weekly.py       # Weekly report generator
└── exporters/
    ├── excel.py        # Excel export (openpyxl)
    └── pdf.py          # PDF export (reportlab)
```
