# TELETRAAN — Database Schema

## Overview

TELETRAAN uses Supabase (PostgreSQL) with 26 tables. All tables use UUID
primary keys. Multi-tenancy is enforced via `distributor_id` FK on all
tenant-scoped tables.

**Conventions:**
- All monetary amounts stored as `BIGINT` in **paisas** (PKR × 100)
- Timestamps are `TIMESTAMPTZ` (UTC)
- Soft deletes via `is_active` flag where applicable
- Migrations numbered sequentially: `001_` through `028_`

---

## Table Reference

### 1. `subscription_plans`
Defines available subscription tiers for distributors.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Plan identifier |
| `name` | VARCHAR | Plan name (Basic, Pro, Enterprise) |
| `slug` | VARCHAR UNIQUE | URL-safe identifier |
| `description` | TEXT | Plan description |
| `price_paisas` | BIGINT | Monthly price in paisas |
| `duration_days` | INT | Subscription duration |
| `max_customers` | INT | Customer limit |
| `max_orders_per_day` | INT | Daily order cap |
| `features` | JSONB | Feature flags |
| `is_active` | BOOLEAN | Whether plan is available |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 2. `distributors`
Medicine distributor accounts (tenants).

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Distributor identifier |
| `business_name` | VARCHAR | Business name |
| `owner_name` | VARCHAR | Owner's name |
| `whatsapp_number` | VARCHAR | Owner's WhatsApp number |
| `phone_number_id` | VARCHAR | Meta phone number ID |
| `waba_id` | VARCHAR | WhatsApp Business Account ID |
| `access_token` | TEXT | Encrypted Meta API access token |
| `city` | VARCHAR | Business city |
| `subscription_plan_id` | UUID FK | References subscription_plans |
| `subscription_status` | VARCHAR | active, expired, suspended |
| `subscription_expires_at` | TIMESTAMPTZ | Expiry date |
| `is_active` | BOOLEAN | Account active flag |
| `settings` | JSONB | Distributor-specific config |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 3. `customers`
Retailer customers belonging to a distributor.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Customer identifier |
| `distributor_id` | UUID FK | Tenant scope |
| `whatsapp_number` | VARCHAR | Customer's WhatsApp |
| `name` | VARCHAR | Customer name |
| `shop_name` | VARCHAR | Shop/business name |
| `address` | TEXT | Delivery address |
| `city` | VARCHAR | City |
| `delivery_zone_id` | UUID FK | References delivery_zones |
| `language_preference` | VARCHAR | roman_urdu, urdu, english |
| `is_verified` | BOOLEAN | Verified customer |
| `credit_limit_paisas` | BIGINT | Credit limit |
| `outstanding_balance_paisas` | BIGINT | Outstanding balance |
| `is_active` | BOOLEAN | Active flag |
| `is_blocked` | BOOLEAN | Blocked flag |
| `blocked_reason` | TEXT | Reason for blocking |
| `blocked_at` | TIMESTAMPTZ | When blocked |
| `last_order_at` | TIMESTAMPTZ | Last order date |
| `total_orders` | INT | Lifetime order count |
| `total_spend_paisas` | BIGINT | Lifetime spend |
| `tags` | JSONB | Customer tags |
| `notes` | TEXT | Internal notes |
| `metadata` | JSONB | Additional data |
| `registered_at` | TIMESTAMPTZ | Registration date |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 4. `catalog`
Medicine catalog for each distributor.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Catalog item ID |
| `distributor_id` | UUID FK | Tenant scope |
| `medicine_name` | VARCHAR | Normalised name |
| `generic_name` | VARCHAR | Generic/salt name |
| `manufacturer` | VARCHAR | Manufacturer |
| `category` | VARCHAR | Category (tablet, syrup, etc.) |
| `unit` | VARCHAR | Sale unit (strip, bottle) |
| `price_per_unit_paisas` | BIGINT | Price per unit |
| `stock_quantity` | INT | Current stock |
| `min_stock_threshold` | INT | Reorder threshold |
| `is_active` | BOOLEAN | Available for ordering |
| `search_keywords` | TEXT[] | Search terms |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 5. `discount_rules`
Discount rules per distributor.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Rule identifier |
| `distributor_id` | UUID FK | Tenant scope |
| `name` | VARCHAR | Rule name |
| `rule_type` | VARCHAR | percentage, fixed, bogo, tiered |
| `conditions` | JSONB | Trigger conditions |
| `discount_value` | INT | Discount amount/percentage |
| `is_active` | BOOLEAN | Active flag |
| `priority` | INT | Rule priority |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 6. `delivery_zones`
Geographic delivery zones.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Zone identifier |
| `distributor_id` | UUID FK | Tenant scope |
| `name` | VARCHAR | Zone name |
| `delivery_charge_paisas` | BIGINT | Delivery fee |
| `estimated_hours` | INT | Estimated delivery time |
| `is_active` | BOOLEAN | Active flag |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 7. `sessions`
WhatsApp conversation sessions (FSM state).

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Session identifier |
| `distributor_id` | UUID FK | Tenant scope |
| `whatsapp_number` | VARCHAR | Customer's number |
| `customer_id` | UUID FK | References customers |
| `channel` | VARCHAR | A or B |
| `current_state` | VARCHAR | FSM state name |
| `previous_state` | VARCHAR | Previous FSM state |
| `state_data` | JSONB | State-specific data |
| `conversation_history` | JSONB | AI conversation context |
| `pending_order_draft` | JSONB | In-progress order |
| `language` | VARCHAR | Detected language |
| `retry_count` | INT | Retry counter |
| `handoff_mode` | BOOLEAN | Human handoff active |
| `last_message_at` | TIMESTAMPTZ | Last activity |
| `expires_at` | TIMESTAMPTZ | Session expiry |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 8. `orders`
Customer orders.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Order identifier |
| `order_number` | VARCHAR UNIQUE | Human-readable number |
| `distributor_id` | UUID FK | Tenant scope |
| `customer_id` | UUID FK | References customers |
| `status` | VARCHAR | pending, confirmed, dispatched, delivered, cancelled |
| `subtotal_paisas` | BIGINT | Pre-discount total |
| `discount_paisas` | BIGINT | Applied discount |
| `delivery_charges_paisas` | BIGINT | Delivery fee |
| `total_paisas` | BIGINT | Final total |
| `payment_status` | VARCHAR | unpaid, pending, paid, failed |
| `payment_method` | VARCHAR | Gateway used |
| `delivery_address` | TEXT | Delivery address |
| `delivery_zone_id` | UUID FK | Delivery zone |
| `estimated_delivery_at` | TIMESTAMPTZ | ETA |
| `dispatched_at` | TIMESTAMPTZ | Dispatch time |
| `delivered_at` | TIMESTAMPTZ | Delivery time |
| `notes` | TEXT | Customer notes |
| `internal_notes` | TEXT | Staff notes |
| `discount_requests` | JSONB | Discount request history |
| `discount_approval_status` | VARCHAR | not_requested, pending, approved, rejected |
| `source` | VARCHAR | whatsapp, admin, reorder |
| `is_quick_reorder` | BOOLEAN | Reorder flag |
| `source_order_id` | UUID FK | Source for reorders |
| `order_context_snapshot` | JSONB | Full context at confirmation |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 9. `order_items`
Line items within orders.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Item identifier |
| `order_id` | UUID FK | References orders |
| `distributor_id` | UUID FK | Tenant scope |
| `catalog_id` | UUID FK | References catalog |
| `medicine_name_raw` | VARCHAR | Raw customer input |
| `medicine_name` | VARCHAR | Normalised name |
| `unit` | VARCHAR | Sale unit |
| `quantity_ordered` | INT | Ordered quantity |
| `quantity_fulfilled` | INT | Fulfilled quantity |
| `price_per_unit_paisas` | BIGINT | Unit price |
| `line_total_paisas` | BIGINT | Line total |
| `discount_paisas` | BIGINT | Line discount |
| `bonus_units_given` | INT | Free bonus units |
| `is_out_of_stock_order` | BOOLEAN | Ordered despite OOS |
| `is_unlisted_item` | BOOLEAN | Not in catalog |
| `input_method` | VARCHAR | text, voice, button |
| `fuzzy_match_score` | FLOAT | Match confidence 0-100 |
| `notes` | TEXT | Item notes |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 10. `order_status_history`
Audit trail for order status changes.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Record identifier |
| `order_id` | UUID FK | References orders |
| `from_status` | VARCHAR | Previous status |
| `to_status` | VARCHAR | New status |
| `changed_by` | VARCHAR | system, admin, customer |
| `reason` | TEXT | Change reason |
| `created_at` | TIMESTAMPTZ | Change timestamp |

