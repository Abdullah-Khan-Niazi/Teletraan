-- Migration 008: Create sessions table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Tracks conversation state per WhatsApp number per distributor

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE,
    whatsapp_number VARCHAR(20) NOT NULL,
    customer_id UUID REFERENCES customers(id),
    channel VARCHAR(10) NOT NULL DEFAULT 'A',
    current_state VARCHAR(100) NOT NULL DEFAULT 'idle',
    previous_state VARCHAR(100),
    state_data JSONB DEFAULT '{}',
    conversation_history JSONB DEFAULT '[]',
    pending_order_draft JSONB DEFAULT '{}',
    language VARCHAR(20) DEFAULT 'roman_urdu',
    retry_count INTEGER DEFAULT 0,
    handoff_mode BOOLEAN DEFAULT false,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(distributor_id, whatsapp_number)
);
