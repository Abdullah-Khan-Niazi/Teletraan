-- Migration 007: Create delivery_zones table + add FK from customers
-- Idempotent: CREATE TABLE IF NOT EXISTS, DO $$ with constraint check
-- Multi-tenant: distributor_id FK
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS delivery_zones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    areas TEXT[],
    delivery_days TEXT[],
    estimated_delivery_hours INTEGER DEFAULT 24,
    delivery_charges_paisas BIGINT DEFAULT 0,
    minimum_order_for_free_delivery_paisas BIGINT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Now add the FK from customers to delivery_zones
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'customers_delivery_zone_id_fkey'
    ) THEN
        ALTER TABLE customers
            ADD CONSTRAINT customers_delivery_zone_id_fkey
            FOREIGN KEY (delivery_zone_id) REFERENCES delivery_zones(id);
    END IF;
END $$;