### 11. `payments`
Payment transactions.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Payment identifier |
| `order_id` | UUID FK | References orders |
| `distributor_id` | UUID FK | Tenant scope |
| `gateway` | VARCHAR | jazzcash, easypaisa, etc. |
| `amount_paisas` | BIGINT | Payment amount |
| `status` | VARCHAR | pending, completed, failed, refunded |
| `gateway_reference` | VARCHAR | Gateway transaction ID |
| `payment_url` | TEXT | Payment link URL |
| `callback_data` | JSONB | Gateway callback payload |
| `expires_at` | TIMESTAMPTZ | Payment link expiry |
| `completed_at` | TIMESTAMPTZ | Completion time |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 12. `complaints`
Customer complaints.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Complaint identifier |
| `distributor_id` | UUID FK | Tenant scope |
| `customer_id` | UUID FK | References customers |
| `order_id` | UUID FK | Related order (optional) |
| `category` | VARCHAR | Complaint category |
| `description` | TEXT | Complaint details |
| `status` | VARCHAR | open, in_progress, resolved, closed |
| `resolution` | TEXT | Resolution notes |
| `priority` | VARCHAR | low, medium, high, critical |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 13. `support_tickets`
Internal support tickets.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Ticket identifier |
| `distributor_id` | UUID FK | Tenant scope |
| `subject` | VARCHAR | Ticket subject |
| `description` | TEXT | Details |
| `status` | VARCHAR | open, in_progress, resolved, closed |
| `priority` | VARCHAR | low, medium, high |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 14. `prospects`
Channel B sales prospects.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Prospect identifier |
| `whatsapp_number` | VARCHAR | Prospect's WhatsApp |
| `name` | VARCHAR | Contact name |
| `business_name` | VARCHAR | Business name |
| `city` | VARCHAR | City |
| `interest_level` | VARCHAR | cold, warm, hot, qualified |
| `status` | VARCHAR | new, contacted, qualified, converted, lost |
| `notes` | TEXT | Sales notes |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 15. `service_registry`
Available TELETRAAN service packages.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Service identifier |
| `name` | VARCHAR | Service name |
| `slug` | VARCHAR UNIQUE | URL-safe identifier |
| `description` | TEXT | Service description |
| `features` | JSONB | Feature list |
| `price_paisas` | BIGINT | Price |
| `is_active` | BOOLEAN | Active flag |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 16. `notifications_log`
Log of all outgoing notifications.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Log entry ID |
| `distributor_id` | UUID FK | Tenant scope |
| `recipient_number` | VARCHAR | Recipient WhatsApp |
| `notification_type` | VARCHAR | order_update, reminder, etc. |
| `template_name` | VARCHAR | Template used |
| `status` | VARCHAR | sent, delivered, failed |
| `message_id` | VARCHAR | Meta message ID |
| `metadata` | JSONB | Additional data |
| `created_at` | TIMESTAMPTZ | Sent timestamp |

