-- Migration 020: Create analytics_events table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Tracks all system events for business intelligence

CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID REFERENCES distributors(id),
    event_type VARCHAR(255) NOT NULL,
    channel VARCHAR(10),
    customer_id UUID REFERENCES customers(id),
    session_id UUID REFERENCES sessions(id),
    properties JSONB DEFAULT '{}',
    duration_ms INTEGER,
    ai_provider VARCHAR(50),
    ai_tokens_used INTEGER,
    ai_cost_paisas INTEGER,
    payment_gateway VARCHAR(50),
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);
