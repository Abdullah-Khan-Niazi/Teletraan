-- Migration 015: Create prospects table (Channel B sales funnel)
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- interested_service_id column present but FK added in 016 after service_registry exists

CREATE TABLE IF NOT EXISTS prospects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    whatsapp_number VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255),
    business_name VARCHAR(255),
    business_type VARCHAR(100),
    city VARCHAR(100),
    estimated_retailer_count INTEGER,
    monthly_order_estimate INTEGER,
    interested_service_id UUID,
    status VARCHAR(50) DEFAULT 'new',
    demo_booked_at TIMESTAMPTZ,
    demo_slot TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,
    converted_distributor_id UUID REFERENCES distributors(id),
    lost_reason TEXT,
    waitlist_service VARCHAR(255),
    follow_up_at TIMESTAMPTZ,
    preferred_payment_gateway VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
