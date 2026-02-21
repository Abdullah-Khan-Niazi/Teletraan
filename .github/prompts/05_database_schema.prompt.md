# TELETRAAN Database Schema — All 27 Tables + Indexes

**Rules:** PostgreSQL via Supabase. Multi-tenant (distributor_id FK on all tenant tables).
RLS at DB level. UUIDs as PKs. Financial amounts in **paisas (BIGINT) — no floats**.
Soft deletes where applicable. All tables have `created_at`/`updated_at`.
`updated_at` maintained by DB trigger on all tables.

---

## Table: subscription_plans
```sql
id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4()
name                    VARCHAR(100) NOT NULL
description             TEXT
monthly_fee_paisas      BIGINT NOT NULL
setup_fee_paisas        BIGINT NOT NULL DEFAULT 0
max_orders_per_month    INTEGER           -- NULL = unlimited
max_customers           INTEGER           -- NULL = unlimited
features                JSONB DEFAULT '{}'
is_active               BOOLEAN DEFAULT true
created_at              TIMESTAMPTZ DEFAULT NOW()
updated_at              TIMESTAMPTZ DEFAULT NOW()
```

## Table: distributors
```sql
id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4()
business_name               VARCHAR(255) NOT NULL
owner_name                  VARCHAR(255) NOT NULL
whatsapp_number             VARCHAR(20) NOT NULL UNIQUE
whatsapp_phone_number_id    VARCHAR(100) NOT NULL UNIQUE
whatsapp_group_id           VARCHAR(100)
city                        VARCHAR(100)
address                     TEXT
cnic_encrypted              TEXT          -- Fernet-encrypted CNIC
email                       VARCHAR(255)
plan_id                     UUID REFERENCES subscription_plans(id)
subscription_status         VARCHAR(50) NOT NULL DEFAULT 'trial'
                            -- ENUM: trial, active, expiring, suspended, cancelled
subscription_start          TIMESTAMPTZ
subscription_end            TIMESTAMPTZ
trial_end                   TIMESTAMPTZ
grace_period_days           INTEGER DEFAULT 3
deployment_version          VARCHAR(50)
bot_language_default        VARCHAR(20) DEFAULT 'roman_urdu'
catalog_last_synced         TIMESTAMPTZ
catalog_sync_url            TEXT    -- Google Drive or Supabase Storage URL
onboarding_completed        BOOLEAN DEFAULT false
onboarding_completed_at     TIMESTAMPTZ
preferred_payment_gateway   VARCHAR(50)  -- Override for subscription fees
is_active                   BOOLEAN DEFAULT true
is_deleted                  BOOLEAN DEFAULT false
deleted_at                  TIMESTAMPTZ
notes                       TEXT
metadata                    JSONB DEFAULT '{}'
created_at                  TIMESTAMPTZ DEFAULT NOW()
updated_at                  TIMESTAMPTZ DEFAULT NOW()
```

## Table: customers
```sql
id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id          UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE
whatsapp_number         VARCHAR(20) NOT NULL
name                    VARCHAR(255) NOT NULL
shop_name               VARCHAR(255) NOT NULL
address                 TEXT
city                    VARCHAR(100)
delivery_zone_id        UUID REFERENCES delivery_zones(id)
language_preference     VARCHAR(20) DEFAULT 'roman_urdu'
is_verified             BOOLEAN DEFAULT false
credit_limit_paisas     BIGINT DEFAULT 0
outstanding_balance_paisas BIGINT DEFAULT 0
is_active               BOOLEAN DEFAULT true
is_blocked              BOOLEAN DEFAULT false
blocked_reason          TEXT
blocked_at              TIMESTAMPTZ
last_order_at           TIMESTAMPTZ
total_orders            INTEGER DEFAULT 0
total_spend_paisas      BIGINT DEFAULT 0
tags                    TEXT[]
notes                   TEXT
metadata                JSONB DEFAULT '{}'
registered_at           TIMESTAMPTZ DEFAULT NOW()
created_at              TIMESTAMPTZ DEFAULT NOW()
updated_at              TIMESTAMPTZ DEFAULT NOW()
UNIQUE(distributor_id, whatsapp_number)
```

