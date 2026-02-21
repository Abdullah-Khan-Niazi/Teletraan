-- Migration 019: Create inventory_sync_log table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Tracks catalog/inventory sync operations

CREATE TABLE IF NOT EXISTS inventory_sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id),
    sync_source VARCHAR(100),
    file_name VARCHAR(500),
    file_url TEXT,
    status VARCHAR(50),
    rows_processed INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    rows_inserted INTEGER DEFAULT 0,
    rows_failed INTEGER DEFAULT 0,
    error_details JSONB DEFAULT '[]',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
