-- Migration 028: Create analytics aggregation tables
--
-- Stores pre-computed daily metrics, top items, and customer lifecycle
-- events.  The nightly aggregation job populates these from source
-- tables (orders, customers, ai_provider_log, sessions).
-- These are read-only for WhatsApp analytics commands and reports.

-- Aggregated daily metrics per distributor
CREATE TABLE IF NOT EXISTS analytics_daily (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id          UUID NOT NULL REFERENCES distributors(id),
    date                    DATE NOT NULL,

    -- Orders
    orders_confirmed        INTEGER DEFAULT 0,
    orders_pending          INTEGER DEFAULT 0,
    orders_cancelled        INTEGER DEFAULT 0,
    orders_total_paisas     BIGINT DEFAULT 0,
    avg_order_paisas        BIGINT DEFAULT 0,

    -- Customers
    unique_customers        INTEGER DEFAULT 0,
    new_customers           INTEGER DEFAULT 0,
    returning_customers     INTEGER DEFAULT 0,

    -- Payments
    payments_received_paisas BIGINT DEFAULT 0,
    outstanding_delta_paisas BIGINT DEFAULT 0,

    -- AI & System
    messages_processed      INTEGER DEFAULT 0,
    voice_notes_count       INTEGER DEFAULT 0,
    ai_calls_count          INTEGER DEFAULT 0,
    ai_cost_paisas          INTEGER DEFAULT 0,
    fallback_responses      INTEGER DEFAULT 0,
    avg_response_ms         INTEGER DEFAULT 0,

    -- Catalog
    fuzzy_match_count       INTEGER DEFAULT 0,
    unlisted_requests       INTEGER DEFAULT 0,
    out_of_stock_events     INTEGER DEFAULT 0,

    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(distributor_id, date)
);

-- Top items per day
CREATE TABLE IF NOT EXISTS analytics_top_items (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id      UUID NOT NULL REFERENCES distributors(id),
    date                DATE NOT NULL,
    catalog_id          UUID REFERENCES catalog(id),
    medicine_name       TEXT NOT NULL,
    units_sold          INTEGER DEFAULT 0,
    revenue_paisas      BIGINT DEFAULT 0,
    order_count         INTEGER DEFAULT 0
);

-- Customer lifecycle events
CREATE TABLE IF NOT EXISTS analytics_customer_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id      UUID NOT NULL REFERENCES distributors(id),
    customer_id         UUID NOT NULL REFERENCES customers(id),
    event_type          TEXT NOT NULL,  -- 'first_order' | 'reorder' | 'escalation' | 'churn_risk'
    event_data          JSONB DEFAULT '{}',
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_analytics_daily_dist_date
    ON analytics_daily(distributor_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_top_items_dist_date
    ON analytics_top_items(distributor_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_customer_events_dist
    ON analytics_customer_events(distributor_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_customer_events_type
    ON analytics_customer_events(event_type, occurred_at DESC);
