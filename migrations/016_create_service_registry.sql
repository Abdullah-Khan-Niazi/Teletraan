-- Migration 016: Create service_registry table + add FK from prospects
-- Idempotent: CREATE TABLE IF NOT EXISTS, DO $$ with constraint check
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS service_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    short_description VARCHAR(500),
    setup_fee_paisas BIGINT DEFAULT 0,
    monthly_fee_paisas BIGINT DEFAULT 0,
    demo_video_url TEXT,
    catalog_url TEXT,
    target_business_types TEXT[],
    sales_flow_handler VARCHAR(100),
    is_available BOOLEAN DEFAULT true,
    is_coming_soon BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add FK from prospects to service_registry
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'prospects_interested_service_id_fkey'
    ) THEN
        ALTER TABLE prospects
            ADD CONSTRAINT prospects_interested_service_id_fkey
            FOREIGN KEY (interested_service_id) REFERENCES service_registry(id);
    END IF;
END $$;
