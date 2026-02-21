-- Migration 004: Create customers table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- delivery_zone_id column present but FK added in 007 after delivery_zones exists

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE,
    whatsapp_number VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    shop_name VARCHAR(255) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    delivery_zone_id UUID,
    language_preference VARCHAR(20) DEFAULT 'roman_urdu',
    is_verified BOOLEAN DEFAULT false,
    credit_limit_paisas BIGINT DEFAULT 0,
    outstanding_balance_paisas BIGINT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    is_blocked BOOLEAN DEFAULT false,
    blocked_reason TEXT,
    blocked_at TIMESTAMPTZ,
    last_order_at TIMESTAMPTZ,
    total_orders INTEGER DEFAULT 0,
    total_spend_paisas BIGINT DEFAULT 0,
    tags TEXT[],
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(distributor_id, whatsapp_number)
);