## Table: catalog
```sql
id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id                  UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE
medicine_name                   VARCHAR(500) NOT NULL
generic_name                    VARCHAR(500)
brand_name                      VARCHAR(255)
manufacturer                    VARCHAR(255)
category                        VARCHAR(100)
form                            VARCHAR(100)    -- tablet, capsule, syrup, injection, sachet, cream, drops
strength                        VARCHAR(100)
unit                            VARCHAR(50)     -- strip, box, carton, bottle, vial, sachet
units_per_pack                  INTEGER DEFAULT 1
price_per_unit_paisas           BIGINT NOT NULL
mrp_paisas                      BIGINT
stock_quantity                  INTEGER DEFAULT 0
reserved_quantity               INTEGER DEFAULT 0   -- Qty reserved in pending confirmed orders
low_stock_threshold             INTEGER DEFAULT 10
is_in_stock                     BOOLEAN DEFAULT true
allow_order_when_out_of_stock   BOOLEAN DEFAULT true
requires_prescription           BOOLEAN DEFAULT false
is_controlled_substance         BOOLEAN DEFAULT false
search_keywords                 TEXT[]
sku                             VARCHAR(100)
barcode                         VARCHAR(100)
image_url                       TEXT
is_active                       BOOLEAN DEFAULT true
is_deleted                      BOOLEAN DEFAULT false
deleted_at                      TIMESTAMPTZ
metadata                        JSONB DEFAULT '{}'
created_at                      TIMESTAMPTZ DEFAULT NOW()
updated_at                      TIMESTAMPTZ DEFAULT NOW()
UNIQUE(distributor_id, sku) WHERE sku IS NOT NULL AND is_deleted = false
```

## Table: discount_rules
```sql
id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id                  UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE
catalog_id                      UUID REFERENCES catalog(id) ON DELETE CASCADE  -- NULL = all items
rule_name                       VARCHAR(255)
rule_type                       VARCHAR(50) NOT NULL
                                -- ENUM: bonus_units, percentage_discount, flat_discount,
                                --       minimum_order, tiered_pricing
buy_quantity                    INTEGER
get_quantity                    INTEGER
discount_percentage             DECIMAL(5,2)
discount_flat_paisas            BIGINT
minimum_order_quantity          INTEGER
minimum_order_value_paisas      BIGINT
applicable_customer_tags        TEXT[]  -- NULL = all customers
priority                        INTEGER DEFAULT 0   -- Higher = applied first
is_stackable                    BOOLEAN DEFAULT false
valid_from                      TIMESTAMPTZ
valid_until                     TIMESTAMPTZ
usage_limit                     INTEGER             -- NULL = unlimited
usage_count                     INTEGER DEFAULT 0
is_active                       BOOLEAN DEFAULT true
created_at                      TIMESTAMPTZ DEFAULT NOW()
updated_at                      TIMESTAMPTZ DEFAULT NOW()
```

## Table: delivery_zones
```sql
id                                          UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id                              UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE
name                                        VARCHAR(255) NOT NULL
areas                                       TEXT[]
delivery_days                               TEXT[]
estimated_delivery_hours                    INTEGER DEFAULT 24
delivery_charges_paisas                     BIGINT DEFAULT 0
minimum_order_for_free_delivery_paisas      BIGINT
is_active                                   BOOLEAN DEFAULT true
created_at                                  TIMESTAMPTZ DEFAULT NOW()
updated_at                                  TIMESTAMPTZ DEFAULT NOW()
```

## Table: sessions (process-restart-safe)
```sql
id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id          UUID NOT NULL REFERENCES distributors(id) ON DELETE CASCADE
whatsapp_number         VARCHAR(20) NOT NULL
customer_id             UUID REFERENCES customers(id)
channel                 VARCHAR(10) NOT NULL DEFAULT 'A'  -- ENUM: A, B
current_state           VARCHAR(100) NOT NULL DEFAULT 'idle'
previous_state          VARCHAR(100)
state_data              JSONB DEFAULT '{}'
conversation_history    JSONB DEFAULT '[]'  -- Last 15 turns for AI context (rolling)
pending_order_draft     JSONB DEFAULT '{}'  -- FULL order context — see 07_order_context_schema.prompt.md
language                VARCHAR(20) DEFAULT 'roman_urdu'
retry_count             INTEGER DEFAULT 0
handoff_mode            BOOLEAN DEFAULT false  -- True: human agent requested, AI paused
last_message_at         TIMESTAMPTZ DEFAULT NOW()
expires_at              TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
created_at              TIMESTAMPTZ DEFAULT NOW()
updated_at              TIMESTAMPTZ DEFAULT NOW()
UNIQUE(distributor_id, whatsapp_number)
```

