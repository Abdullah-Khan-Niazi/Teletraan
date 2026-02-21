-- Migration 027: Seed initial data
-- Idempotent: ON CONFLICT DO NOTHING

-- Seed subscription plans
INSERT INTO subscription_plans (name, description, monthly_fee_paisas, setup_fee_paisas, max_orders_per_month, max_customers, features, is_active)
VALUES
    ('Starter', 'Basic plan for small distributors', 500000, 0, 500, 100, '{"excel_reports": true, "voice_orders": false, "pdf_catalog": false}', true),
    ('Professional', 'Full-featured plan for growing businesses', 1500000, 500000, 2000, 500, '{"excel_reports": true, "voice_orders": true, "pdf_catalog": true, "analytics": true}', true),
    ('Enterprise', 'Unlimited plan for large distributors', 3000000, 1000000, NULL, NULL, '{"excel_reports": true, "voice_orders": true, "pdf_catalog": true, "analytics": true, "priority_support": true, "custom_branding": true}', true)
ON CONFLICT DO NOTHING;

-- Seed the TELETRAAN service in service_registry (for Channel B)
INSERT INTO service_registry (name, slug, description, short_description, setup_fee_paisas, monthly_fee_paisas, is_available)
VALUES
    ('TELETRAAN Order Bot', 'teletraan-order-bot', 'WhatsApp-based intelligent order management system for medicine distributors. Handles retailer orders via voice and text with fuzzy matching, live billing, discount negotiation, and automated order logging.', 'WhatsApp order bot for medicine distributors', 500000, 1500000, true)
ON CONFLICT (slug) DO NOTHING;
