-- Migration 010: Create order_items table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    distributor_id UUID NOT NULL REFERENCES distributors(id),
    catalog_id UUID REFERENCES catalog(id),
    medicine_name_raw VARCHAR(500),
    medicine_name VARCHAR(500) NOT NULL,
    unit VARCHAR(50),
    quantity_ordered INTEGER NOT NULL,
    quantity_fulfilled INTEGER DEFAULT 0,
    price_per_unit_paisas BIGINT NOT NULL,
    line_total_paisas BIGINT NOT NULL,
    discount_paisas BIGINT DEFAULT 0,
    bonus_units_given INTEGER DEFAULT 0,
    is_out_of_stock_order BOOLEAN DEFAULT false,
    is_unlisted_item BOOLEAN DEFAULT false,
    input_method VARCHAR(20),
    fuzzy_match_score DECIMAL(5,2),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