## Table: orders
```sql
id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4()
order_number                VARCHAR(20) NOT NULL UNIQUE
distributor_id              UUID NOT NULL REFERENCES distributors(id)
customer_id                 UUID NOT NULL REFERENCES customers(id)
status                      VARCHAR(50) NOT NULL DEFAULT 'pending'
                            -- ENUM: pending, confirmed, processing, dispatched,
                            --       delivered, cancelled, returned, partially_fulfilled
subtotal_paisas             BIGINT NOT NULL DEFAULT 0
discount_paisas             BIGINT DEFAULT 0
delivery_charges_paisas     BIGINT DEFAULT 0
total_paisas                BIGINT NOT NULL DEFAULT 0
payment_status              VARCHAR(50) DEFAULT 'unpaid'
                            -- ENUM: unpaid, partial, paid, credit
payment_method              VARCHAR(50)
                            -- ENUM: cash, credit, jazzcash, easypaisa, safepay, nayapay,
                            --       bank_transfer, dummy
delivery_address            TEXT
delivery_zone_id            UUID REFERENCES delivery_zones(id)
estimated_delivery_at       TIMESTAMPTZ
dispatched_at               TIMESTAMPTZ
delivered_at                TIMESTAMPTZ
notes                       TEXT
internal_notes              TEXT
discount_requests           JSONB DEFAULT '[]'
discount_approval_status    VARCHAR(50) DEFAULT 'not_requested'
source                      VARCHAR(50) DEFAULT 'whatsapp'
is_quick_reorder            BOOLEAN DEFAULT false
source_order_id             UUID REFERENCES orders(id)  -- For quick reorders
whatsapp_logged_at          TIMESTAMPTZ
excel_logged_at             TIMESTAMPTZ
order_context_snapshot      JSONB DEFAULT '{}'  -- Snapshot at confirmation — for audit
metadata                    JSONB DEFAULT '{}'
created_at                  TIMESTAMPTZ DEFAULT NOW()
updated_at                  TIMESTAMPTZ DEFAULT NOW()
```

## Table: order_items
```sql
id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4()
order_id                UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE
distributor_id          UUID NOT NULL REFERENCES distributors(id)
catalog_id              UUID REFERENCES catalog(id)
medicine_name_raw       VARCHAR(500)  -- Exactly as customer typed/said
medicine_name           VARCHAR(500) NOT NULL  -- Matched/display name
unit                    VARCHAR(50)
quantity_ordered        INTEGER NOT NULL
quantity_fulfilled      INTEGER DEFAULT 0
price_per_unit_paisas   BIGINT NOT NULL
line_total_paisas       BIGINT NOT NULL
discount_paisas         BIGINT DEFAULT 0
bonus_units_given       INTEGER DEFAULT 0
is_out_of_stock_order   BOOLEAN DEFAULT false
is_unlisted_item        BOOLEAN DEFAULT false
input_method            VARCHAR(20)   -- ENUM: text, voice, button_selection
fuzzy_match_score       DECIMAL(5,2)
notes                   TEXT
created_at              TIMESTAMPTZ DEFAULT NOW()
```

## Table: order_status_history
```sql
id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE
distributor_id  UUID NOT NULL
from_status     VARCHAR(50)
to_status       VARCHAR(50) NOT NULL
changed_by      VARCHAR(50)  -- ENUM: customer, distributor, system, scheduler
notes           TEXT
created_at      TIMESTAMPTZ DEFAULT NOW()
```

