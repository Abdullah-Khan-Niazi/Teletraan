-- Migration 012: Create payments table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Financial amounts in paisas (BIGINT)
-- Supports JazzCash, EasyPaisa, SafePay, NayaPay, Bank Transfer, Dummy

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_reference VARCHAR(255) NOT NULL UNIQUE,
    payment_type VARCHAR(50) NOT NULL,
    distributor_id UUID REFERENCES distributors(id),
    order_id UUID REFERENCES orders(id),
    customer_id UUID REFERENCES customers(id),
    gateway VARCHAR(50) NOT NULL,
    gateway_transaction_id VARCHAR(255),
    gateway_order_id VARCHAR(255),
    amount_paisas BIGINT NOT NULL,
    currency VARCHAR(10) DEFAULT 'PKR',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    payment_link TEXT,
    payment_link_expires_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    gateway_response JSONB DEFAULT '{}',
    failure_reason TEXT,
    refund_amount_paisas BIGINT DEFAULT 0,
    refunded_at TIMESTAMPTZ,
    screenshot_storage_path TEXT,
    manual_confirmed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
