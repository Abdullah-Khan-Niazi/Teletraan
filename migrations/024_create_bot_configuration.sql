-- Migration 024: Create bot_configuration table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- One row per distributor — per-tenant bot settings
-- Financial amounts in paisas (BIGINT)

CREATE TABLE IF NOT EXISTS bot_configuration (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL UNIQUE REFERENCES distributors(id) ON DELETE CASCADE,
    welcome_message_override TEXT,
    business_hours_start TIME DEFAULT '08:00',
    business_hours_end TIME DEFAULT '20:00',
    timezone VARCHAR(50) DEFAULT 'Asia/Karachi',
    out_of_hours_message TEXT,
    allow_orders_outside_hours BOOLEAN DEFAULT true,
    voice_enabled BOOLEAN DEFAULT true,
    catalog_pdf_enabled BOOLEAN DEFAULT true,
    discount_requests_enabled BOOLEAN DEFAULT true,
    credit_orders_enabled BOOLEAN DEFAULT false,
    minimum_order_value_paisas BIGINT DEFAULT 0,
    max_items_per_order INTEGER DEFAULT 50,
    session_timeout_minutes INTEGER DEFAULT 60,
    ai_temperature DECIMAL(3,2) DEFAULT 0.30,
    custom_system_prompt_suffix TEXT,
    excel_report_email VARCHAR(255),
    excel_report_schedule VARCHAR(50) DEFAULT 'daily_evening',
    preferred_payment_gateways TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