## Table: payments
```sql
id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4()
transaction_reference       VARCHAR(255) NOT NULL UNIQUE
payment_type                VARCHAR(50) NOT NULL
                            -- ENUM: subscription_fee, setup_fee, order_payment
distributor_id              UUID REFERENCES distributors(id)
order_id                    UUID REFERENCES orders(id)
customer_id                 UUID REFERENCES customers(id)
gateway                     VARCHAR(50) NOT NULL
                            -- ENUM: jazzcash, easypaisa, safepay, nayapay,
                            --       bank_transfer, dummy, manual
gateway_transaction_id      VARCHAR(255)
gateway_order_id            VARCHAR(255)
amount_paisas               BIGINT NOT NULL
currency                    VARCHAR(10) DEFAULT 'PKR'
status                      VARCHAR(50) NOT NULL DEFAULT 'pending'
                            -- ENUM: pending, completed, failed, refunded, expired, cancelled
payment_link                TEXT
payment_link_expires_at     TIMESTAMPTZ
paid_at                     TIMESTAMPTZ
gateway_response            JSONB DEFAULT '{}'
failure_reason              TEXT
refund_amount_paisas        BIGINT DEFAULT 0
refunded_at                 TIMESTAMPTZ
screenshot_storage_path     TEXT   -- For bank_transfer screenshots
manual_confirmed_at         TIMESTAMPTZ
metadata                    JSONB DEFAULT '{}'
created_at                  TIMESTAMPTZ DEFAULT NOW()
updated_at                  TIMESTAMPTZ DEFAULT NOW()
```

## Table: complaints
```sql
id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4()
ticket_number       VARCHAR(20) NOT NULL UNIQUE
distributor_id      UUID NOT NULL REFERENCES distributors(id)
customer_id         UUID NOT NULL REFERENCES customers(id)
order_id            UUID REFERENCES orders(id)
category            VARCHAR(100) NOT NULL
                    -- wrong_item, late_delivery, damaged_goods, expired_medicine,
                    --   short_quantity, billing_error, other
description         TEXT NOT NULL
status              VARCHAR(50) NOT NULL DEFAULT 'open'
                    -- ENUM: open, in_progress, resolved, closed, rejected
priority            VARCHAR(20) DEFAULT 'normal'  -- ENUM: low, normal, high, urgent
resolution_notes    TEXT
resolved_at         TIMESTAMPTZ
escalated_to_owner  BOOLEAN DEFAULT false
media_urls          TEXT[]
metadata            JSONB DEFAULT '{}'
created_at          TIMESTAMPTZ DEFAULT NOW()
updated_at          TIMESTAMPTZ DEFAULT NOW()
```

## Table: support_tickets
```sql
id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
ticket_number   VARCHAR(20) NOT NULL UNIQUE
distributor_id  UUID NOT NULL REFERENCES distributors(id)
category        VARCHAR(100)
                -- bot_issue, billing, setup, feature_request, gateway_issue, other
description     TEXT NOT NULL
status          VARCHAR(50) DEFAULT 'open'  -- ENUM: open, in_progress, resolved, closed
priority        VARCHAR(20) DEFAULT 'normal'
owner_response  TEXT
resolved_at     TIMESTAMPTZ
metadata        JSONB DEFAULT '{}'
created_at      TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW()
```

## Table: prospects
```sql
id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4()
whatsapp_number             VARCHAR(20) NOT NULL UNIQUE
name                        VARCHAR(255)
business_name               VARCHAR(255)
business_type               VARCHAR(100)
city                        VARCHAR(100)
estimated_retailer_count    INTEGER
monthly_order_estimate      INTEGER
interested_service_id       UUID REFERENCES service_registry(id)
status                      VARCHAR(50) DEFAULT 'new'
                            -- new, qualified, demo_booked, proposal_sent,
                            --   payment_pending, converted, lost, waitlisted
demo_booked_at              TIMESTAMPTZ
demo_slot                   TIMESTAMPTZ
converted_at                TIMESTAMPTZ
converted_distributor_id    UUID REFERENCES distributors(id)
lost_reason                 TEXT
waitlist_service            VARCHAR(255)
follow_up_at                TIMESTAMPTZ
preferred_payment_gateway   VARCHAR(50)
metadata                    JSONB DEFAULT '{}'
created_at                  TIMESTAMPTZ DEFAULT NOW()
updated_at                  TIMESTAMPTZ DEFAULT NOW()
```

## Table: service_registry
```sql
id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4()
name                    VARCHAR(255) NOT NULL
slug                    VARCHAR(100) NOT NULL UNIQUE
description             TEXT
short_description       VARCHAR(500)
setup_fee_paisas        BIGINT DEFAULT 0
monthly_fee_paisas      BIGINT DEFAULT 0
demo_video_url          TEXT
catalog_url             TEXT
target_business_types   TEXT[]
sales_flow_handler      VARCHAR(100)
is_available            BOOLEAN DEFAULT true
is_coming_soon          BOOLEAN DEFAULT false
metadata                JSONB DEFAULT '{}'
created_at              TIMESTAMPTZ DEFAULT NOW()
updated_at              TIMESTAMPTZ DEFAULT NOW()
```