### 17. `audit_log`
System audit trail.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Audit entry ID |
| `event_type` | VARCHAR | Event category |
| `actor` | VARCHAR | Who triggered it |
| `resource_type` | VARCHAR | Affected resource type |
| `resource_id` | VARCHAR | Affected resource ID |
| `details` | JSONB | Event details |
| `ip_address` | VARCHAR | Source IP |
| `created_at` | TIMESTAMPTZ | Event timestamp |

### 18. `inventory_sync_log`
Inventory synchronisation history.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Sync entry ID |
| `distributor_id` | UUID FK | Tenant scope |
| `items_synced` | INT | Number of items synced |
| `items_added` | INT | New items added |
| `items_updated` | INT | Items updated |
| `status` | VARCHAR | success, partial, failed |
| `error_message` | TEXT | Error details if any |
| `created_at` | TIMESTAMPTZ | Sync timestamp |

### 19. `analytics_events`
Raw analytics events.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Event ID |
| `distributor_id` | UUID FK | Tenant scope |
| `event_type` | VARCHAR | Event category |
| `event_data` | JSONB | Event payload |
| `session_id` | UUID FK | Associated session |
| `created_at` | TIMESTAMPTZ | Event timestamp |

### 20. `rate_limits`
Per-number rate limit tracking.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Record ID |
| `identifier` | VARCHAR | WhatsApp number |
| `window_start` | TIMESTAMPTZ | Window start time |
| `request_count` | INT | Requests in window |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 21. `scheduled_messages`
Messages scheduled for future delivery.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Message ID |
| `distributor_id` | UUID FK | Tenant scope |
| `recipient_number` | VARCHAR | Target number |
| `message_type` | VARCHAR | Type of message |
| `message_content` | JSONB | Message payload |
| `scheduled_for` | TIMESTAMPTZ | Delivery time |
| `status` | VARCHAR | pending, sent, failed, cancelled |
| `sent_at` | TIMESTAMPTZ | Actual send time |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### 22. `catalog_import_history`
Catalog import/update history.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Import ID |
| `distributor_id` | UUID FK | Tenant scope |
| `filename` | VARCHAR | Source file name |
| `items_imported` | INT | Items processed |
| `items_failed` | INT | Failed items |
| `status` | VARCHAR | success, partial, failed |
| `created_at` | TIMESTAMPTZ | Import timestamp |

