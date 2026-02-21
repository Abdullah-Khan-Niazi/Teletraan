-- Migration 002: Create subscription_plans table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS subscription_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    monthly_fee_paisas BIGINT NOT NULL,
    setup_fee_paisas BIGINT NOT NULL DEFAULT 0,
    max_orders_per_month INTEGER,
    max_customers INTEGER,
    features JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
