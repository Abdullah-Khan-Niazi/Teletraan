-- Migration 026: Create all performance indexes
-- Idempotent: CREATE INDEX IF NOT EXISTS

-- Customers: fast lookup by distributor + WhatsApp number
CREATE INDEX IF NOT EXISTS idx_customers_distributor_number ON customers (distributor_id, whatsapp_number);

-- Sessions: fast lookup by distributor + WhatsApp number
CREATE INDEX IF NOT EXISTS idx_sessions_distributor_number ON sessions (distributor_id, whatsapp_number);

-- Sessions: find expiring active sessions for cleanup
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions (expires_at) WHERE current_state != 'idle';

-- Orders: distributor dashboard sorted by date
CREATE INDEX IF NOT EXISTS idx_orders_distributor_date ON orders (distributor_id, created_at DESC);

-- Orders: filter by status per distributor
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (distributor_id, status);

-- Orders: lookup by customer
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id);

-- Order items: lookup by parent order
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);

-- Catalog: active items per distributor
CREATE INDEX IF NOT EXISTS idx_catalog_active ON catalog (distributor_id) WHERE is_active = true AND is_deleted = false;

-- Catalog: fast prefix search on medicine name
CREATE INDEX IF NOT EXISTS idx_catalog_name ON catalog (distributor_id, medicine_name text_pattern_ops);

-- Catalog: GIN index for keyword array search
CREATE INDEX IF NOT EXISTS idx_catalog_keywords ON catalog USING GIN (search_keywords);

-- Payments: lookup by distributor + status
CREATE INDEX IF NOT EXISTS idx_payments_distributor ON payments (distributor_id, status);

-- Payments: lookup by gateway transaction ID
CREATE INDEX IF NOT EXISTS idx_payments_gateway_txn ON payments (gateway_transaction_id);

-- Distributors: find expiring subscriptions
CREATE INDEX IF NOT EXISTS idx_distributors_subscription ON distributors (subscription_end) WHERE subscription_status IN ('active', 'expiring');

-- Analytics: time-series queries per distributor
CREATE INDEX IF NOT EXISTS idx_analytics_distributor_time ON analytics_events (distributor_id, occurred_at DESC);

-- Scheduled messages: find due messages for processing
CREATE INDEX IF NOT EXISTS idx_scheduled_messages_due ON scheduled_messages (scheduled_for, status) WHERE status = 'pending';

-- Audit log: lookup by entity type + ID
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log (entity_type, entity_id);

-- Rate limits: fast lookup for throttle checks
CREATE INDEX IF NOT EXISTS idx_rate_limits_lookup ON rate_limits (distributor_id, whatsapp_number, window_start);