## Table: notifications_log
```sql
id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id                  UUID REFERENCES distributors(id)
recipient_number_masked         VARCHAR(20)   -- Last 4 digits only — PII protection
recipient_type                  VARCHAR(50)   -- customer, distributor, prospect, owner
notification_type               VARCHAR(100) NOT NULL
message_preview                 VARCHAR(500)
whatsapp_message_id             VARCHAR(255)
delivery_status                 VARCHAR(50) DEFAULT 'sent'
                                -- ENUM: sent, delivered, read, failed
delivery_status_updated_at      TIMESTAMPTZ
reference_id                    UUID
reference_type                  VARCHAR(50)
error_message                   TEXT
sent_at                         TIMESTAMPTZ DEFAULT NOW()
```

## Table: audit_log (**IMMUTABLE — no updates, no deletes. RLS: INSERT only**)
```sql
id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4()
actor_type                  VARCHAR(50) NOT NULL  -- customer, distributor, owner, system, scheduler
actor_id                    UUID
actor_whatsapp_masked       VARCHAR(20)  -- Last 4 digits only
distributor_id              UUID REFERENCES distributors(id)
action                      VARCHAR(255) NOT NULL
entity_type                 VARCHAR(100)
entity_id                   UUID
before_state                JSONB
after_state                 JSONB
metadata                    JSONB DEFAULT '{}'
created_at                  TIMESTAMPTZ DEFAULT NOW()
```

## Table: inventory_sync_log
```sql
id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id  UUID NOT NULL REFERENCES distributors(id)
sync_source     VARCHAR(100)  -- google_drive, supabase_upload, manual_api
file_name       VARCHAR(500)
file_url        TEXT
status          VARCHAR(50)   -- started, completed, failed, partial
rows_processed  INTEGER DEFAULT 0
rows_updated    INTEGER DEFAULT 0
rows_inserted   INTEGER DEFAULT 0
rows_failed     INTEGER DEFAULT 0
error_details   JSONB DEFAULT '[]'
started_at      TIMESTAMPTZ DEFAULT NOW()
completed_at    TIMESTAMPTZ
```

## Table: analytics_events
```sql
id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id  UUID REFERENCES distributors(id)
event_type      VARCHAR(255) NOT NULL
channel         VARCHAR(10)     -- A, B, system
customer_id     UUID REFERENCES customers(id)
session_id      UUID REFERENCES sessions(id)
properties      JSONB DEFAULT '{}'
duration_ms     INTEGER
ai_provider     VARCHAR(50)     -- Which AI provider handled this event
ai_tokens_used  INTEGER
ai_cost_paisas  INTEGER
payment_gateway VARCHAR(50)     -- Which gateway if payment event
occurred_at     TIMESTAMPTZ DEFAULT NOW()
```

## Table: rate_limits
```sql
id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id  UUID REFERENCES distributors(id)
whatsapp_number VARCHAR(20) NOT NULL
window_start    TIMESTAMPTZ NOT NULL
window_end      TIMESTAMPTZ NOT NULL
message_count   INTEGER DEFAULT 0
voice_count     INTEGER DEFAULT 0
ai_call_count   INTEGER DEFAULT 0
is_throttled    BOOLEAN DEFAULT false
UNIQUE(distributor_id, whatsapp_number, window_start)
```

## Table: scheduled_messages
```sql
id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id      UUID REFERENCES distributors(id)
recipient_number    VARCHAR(20) NOT NULL
recipient_type      VARCHAR(50) NOT NULL
message_type        VARCHAR(100) NOT NULL
message_payload     JSONB NOT NULL
scheduled_for       TIMESTAMPTZ NOT NULL
status              VARCHAR(50) DEFAULT 'pending'  -- ENUM: pending, sent, failed, cancelled
retry_count         INTEGER DEFAULT 0
max_retries         INTEGER DEFAULT 3
sent_at             TIMESTAMPTZ
error_message       TEXT
reference_id        UUID
reference_type      VARCHAR(50)
idempotency_key     VARCHAR(255) UNIQUE  -- Prevent duplicate scheduled messages
created_at          TIMESTAMPTZ DEFAULT NOW()
```

