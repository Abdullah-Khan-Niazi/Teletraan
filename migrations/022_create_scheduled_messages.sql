-- Migration 022: Create scheduled_messages table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Supports deferred WhatsApp message delivery with retry

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID REFERENCES distributors(id),
    recipient_number VARCHAR(20) NOT NULL,
    recipient_type VARCHAR(50) NOT NULL,
    message_type VARCHAR(100) NOT NULL,
    message_payload JSONB NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    reference_id UUID,
    reference_type VARCHAR(50),
    idempotency_key VARCHAR(255) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
