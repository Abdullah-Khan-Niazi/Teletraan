# TELETRAAN — System Architecture

## Overview

TELETRAAN is a production-grade WhatsApp automation system for medicine distributors
in Pakistan. It runs on the Meta Cloud API and handles two distinct business channels:

- **Channel A** — Retailer order management (existing customers)
- **Channel B** — Software sales funnel (new prospects via owner's number)

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11+ (async throughout) |
| Framework | FastAPI |
| Validation | Pydantic v2 |
| Database | Supabase (PostgreSQL) |
| ORM/Queries | supabase-py (async) |
| AI Providers | Gemini (default), OpenAI, Anthropic, Cohere, OpenRouter |
| Payments | JazzCash, EasyPaisa, SafePay, NayaPay, Bank Transfer, Dummy |
| WhatsApp | Meta Cloud API v19.0 |
| Scheduler | APScheduler 3.x (AsyncIOScheduler) |
| Logging | Loguru (structured, PII-masked) |
| Email | Resend SDK |
| Formatting | black + isort + flake8 (pre-commit) |
| Testing | pytest + pytest-asyncio + pytest-cov |

## Component Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Meta Cloud API                        │
│              (WhatsApp Business Platform)                │
└───────────────┬───────────────────────┬─────────────────┘
                │ webhook POST          │ send messages
                ▼                       ▲
┌───────────────────────────────────────────────────────────┐
│                    FastAPI Application                     │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌───────────┐  │
│  │ Webhook  │  │  Admin   │  │Payments │  │  Health   │  │
│  │  Route   │  │  Routes  │  │Callbacks│  │  Route    │  │
│  └────┬─────┘  └──────────┘  └────┬────┘  └───────────┘  │
│       │                           │                       │
│  ┌────▼───────────────────────────▼────────────────────┐  │
│  │              Core Orchestrator                      │  │
│  │  signature verify → parse → rate limit → route      │  │
│  └────┬────────────────────┬───────────────────────────┘  │
│       │                    │                              │
│  ┌────▼─────┐        ┌────▼─────┐                        │
│  │Channel A │        │Channel B │                        │
│  │  (Order) │        │  (Sales) │                        │
│  │   FSM    │        │   FSM    │                        │
│  └────┬─────┘        └────┬─────┘                        │
│       │                    │                              │
│  ┌────▼────────────────────▼───────────────────────────┐  │
│  │              Service Layer                          │  │
│  │  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐  │  │
│  │  │ Orders  │ │Inventory │ │Payments │ │   AI   │  │  │
│  │  │ Service │ │ Service  │ │ Service │ │Provider│  │  │
│  │  └─────────┘ └──────────┘ └─────────┘ └────────┘  │  │
│  └────────────────────┬────────────────────────────────┘  │
│                       │                                   │
│  ┌────────────────────▼────────────────────────────────┐  │
│  │             Repository Layer                        │  │
│  │  21 async repositories with Pydantic validation     │  │
│  └────────────────────┬────────────────────────────────┘  │
│                       │                                   │
│  ┌────────────────────▼────────────────────────────────┐  │
│  │           Supabase (PostgreSQL)                     │  │
│  │  26 tables, UUID PKs, RLS, multi-tenant             │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           Background Scheduler                      │  │
│  │  14 jobs: sync, cleanup, reports, health, reminders │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

## Data Flow — Inbound Message

1. Meta sends POST to `/api/webhook` with HMAC-SHA256 signature
2. Webhook handler verifies signature using `META_APP_SECRET`
3. Raw payload parsed by `WhatsAppParser` → `ParsedMessage`
4. Rate limiter checks per-number message rate (30/min max)
5. Channel router resolves by phone number ID:
   - Owner's number → Channel B (sales)
   - Distributor's number → Channel A (orders)
6. Session loaded/created from `sessions` table
7. FSM determines current state and routes to handler
8. Handler processes message (may involve AI, inventory, payments)
9. Response sent back via `WhatsAppClient.send_*()` methods
10. Session state updated in DB

## Data Flow — Payment

1. Order confirmed → `PaymentService.initiate_payment()` called
2. Gateway factory selects active gateway (JazzCash, EasyPaisa, etc.)
3. Gateway creates payment link/request → returned to user via WhatsApp
4. Customer pays → gateway sends callback to `/api/payments/{gateway}/callback`
5. Webhook handler verifies signature, updates payment record
6. Order status updated to `confirmed` if payment successful
7. Distributor notified via WhatsApp

## Multi-Tenancy

Every tenant table has a `distributor_id` FK column. All repository queries
filter by `distributor_id` to enforce tenant isolation. No cross-tenant data
access is possible at the repository layer.

## Session Management

Sessions track per-conversation state for each WhatsApp number. They include:
- Current FSM state and state data
- Pending order draft (items being built)
- Conversation history (for AI context)
- Language preference
- Expiry timestamp (auto-cleaned by scheduler)

## Error Handling

All exceptions derive from `TeletraanError` base class:
- `DatabaseError` — DB operations
- `NotFoundError` — entity lookups
- `ValidationError` — input validation
- `WhatsAppError` — Meta API issues
- `PaymentError` — gateway failures
- `AIProviderError` — AI service failures

Every error is caught, logged with structured context, and results in a
user-friendly WhatsApp response.

## Security

- Webhook signature verification (HMAC-SHA256) on every POST
- Fernet encryption for CNIC and sensitive fields
- PII masking in all log output (phone: last 4 digits only)
- Rate limiting per WhatsApp number
- Admin endpoints protected by `X-Admin-Key` header
- Prompt injection sanitisation on all user input before AI
- Startup validation: app refuses to start if secrets missing
