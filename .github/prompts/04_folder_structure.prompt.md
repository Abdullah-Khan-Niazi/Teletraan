# TELETRAAN — Exact Folder Structure

**MANDATORY:** Follow this structure exactly. No deviations, abbreviations, or skips.
Every package directory must have an `__init__.py`.

```
teletraan/
│
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── webhook.py            # Meta webhook verify + receive
│   │   ├── health.py             # /health — dependency status check
│   │   ├── admin.py              # Admin API — X-Admin-Key protected
│   │   └── payments.py           # All gateway callback endpoints
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic Settings — all env vars typed + validated
│   │   ├── security.py           # HMAC verification, Fernet encrypt/decrypt, token utils
│   │   ├── logging.py            # Loguru config — JSON prod, colored dev, PII masking
│   │   ├── exceptions.py         # Full custom exception hierarchy
│   │   └── constants.py          # Enums, limits, state names, timeouts
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── client.py             # Supabase client singleton + health check
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── distributor_repo.py
│   │   │   ├── customer_repo.py
│   │   │   ├── order_repo.py
│   │   │   ├── order_item_repo.py
│   │   │   ├── catalog_repo.py
│   │   │   ├── session_repo.py
│   │   │   ├── payment_repo.py
│   │   │   ├── complaint_repo.py
│   │   │   ├── support_ticket_repo.py
│   │   │   ├── prospect_repo.py
│   │   │   ├── analytics_repo.py
│   │   │   ├── audit_repo.py
│   │   │   ├── notification_repo.py
│   │   │   ├── scheduled_message_repo.py
│   │   │   └── rate_limit_repo.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── distributor.py
│   │       ├── customer.py
│   │       ├── order.py
│   │       ├── catalog.py
│   │       ├── session.py
│   │       ├── payment.py
│   │       ├── complaint.py
│   │       ├── support_ticket.py
│   │       ├── prospect.py
│   │       ├── audit.py
│   │       └── order_context.py   # Pydantic model for pending_order_draft JSONB
│   │
│   ├── whatsapp/
│   │   ├── __init__.py
│   │   ├── client.py             # Meta Cloud API async client
│   │   ├── message_types.py      # All outbound message payload builders
│   │   ├── parser.py             # Incoming webhook parser — all message types
│   │   └── media.py              # Media download (voice, images) + Supabase upload
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract AIProvider base class
│   │   ├── factory.py            # Provider factory — reads ACTIVE_AI_PROVIDER env
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── gemini_provider.py
│   │   │   ├── openai_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   ├── cohere_provider.py
│   │   │   └── openrouter_provider.py
│   │   ├── nlu.py                # Intent classification + entity extraction
│   │   ├── voice.py              # Voice pipeline — ogg download → STT → transcription
│   │   ├── response_generator.py # Multi-language response generation
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── order_bot_prompts.py
│   │       ├── sales_bot_prompts.py
│   │       └── system_prompts.py
│   │
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── router.py             # Message routing by phone_number_id
│   │   ├── channel_a/
│   │   │   ├── __init__.py
│   │   │   ├── handler.py
│   │   │   ├── onboarding.py
│   │   │   ├── order_flow.py
│   │   │   ├── catalog_flow.py
│   │   │   ├── complaint_flow.py
│   │   │   ├── profile_flow.py
│   │   │   ├── inquiry_flow.py
│   │   │   └── state_machine.py
│   │   └── channel_b/
│   │       ├── __init__.py
│   │       ├── handler.py
│   │       ├── sales_flow.py
│   │       ├── onboarding_flow.py
│   │       ├── service_registry.py
│   │       └── state_machine.py
│   │
│   ├── distributor_mgmt/
│   │   ├── __init__.py
│   │   ├── subscription_manager.py
│   │   ├── reminder_service.py
│   │   ├── notification_service.py
│   │   ├── onboarding_service.py
│   │   └── support_service.py
│   │
│   ├── payments/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract PaymentGateway base class
│   │   ├── factory.py            # Gateway factory — reads ACTIVE_PAYMENT_GATEWAY
│   │   ├── gateways/
│   │   │   ├── __init__.py
│   │   │   ├── jazzcash.py
│   │   │   ├── easypaisa.py
│   │   │   ├── safepay.py
│   │   │   ├── nayapay.py
│   │   │   ├── bank_transfer.py
│   │   │   └── dummy_gateway.py
│   │   └── webhook_handlers.py   # Unified post-payment lifecycle
│   │
│   ├── inventory/
│   │   ├── __init__.py
│   │   ├── catalog_service.py
│   │   ├── stock_service.py
│   │   ├── sync_service.py
│   │   └── fuzzy_matcher.py
│   │
│   ├── orders/
│   │   ├── __init__.py
│   │   ├── order_service.py
│   │   ├── billing_service.py
│   │   ├── context_manager.py    # Order context CRUD — read/write/validate order context
│   │   └── logging_service.py
│   │
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── excel_generator.py
│   │   ├── pdf_generator.py
│   │   ├── analytics_service.py
│   │   └── report_scheduler.py
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── scheduler.py
│   │   └── jobs/
│   │       ├── __init__.py
│   │       ├── reminder_jobs.py
│   │       ├── sync_jobs.py
│   │       ├── report_jobs.py
│   │       ├── cleanup_jobs.py
│   │       └── health_jobs.py
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── whatsapp_notifier.py
│   │   └── templates/
│   │       ├── __init__.py
│   │       ├── urdu_templates.py
│   │       ├── english_templates.py
│   │       └── roman_urdu_templates.py
│   │
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── order_analytics.py
│   │   ├── customer_analytics.py
│   │   ├── distributor_analytics.py
│   │   └── system_analytics.py
│   │
│   └── main.py
│
├── migrations/
│   ├── 001_create_extensions.sql
│   ├── 002_create_subscription_plans.sql
│   ├── 003_create_distributors.sql
│   ├── 004_create_customers.sql
│   ├── 005_create_catalog.sql
│   ├── 006_create_discount_rules.sql
│   ├── 007_create_delivery_zones.sql
│   ├── 008_create_sessions.sql
│   ├── 009_create_orders.sql
│   ├── 010_create_order_items.sql
│   ├── 011_create_order_status_history.sql
│   ├── 012_create_payments.sql
│   ├── 013_create_complaints.sql
│   ├── 014_create_support_tickets.sql
│   ├── 015_create_prospects.sql
│   ├── 016_create_service_registry.sql
│   ├── 017_create_notifications_log.sql
│   ├── 018_create_audit_log.sql
│   ├── 019_create_inventory_sync_log.sql
│   ├── 020_create_analytics_events.sql
│   ├── 021_create_rate_limits.sql
│   ├── 022_create_scheduled_messages.sql
│   ├── 023_create_catalog_import_history.sql
│   ├── 024_create_bot_configuration.sql
│   ├── 025_enable_rls_policies.sql
│   ├── 026_create_indexes.sql
│   └── 027_seed_data.sql
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_nlu.py
│   │   ├── test_billing.py
│   │   ├── test_order_context.py
│   │   ├── test_fuzzy_matcher.py
│   │   ├── test_state_machine_a.py
│   │   ├── test_state_machine_b.py
│   │   ├── test_subscription_manager.py
│   │   ├── test_payment_gateways.py
│   │   ├── test_ai_providers.py
│   │   ├── test_voice_pipeline.py
│   │   ├── test_message_parser.py
│   │   └── test_security.py
│   └── integration/
│       ├── test_webhook_flow.py
│       ├── test_order_flow.py
│       ├── test_onboarding_flow.py
│       ├── test_distributor_mgmt.py
│       └── test_payment_flow.py
│
├── scripts/
│   ├── run_migrations.py
│   ├── seed_catalog.py
│   ├── create_distributor.py
│   ├── test_webhook_locally.py
│   └── rotate_api_keys.py
│
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   ├── database_schema.md
│   ├── deployment_guide.md
│   ├── onboarding_guide.md
│   ├── payment_gateways.md
│   ├── ai_providers.md
│   └── conversation_flows.md
│
├── .env.example
├── .env                           # NEVER commit
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Procfile
├── render.yaml
└── README.md
```