## Table: catalog_import_history
```sql
id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id  UUID NOT NULL REFERENCES distributors(id)
file_name       VARCHAR(500)
storage_path    TEXT
items_total     INTEGER DEFAULT 0
items_imported  INTEGER DEFAULT 0
items_failed    INTEGER DEFAULT 0
status          VARCHAR(50)
error_log       JSONB DEFAULT '[]'
imported_by     VARCHAR(100)  -- scheduler, manual, api
created_at      TIMESTAMPTZ DEFAULT NOW()
```

## Table: bot_configuration
```sql
id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
distributor_id                  UUID NOT NULL UNIQUE REFERENCES distributors(id) ON DELETE CASCADE
welcome_message_override        TEXT
business_hours_start            TIME DEFAULT '08:00'
business_hours_end              TIME DEFAULT '20:00'
timezone                        VARCHAR(50) DEFAULT 'Asia/Karachi'
out_of_hours_message            TEXT
allow_orders_outside_hours      BOOLEAN DEFAULT true
voice_enabled                   BOOLEAN DEFAULT true
catalog_pdf_enabled             BOOLEAN DEFAULT true
discount_requests_enabled       BOOLEAN DEFAULT true
credit_orders_enabled           BOOLEAN DEFAULT false
minimum_order_value_paisas      BIGINT DEFAULT 0
max_items_per_order             INTEGER DEFAULT 50
session_timeout_minutes         INTEGER DEFAULT 60
ai_temperature                  DECIMAL(3,2) DEFAULT 0.30
custom_system_prompt_suffix     TEXT
excel_report_email              VARCHAR(255)
excel_report_schedule           VARCHAR(50) DEFAULT 'daily_evening'
                                -- realtime, daily_morning, daily_evening, weekly
preferred_payment_gateways      TEXT[]  -- Ordered list of gateways to offer customers
metadata                        JSONB DEFAULT '{}'
created_at                      TIMESTAMPTZ DEFAULT NOW()
updated_at                      TIMESTAMPTZ DEFAULT NOW()
```

---

## Indexes
```sql
CREATE INDEX idx_customers_distributor_number ON customers (distributor_id, whatsapp_number);
CREATE INDEX idx_sessions_distributor_number ON sessions (distributor_id, whatsapp_number);
CREATE INDEX idx_sessions_expiry ON sessions (expires_at) WHERE current_state != 'idle';
CREATE INDEX idx_orders_distributor_date ON orders (distributor_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders (distributor_id, status);
CREATE INDEX idx_orders_customer ON orders (customer_id);
CREATE INDEX idx_order_items_order ON order_items (order_id);
CREATE INDEX idx_catalog_active ON catalog (distributor_id) WHERE is_active = true AND is_deleted = false;
CREATE INDEX idx_catalog_name ON catalog (distributor_id, medicine_name text_pattern_ops);
CREATE INDEX idx_catalog_keywords ON catalog USING GIN (search_keywords);
CREATE INDEX idx_payments_distributor ON payments (distributor_id, status);
CREATE INDEX idx_payments_gateway_txn ON payments (gateway_transaction_id);
CREATE INDEX idx_distributors_subscription ON distributors (subscription_end)
    WHERE subscription_status IN ('active', 'expiring');
CREATE INDEX idx_analytics_distributor_time ON analytics_events (distributor_id, occurred_at DESC);
CREATE INDEX idx_scheduled_messages_due ON scheduled_messages (scheduled_for, status)
    WHERE status = 'pending';
CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id);
CREATE INDEX idx_rate_limits_lookup ON rate_limits (distributor_id, whatsapp_number, window_start);
```

---

## Migration File Order
001 → extensions | 002 → subscription_plans | 003 → distributors | 004 → customers
005 → catalog | 006 → discount_rules | 007 → delivery_zones | 008 → sessions
009 → orders | 010 → order_items | 011 → order_status_history | 012 → payments
013 → complaints | 014 → support_tickets | 015 → prospects | 016 → service_registry
017 → notifications_log | 018 → audit_log | 019 → inventory_sync_log | 020 → analytics_events
021 → rate_limits | 022 → scheduled_messages | 023 → catalog_import_history
024 → bot_configuration | 025 → enable_rls_policies | 026 → create_indexes | 027 → seed_data