### 23. `bot_configuration`
Per-distributor bot configuration.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Config ID |
| `distributor_id` | UUID FK | Tenant scope |
| `config_key` | VARCHAR | Configuration key |
| `config_value` | JSONB | Configuration value |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

### 24-26. Analytics Tables

**`analytics_daily`** — Daily aggregated metrics per distributor.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Record ID |
| `distributor_id` | UUID FK | Tenant scope |
| `date` | DATE | Metric date |
| `total_orders` | INT | Orders placed |
| `total_revenue_paisas` | BIGINT | Revenue |
| `unique_customers` | INT | Unique customers |
| `avg_order_value_paisas` | BIGINT | AOV |
| `top_items` | JSONB | Top selling items |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

**`analytics_top_items`** — Top-selling items per period.

**`analytics_customer_events`** — Customer lifecycle events (churn, reactivation).

---

## Indexes

Key indexes are created by migrations:
- `idx_sessions_distributor_number` on `sessions(distributor_id, whatsapp_number)`
- `idx_orders_distributor_status` on `orders(distributor_id, status)`
- `idx_orders_customer` on `orders(distributor_id, customer_id)`
- `idx_catalog_distributor_active` on `catalog(distributor_id, is_active)`
- `idx_customers_distributor_number` on `customers(distributor_id, whatsapp_number)`
- `idx_payments_order` on `payments(order_id)`
- `idx_analytics_events_type` on `analytics_events(distributor_id, event_type)`

## Row Level Security

RLS policies enforced at the Supabase level:
- All tenant tables filtered by `distributor_id`
- Service role key bypasses RLS for backend operations
- Anon key (if used) restricted to read-only on public tables
