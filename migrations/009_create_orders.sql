-- Migration 009: Create orders table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Financial amounts in paisas (BIGINT)
-- Self-referencing FK: source_order_id for quick reorders

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_number VARCHAR(20) NOT NULL UNIQUE,
    distributor_id UUID NOT NULL REFERENCES distributors(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    subtotal_paisas BIGINT NOT NULL DEFAULT 0,
    discount_paisas BIGINT DEFAULT 0,
    delivery_charges_paisas BIGINT DEFAULT 0,
    total_paisas BIGINT NOT NULL DEFAULT 0,
    payment_status VARCHAR(50) DEFAULT 'unpaid',
    payment_method VARCHAR(50),
    delivery_address TEXT,
    delivery_zone_id UUID REFERENCES delivery_zones(id),
    estimated_delivery_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    notes TEXT,
    internal_notes TEXT,
    discount_requests JSONB DEFAULT '[]',
    discount_approval_status VARCHAR(50) DEFAULT 'not_requested',
    source VARCHAR(50) DEFAULT 'whatsapp',
    is_quick_reorder BOOLEAN DEFAULT false,
    source_order_id UUID REFERENCES orders(id),
    whatsapp_logged_at TIMESTAMPTZ,
    excel_logged_at TIMESTAMPTZ,
    order_context_snapshot JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
