-- Migration 018: Create audit_log table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- IMMUTABLE: no updates, no deletes. RLS: INSERT only.

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_type VARCHAR(50) NOT NULL,
    actor_id UUID,
    actor_whatsapp_masked VARCHAR(20),
    distributor_id UUID REFERENCES distributors(id),
    action VARCHAR(255) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    before_state JSONB,
    after_state JSONB,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
