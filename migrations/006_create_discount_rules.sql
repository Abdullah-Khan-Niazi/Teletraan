-- Migration 006: Create discount_rules table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS discount_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE,
    catalog_id UUID REFERENCES catalog(id) ON DELETE CASCADE,
    rule_name VARCHAR(255),
    rule_type VARCHAR(50) NOT NULL,
    buy_quantity INTEGER,
    get_quantity INTEGER,
    discount_percentage DECIMAL(5,2),
    discount_flat_paisas BIGINT,
    minimum_order_quantity INTEGER,
    minimum_order_value_paisas BIGINT,
    applicable_customer_tags TEXT[],
    priority INTEGER DEFAULT 0,
    is_stackable BOOLEAN DEFAULT false,
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    usage_limit INTEGER,
    usage_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
