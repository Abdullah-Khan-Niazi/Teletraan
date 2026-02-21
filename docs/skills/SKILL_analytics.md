# ANALYTICS & REPORTING SKILL
## SKILL: analytics | Version: 1.0 | Priority: MEDIUM

---

## PURPOSE

This skill defines how TELETRAAN captures, stores, aggregates, and exports
business analytics for distributor owners. Analytics are not optional —
they are the mechanism by which owners understand their business, track
performance, and justify TELETRAAN's cost.

Every meaningful business event must be captured at transaction time.
No analytics is derived from logs — analytics come from structured DB records.

---

## WHAT GETS TRACKED

### Orders & Revenue
- Order count by status (confirmed, pending, cancelled)
- Revenue by day, week, month
- Average order value
- Order value distribution (histogram)
- Orders by time of day (heatmap)
- Top ordering customers (by volume and value)
- Repeat vs. first-time customers

### Inventory & Catalog
- Top 10 medicines by units sold
- Top 10 medicines by revenue
- Stock depletion rate per medicine
- Out-of-stock events (frequency, duration, lost order estimate)
- Fuzzy match rate (% of orders needing fuzzy lookup)
- Unlisted item requests (medicines customers ordered but aren't in catalog)

### Payments
- Payment method distribution (JazzCash/EasyPaisa/Safepay/etc.)
- Average days to payment
- Outstanding balance trend
- Payment completion rate

### Customer Behavior
- New customers per week/month
- Customer retention (orders per customer per month)
- Voice note usage rate
- Discount request rate
- Escalation rate

### AI & System Performance
- Intent classification accuracy (inferred from correction rate)
- Voice transcription usage
- Average response time per message
- AI provider cost per day/month
- Tool call success rate
- Error rate (fallback responses triggered)

---

## DATABASE SCHEMA — ANALYTICS TABLES

```sql
-- Aggregated daily metrics per distributor
CREATE TABLE analytics_daily (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id  UUID NOT NULL REFERENCES distributors(id),
    date            DATE NOT NULL,

    -- Orders
    orders_confirmed    INTEGER DEFAULT 0,
    orders_pending      INTEGER DEFAULT 0,
    orders_cancelled    INTEGER DEFAULT 0,
    orders_total_paisas BIGINT DEFAULT 0,
    avg_order_paisas    BIGINT DEFAULT 0,

    -- Customers
    unique_customers    INTEGER DEFAULT 0,
    new_customers       INTEGER DEFAULT 0,
    returning_customers INTEGER DEFAULT 0,

    -- Payments
    payments_received_paisas BIGINT DEFAULT 0,
    outstanding_delta_paisas BIGINT DEFAULT 0,

    -- AI & System
    messages_processed  INTEGER DEFAULT 0,
    voice_notes_count   INTEGER DEFAULT 0,
    ai_calls_count      INTEGER DEFAULT 0,
    ai_cost_paisas      INTEGER DEFAULT 0,
    fallback_responses  INTEGER DEFAULT 0,
    avg_response_ms     INTEGER DEFAULT 0,

    -- Catalog
    fuzzy_match_count   INTEGER DEFAULT 0,
    unlisted_requests   INTEGER DEFAULT 0,
    out_of_stock_events INTEGER DEFAULT 0,

    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(distributor_id, date)
);

-- Top items per day
CREATE TABLE analytics_top_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id  UUID NOT NULL REFERENCES distributors(id),
    date            DATE NOT NULL,
    catalog_id      UUID NOT NULL REFERENCES catalog(id),
    medicine_name   TEXT NOT NULL,
    units_sold      INTEGER DEFAULT 0,
    revenue_paisas  BIGINT DEFAULT 0,
    order_count     INTEGER DEFAULT 0
);

-- Customer lifecycle events
CREATE TABLE analytics_customer_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id  UUID NOT NULL REFERENCES distributors(id),
    customer_id     UUID NOT NULL REFERENCES customers(id),
    event_type      TEXT NOT NULL,  -- 'first_order' | 'reorder' | 'escalation' | 'churn_risk'
    event_data      JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_daily_dist_date ON analytics_daily(distributor_id, date DESC);
CREATE INDEX idx_analytics_top_items_dist_date ON analytics_top_items(distributor_id, date DESC);
```

---

## AGGREGATION PIPELINE

Analytics are computed nightly by the scheduler. Never derived on-demand
(too slow for production WhatsApp responses).

```python
# app/analytics/aggregator.py

class DailyAnalyticsAggregator:
    """
    Computes and upserts daily analytics for all active distributors.
    Runs nightly at 23:50 PKT via scheduler.
    Can also be triggered manually: POST /admin/analytics/compute?date=YYYY-MM-DD
    """

    async def compute_for_date(self, distributor_id: str, date: date) -> None:
        # Orders
        orders = await order_repo.get_by_distributor_and_date(distributor_id, date)
        confirmed = [o for o in orders if o.status == "confirmed"]
        
        total_paisas = sum(o.total_paisas for o in confirmed)
        avg_paisas = total_paisas // len(confirmed) if confirmed else 0

        # Customers
        customer_phones = {o.customer_phone for o in confirmed}
        new_customers = await customer_repo.count_new_on_date(distributor_id, date)

        # AI costs
        ai_cost = await ai_provider_log_repo.sum_cost_paisas(distributor_id, date)

        # Upsert
        await analytics_repo.upsert_daily(
            distributor_id=distributor_id,
            date=date,
            orders_confirmed=len(confirmed),
            orders_pending=len([o for o in orders if o.status == "pending"]),
            orders_cancelled=len([o for o in orders if o.status == "cancelled"]),
            orders_total_paisas=total_paisas,
            avg_order_paisas=avg_paisas,
            unique_customers=len(customer_phones),
            new_customers=new_customers,
            ai_cost_paisas=ai_cost,
        )

        # Top items
        await self._compute_top_items(distributor_id, date, confirmed)
```

---

## REPORTING FORMATS

### 1. Daily WhatsApp Summary (Owner)
Sent nightly at 20:00 PKT to owner's WhatsApp.
Format: See SKILL_human_operator.md → OWNER_NOTIFICATIONS["daily_summary"]

### 2. Weekly Excel Report
Generated every Monday at 09:00 PKT.
Sent to owner as Excel file download link.

**Excel structure:**
```
Sheet 1: Order Summary
  - Date | Orders Confirmed | Revenue PKR | Avg Order PKR | New Customers

Sheet 2: Top Products
  - Medicine Name | Units Sold | Revenue PKR | Order Count

Sheet 3: Customer Analysis
  - Customer Name | Shop | Orders This Week | Total Value | Outstanding Balance

Sheet 4: Payment Summary
  - Payment Method | Count | Total PKR | % of Revenue

Sheet 5: AI & System
  - Date | Messages | AI Calls | AI Cost PKR | Avg Response ms | Errors
```

### 3. Monthly PDF Report
Generated on the 1st of each month for the previous month.
Comprehensive business health report.

```python
# app/analytics/reports/monthly_pdf.py

async def generate_monthly_pdf(distributor_id: str, month: date) -> bytes:
    """
    Generate a professional monthly PDF report.
    Uses reportlab or WeasyPrint.
    Sections:
    1. Executive Summary (1 page)
    2. Revenue Breakdown (charts)
    3. Top Products Table
    4. Customer Retention Analysis
    5. Payment Performance
    6. AI System Performance
    7. Recommendations (rule-based, not AI-generated)
    """
```

---

## INLINE ANALYTICS COMMANDS (Owner WhatsApp)

Owners can request analytics directly via WhatsApp commands.
These are served from the pre-aggregated analytics_daily table — never
computed live from raw order tables.

```python
ANALYTICS_COMMAND_RESPONSES = {

    "today_stats": """📊 *Aaj* ({today_date})
Orders: {confirmed} ✅ | Revenue: PKR {revenue}
New customers: {new_customers}
Top item: {top_item}""",

    "this_week": """📊 *Is Hafta*
Orders: {order_count} | Revenue: PKR {revenue}
Best day: {best_day}
Top item: {top_item}
New customers: {new_customers}""",

    "this_month": """📊 *Is Mahina*
Orders: {order_count} | Revenue: PKR {revenue}
Outstanding: PKR {outstanding}
Month-over-month: {mom_change}%
Excel report: {excel_link}""",

    "top_customers": """👥 *Top 5 Customers* (Is Mahina)
1. {c1_name} — PKR {c1_value}
2. {c2_name} — PKR {c2_value}
3. {c3_name} — PKR {c3_value}
4. {c4_name} — PKR {c4_value}
5. {c5_name} — PKR {c5_value}""",

    "top_medicines": """💊 *Top 5 Medicines* (Is Mahina)
1. {m1_name} — {m1_units} units — PKR {m1_revenue}
2. {m2_name} — {m2_units} units — PKR {m2_revenue}
3. {m3_name} — {m3_units} units — PKR {m3_revenue}
4. {m4_name} — {m4_units} units — PKR {m4_revenue}
5. {m5_name} — {m5_units} units — PKR {m5_revenue}""",

}
```

---

## CHURN DETECTION (Automated)

```python
# app/analytics/churn.py
# Runs weekly — Monday 08:00 PKT

CHURN_THRESHOLDS = {
    "warning": 21,    # days since last order → send gentle alert to owner
    "critical": 42,   # days since last order → strong churn risk alert
}

async def detect_churning_customers(distributor_id: str) -> None:
    customers = await customer_repo.get_active(distributor_id)
    today = date.today()

    for customer in customers:
        days_since = (today - customer.last_order_date).days

        if days_since >= CHURN_THRESHOLDS["critical"]:
            await notify_owner(distributor_id, "churn_critical", customer=customer, days=days_since)
            await analytics_event_repo.log(distributor_id, customer.id, "churn_risk", {"days_inactive": days_since})

        elif days_since >= CHURN_THRESHOLDS["warning"]:
            await notify_owner(distributor_id, "churn_warning", customer=customer, days=days_since)
```

---

## ANALYTICS RULES

### RULE 1 — CAPTURE AT TRANSACTION TIME
When an order is confirmed, write the analytics event immediately.
Do not rely on the nightly aggregator to catch everything. Critical events
(order confirmed, payment received, customer churned) are captured in real-time.

### RULE 2 — AGGREGATED DATA IS IMMUTABLE
Once `analytics_daily` is computed for a past date, it is not recomputed
unless explicitly forced via an admin command. Historical records are stable.

### RULE 3 — NEVER DERIVE ANALYTICS FROM LOGS
Logs are for debugging. Analytics come from DB records.
`orders` table → revenue analytics.
`ai_provider_log` → AI cost analytics.
`sessions` → engagement analytics.

### RULE 4 — ALL AMOUNTS IN PAISAS IN DB, PKR IN DISPLAY
Same rule as everywhere else. Format for display:
```python
def paisas_to_pkr(paisas: int) -> str:
    """Returns formatted PKR string: 'PKR 1,234'"""
    return f"PKR {paisas // 100:,}"
```

### RULE 5 — REPORT GENERATION IS ASYNC
Excel and PDF generation happens in background tasks.
Owner receives a "generating..." message immediately,
then a download link when ready (usually < 30 seconds).

---

*End of SKILL: analytics v1.0*
