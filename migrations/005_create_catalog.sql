-- Migration 005: Create catalog table
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE UNIQUE INDEX IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS catalog (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE,
    medicine_name VARCHAR(500) NOT NULL,
    generic_name VARCHAR(500),
    brand_name VARCHAR(255),
    manufacturer VARCHAR(255),
    category VARCHAR(100),
    form VARCHAR(100),
    strength VARCHAR(100),
    unit VARCHAR(50),
    units_per_pack INTEGER DEFAULT 1,
    price_per_unit_paisas BIGINT NOT NULL,
    mrp_paisas BIGINT,
    stock_quantity INTEGER DEFAULT 0,
    reserved_quantity INTEGER DEFAULT 0,
    low_stock_threshold INTEGER DEFAULT 10,
    is_in_stock BOOLEAN DEFAULT true,
    allow_order_when_out_of_stock BOOLEAN DEFAULT true,
    requires_prescription BOOLEAN DEFAULT false,
    is_controlled_substance BOOLEAN DEFAULT false,
    search_keywords TEXT[],
    sku VARCHAR(100),
    barcode VARCHAR(100),
    image_url TEXT,
    is_active BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Partial unique index on SKU per distributor (only active, non-deleted items)
CREATE UNIQUE INDEX IF NOT EXISTS idx_catalog_sku_unique
    ON catalog (distributor_id, sku)
    WHERE sku IS NOT NULL AND is_deleted = false;
