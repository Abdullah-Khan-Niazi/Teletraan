-- Migration 003: Create distributors table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Core tenant table — most other tables reference distributor_id

CREATE TABLE IF NOT EXISTS distributors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_name VARCHAR(255) NOT NULL,
    owner_name VARCHAR(255) NOT NULL,
    whatsapp_number VARCHAR(20) NOT NULL UNIQUE,
    whatsapp_phone_number_id VARCHAR(100) NOT NULL UNIQUE,
    whatsapp_group_id VARCHAR(100),
    city VARCHAR(100),
    address TEXT,
    cnic_encrypted TEXT,
    email VARCHAR(255),
    plan_id UUID REFERENCES subscription_plans(id),
    subscription_status VARCHAR(50) NOT NULL DEFAULT 'trial',
    subscription_start TIMESTAMPTZ,
    subscription_end TIMESTAMPTZ,
    trial_end TIMESTAMPTZ,
    grace_period_days INTEGER DEFAULT 3,
    deployment_version VARCHAR(50),
    bot_language_default VARCHAR(20) DEFAULT 'roman_urdu',
    catalog_last_synced TIMESTAMPTZ,
    catalog_sync_url TEXT,
    onboarding_completed BOOLEAN DEFAULT false,
    onboarding_completed_at TIMESTAMPTZ,
    preferred_payment_gateway VARCHAR(50),
    is_active BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
