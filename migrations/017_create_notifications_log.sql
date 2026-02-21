-- Migration 017: Create notifications_log table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Stores all outbound WhatsApp notifications for audit and retry

CREATE TABLE IF NOT EXISTS notifications_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID REFERENCES distributors(id),
    recipient_number_masked VARCHAR(20),
    recipient_type VARCHAR(50),
    notification_type VARCHAR(100) NOT NULL,
    message_preview VARCHAR(500),
    whatsapp_message_id VARCHAR(255),
    delivery_status VARCHAR(50) DEFAULT 'sent',
    delivery_status_updated_at TIMESTAMPTZ,
    reference_id UUID,
    reference_type VARCHAR(50),
    error_message TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);
