-- Migration 023: Create catalog_import_history table
-- Idempotent: CREATE TABLE IF NOT EXISTS
-- Multi-tenant: distributor_id FK
-- Tracks bulk catalog import operations

CREATE TABLE IF NOT EXISTS catalog_import_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id UUID NOT NULL REFERENCES distributors(id),
    file_name VARCHAR(500),
    storage_path TEXT,
    items_total INTEGER DEFAULT 0,
    items_imported INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    status VARCHAR(50),
    error_log JSONB DEFAULT '[]',
    imported_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
