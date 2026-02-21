-- Migration 021: Create rate_limits table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Per-number rate limiting with sliding windows

CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID REFERENCES distributors(id),
    whatsapp_number VARCHAR(20) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    message_count INTEGER DEFAULT 0,
    voice_count INTEGER DEFAULT 0,
    ai_call_count INTEGER DEFAULT 0,
    is_throttled BOOLEAN DEFAULT false,
    UNIQUE(distributor_id, whatsapp_number, window_start)
);
