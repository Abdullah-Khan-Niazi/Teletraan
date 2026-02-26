<p align="center">
  <img src="https://img.shields.io/badge/TELETRAAN-v1.0.0-000000?style=for-the-badge&labelColor=000000" alt="version"/>
  <img src="https://img.shields.io/badge/Python-3.11+-000000?style=for-the-badge&logo=python&logoColor=white&labelColor=171717" alt="python"/>
  <img src="https://img.shields.io/badge/FastAPI-async-000000?style=for-the-badge&logo=fastapi&logoColor=white&labelColor=171717" alt="fastapi"/>
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-000000?style=for-the-badge&logo=supabase&logoColor=white&labelColor=171717" alt="supabase"/>
  <img src="https://img.shields.io/badge/WhatsApp-Cloud%20API-000000?style=for-the-badge&logo=whatsapp&logoColor=white&labelColor=171717" alt="whatsapp"/>
  <img src="https://img.shields.io/badge/AI%20Coded-Claude%20Opus%204.6-000000?style=for-the-badge&labelColor=171717" alt="ai-coded"/>
</p>

<br/>

<h1 align="center">
  <br/>
  ⬡&ensp;T E L E T R A A N
  <br/>
</h1>

<p align="center">
  <strong>
    "More than meets the eye."
  </strong>
</p>

<p align="center">
  <em>
    Autonomous WhatsApp order & operations system for medicine distributors in Pakistan.
    <br/>
    Not a chatbot. An intelligence.
  </em>
</p>

<br/>

---

<br/>

## The Name

In the Transformers universe, **Teletraan** is the Autobots' central computer — the sentient system that monitors, coordinates, and orchestrates everything: scanning the environment, analyzing threats, managing resources, and directing Autobot operations across the entire planet. It is the brain behind the mission.

**TELETRAAN** (this project) carries the same purpose.

It is not just a WhatsApp chatbot. It is the **central nervous system** of a medicine distribution operation: receiving orders from retailers across Pakistan via WhatsApp, understanding voice and text in Urdu, Roman Urdu, and English through AI-powered NLU, matching medicine names with fuzzy search, calculating live billing with discounts, managing payments across six gateways, tracking inventory, generating reports, handling subscriptions, and coordinating everything autonomously — 24/7, without human intervention.

Like the Autobot Teletraan-1, this system handles, maintains, and orchestrates the creations of its operator. One system. Full command.

<br/>

---

<br/>

## What It Does

<table>
<tr>
<td width="50%" valign="top">

### Channel A — Order Management
Retailers message the distributor's WhatsApp number. TELETRAAN handles everything:
- **Voice & text orders** — Urdu, Roman Urdu, English
- **Fuzzy medicine search** — finds "panadol" even if spelled "panado"
- **Live billing** — real-time subtotals, discounts, delivery charges
- **Payment collection** — JazzCash, EasyPaisa, SafePay, NayaPay, bank transfer
- **Order confirmation** — formatted WhatsApp receipts
- **Complaint handling** — structured complaint flow with ticket tracking
- **Customer profiles** — automatic registration, order history, spend tracking

</td>
<td width="50%" valign="top">

### Channel B — Sales Funnel
A separate WhatsApp number for software sales outreach:
- **Prospect management** — capture and qualify leads
- **Automated nurturing** — drip sequences with contextual follow-ups
- **Demo scheduling** — integrated booking flow
- **Objection handling** — AI-powered responses to common concerns
- **Conversion tracking** — full funnel analytics
- **Service registry** — feature showcase and pricing

</td>
</tr>
</table>

### Beyond Channels

| Capability | Description |
|:---|:---|
| **Multi-Provider AI** | Gemini 1.5 Flash (default), GPT-4o-mini, Claude, Cohere, OpenRouter — automatic fallback chain |
| **Natural Language Understanding** | Intent classification, entity extraction, sentiment analysis, language detection |
| **Voice Processing** | Whisper-powered transcription → NLU → response |
| **Inventory Sync** | Scheduled catalog import from Google Drive/Supabase with change detection |
| **Fuzzy Matching** | Levenshtein + token-sort ratio medicine matching with confidence scoring |
| **Payment Orchestration** | Six gateway integrations with webhook verification, retry logic, expiry handling |
| **Reporting** | Excel order logs, PDF catalogs, daily/weekly email digests |
| **Analytics** | Order, customer, distributor, system-level metrics and aggregations |
| **Distributor Management** | Subscription lifecycle, trial management, onboarding flows, support tickets |
| **Admin Dashboard** | Full-featured monochrome web UI for system management |
| **Scheduled Jobs** | Subscription reminders, session cleanup, health checks, report generation |
| **Security** | Webhook HMAC verification, field encryption, PII masking, rate limiting, prompt injection defense |

<br/>

---

<br/>

## Tech Stack

```
Runtime ················ Python 3.13+ (fully async, zero blocking I/O)
Framework ·············· FastAPI with Pydantic v2 validation
Database ··············· Supabase (PostgreSQL) with RLS policies
AI Providers ··········· Gemini 1.5 Flash · GPT-4o-mini · Claude · Cohere · OpenRouter
Voice ·················· OpenAI Whisper
WhatsApp ··············· Meta Cloud API v19.0
Payments ··············· JazzCash · EasyPaisa · SafePay · NayaPay · Bank Transfer · Dummy (dev)
Scheduler ·············· APScheduler (async)
Logging ················ Loguru (structured, PII-masked)
Encryption ············· Fernet symmetric encryption (CNIC/sensitive fields)
Testing ················ pytest + pytest-asyncio (1152 tests, 80%+ coverage)
Formatting ············· black + isort + flake8 (pre-commit enforced)
Dashboard ·············· Vanilla HTML/CSS/JS (monochrome design, no dependencies)
Deploy ················· Render / Railway
```

<br/>

---

<br/>

## Project Structure

```
teletraan/
│
├── app/                          ← Application core (52,400+ lines)
│   ├── main.py                   ← FastAPI app factory + lifespan
│   ├── api/                      ← HTTP endpoints
│   │   ├── admin.py              ← Admin API (30+ endpoints, X-Admin-Key protected)
│   │   ├── health.py             ← Health check endpoint
│   │   ├── payments.py           ← Payment gateway callbacks
│   │   └── webhook.py            ← Meta webhook handler
│   ├── core/                     ← Foundation layer
│   │   ├── config.py             ← Pydantic Settings (62 env vars, startup validation)
│   │   ├── constants.py          ← Enums & system constants
│   │   ├── exceptions.py         ← Exception hierarchy
│   │   ├── logging.py            ← Structured logging setup
│   │   └── security.py           ← HMAC verification, encryption, PII masking, rate limiting
│   ├── db/                       ← Database layer
│   │   ├── client.py             ← Supabase async client
│   │   ├── models/               ← 16 Pydantic model files (26 tables)
│   │   └── repositories/         ← 21 repository files (data access)
│   ├── ai/                       ← AI engine
│   │   ├── base.py               ← Provider interface
│   │   ├── factory.py            ← Provider factory with fallback
│   │   ├── nlu.py                ← Intent/entity extraction
│   │   ├── voice.py              ← Whisper transcription
│   │   ├── response_generator.py ← Context-aware response generation
│   │   ├── providers/            ← 5 AI provider implementations
│   │   └── prompts/              ← System prompts (channel A, B, NLU, admin)
│   ├── channels/                 ← Message routing
│   │   ├── router.py             ← Channel A/B dispatcher
│   │   ├── channel_a/            ← Order management (8 flow files)
│   │   └── channel_b/            ← Sales funnel (5 flow files)
│   ├── payments/                 ← Payment processing
│   │   ├── base.py               ← Gateway interface
│   │   ├── factory.py            ← Gateway factory
│   │   ├── service.py            ← Payment orchestration
│   │   ├── webhook_handlers.py   ← Callback processing
│   │   └── gateways/             ← 6 gateway implementations
│   ├── inventory/                ← Stock management
│   │   ├── catalog_service.py    ← Catalog CRUD
│   │   ├── fuzzy_matcher.py      ← Medicine name matching
│   │   ├── stock_service.py      ← Stock tracking
│   │   └── sync_service.py       ← Google Drive sync
│   ├── orders/                   ← Order processing
│   │   ├── order_service.py      ← Order lifecycle
│   │   ├── billing_service.py    ← Live billing calculations
│   │   ├── context_manager.py    ← Order state persistence
│   │   └── logging_service.py    ← Order audit trail
│   ├── whatsapp/                 ← WhatsApp integration
│   │   ├── client.py             ← Meta API client
│   │   ├── parser.py             ← Webhook payload parser
│   │   ├── media.py              ← Media upload/download
│   │   └── message_types.py      ← Message type definitions
│   ├── notifications/            ← Outbound messaging
│   │   ├── whatsapp_notifier.py  ← Notification dispatcher
│   │   └── templates/            ← English, Urdu, Roman Urdu templates
│   ├── analytics/                ← Business intelligence
│   │   ├── aggregator.py         ← Event aggregation
│   │   ├── order_analytics.py    ← Order metrics
│   │   ├── customer_analytics.py ← Customer insights
│   │   ├── distributor_analytics.py ← Distributor metrics
│   │   └── system_analytics.py   ← System health metrics
│   ├── reporting/                ← Report generation
│   │   ├── excel_generator.py    ← XLSX order reports
│   │   ├── pdf_generator.py      ← PDF catalogs
│   │   ├── email_dispatch.py     ← Email delivery
│   │   ├── analytics_service.py  ← Report data queries
│   │   └── report_scheduler.py   ← Scheduled report triggers
│   ├── scheduler/                ← Background jobs
│   │   ├── setup.py              ← APScheduler configuration
│   │   └── jobs/                 ← 5 job category files
│   └── distributor_mgmt/        ← Distributor lifecycle
│       ├── subscription_manager.py ← Trial/subscription management
│       ├── onboarding_service.py ← First-run setup
│       ├── reminder_service.py   ← Expiry notifications
│       ├── support_service.py    ← Support ticket handling
│       └── notification_service.py ← Distributor alerts
│
├── dashboard/                    ← Admin web UI (2,800+ lines)
│   ├── index.html                ← SPA entry point
│   ├── css/                      ← Design tokens, layout, components
│   └── js/                       ← API client, state, 8 page modules
│
├── migrations/                   ← 28 SQL migration files
├── tests/                        ← 1,152 tests (80%+ coverage)
│   ├── unit/                     ← Unit tests
│   └── integration/              ← Integration tests
├── scripts/                      ← 5 utility scripts
├── docs/                         ← 8 documentation files + skills
├── .github/                      ← Copilot instructions (21 skill files)
└── requirements.txt              ← Production dependencies
```

<br/>

---

<br/>

## By the Numbers

```
╔═══════════════════════════════════════════╗
║                                           ║
║    Python files ·········· 182            ║
║    Python lines ·········· 52,400+        ║
║    JavaScript lines ······ 1,500+         ║
║    CSS lines ············· 1,000+         ║
║    SQL migrations ········ 28 files       ║
║    Documentation ········· 8,500+ lines   ║
║    Total codebase ········ 63,700+ lines  ║
║                                           ║
║    Database tables ······· 26             ║
║    API endpoints ········· 30+            ║
║    AI providers ·········· 5              ║
║    Payment gateways ······ 6              ║
║    Test cases ············ 1,152          ║
║    Code coverage ········· 80%+           ║
║    Env variables ········· 62             ║
║    Skill/instruction files 21             ║
║                                           ║
╚═══════════════════════════════════════════╝
```

<br/>

---

<br/>

## Admin Dashboard

TELETRAAN ships with a built-in admin command center at `/dashboard`. Monochrome design — white, black, and their shades only, with color reserved exclusively for status badges.

**Pages:**
- **Overview** — Real-time KPIs: distributors, customers, orders (24h), revenue, feature flags
- **Distributors** — Full lifecycle management: create, suspend, reactivate, extend subscription, view detail with tabbed sub-views (customers, orders, payments, sessions)
- **Orders** — Per-distributor order listing with status/time filters, full order detail with line items
- **Customers** — Customer registry with block/unblock, spend tracking, verification status
- **Payments** — Transaction records by gateway, status, and amount with payment link access
- **Sessions** — Active WhatsApp sessions with channel, state, and handoff monitoring
- **Analytics** — Event log with type breakdown, data inspection, and filtering
- **System** — Health checks (database, AI, payment gateway), force inventory sync, broadcast announcements

<br/>

---

<br/>

## Quickstart

```bash
# Clone
git clone <repo-url> && cd teletraan

# Virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# Install
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure
cp .env.example .env
# Fill .env with real values (62 variables)

# Migrate
python scripts/run_migrations.py

# Seed catalog (optional)
python scripts/seed_catalog.py --file catalog.csv

# Start
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Dashboard
# Open http://localhost:8000/dashboard
```

<br/>

---

<br/>

## Documentation

| Document | Description |
|:---|:---|
| [Architecture](docs/architecture.md) | System design, component diagrams, data flows |
| [API Reference](docs/api_reference.md) | All 30+ endpoints with request/response schemas |
| [Database Schema](docs/database_schema.md) | 26 tables with column descriptions |
| [Deployment Guide](docs/deployment_guide.md) | Render & Railway deployment steps |
| [Onboarding Guide](docs/onboarding_guide.md) | How to onboard a new distributor |
| [Payment Gateways](docs/payment_gateways.md) | Integration guide for all 6 gateways |
| [AI Providers](docs/ai_providers.md) | Provider switching, configuration, costs |
| [Conversation Flows](docs/conversation_flows.md) | Channel A & B FSM state diagrams |

<br/>

---

<br/>

## How It Was Built

This entire project was **AI-coded**.

The primary agent responsible for building TELETRAAN — from project scaffolding through database schema, all 182 Python files, 28 SQL migrations, 1,152 tests, the admin dashboard, documentation, and deployment configuration — was **Claude Opus 4.6** operating through **GitHub Copilot Pro** in VS Code.

The system was built through a structured **21-phase build plan** defined in skill files and prompt instructions, executed sequentially with git discipline: every completed file committed, every test verified, every phase validated before proceeding to the next.

No code was copy-pasted from external projects. No boilerplate generators were used. Every module was written from spec to implementation by the AI agent, following the project's own instruction files that defined coding standards, database conventions, error handling patterns, logging rules, security requirements, and commit protocols.

The build process was **vibecoded** — directed by human intent and architectural decisions, executed entirely by AI. The human provided the vision, the requirements, and the course corrections. The machine wrote every line.

<br/>

---

<br/>

## Acknowledgments

**Built by [Abdullah-Khan-Niazi](https://github.com/Abdullah-Khan-Niazi)**
— architect, product owner, and the one who pointed the AI in the right direction.

**Coded by Claude Opus 4.6** (Anthropic) via GitHub Copilot Pro
— sole developer, from first commit to v1.0.0.

<br/>

---

<br/>

<p align="center">
  <strong>⬡ TELETRAAN</strong>
  <br/>
  <em>"Till all are served."</em>
</p>

<br/>

---

<p align="center">
  <sub>Proprietary — All rights reserved.</sub>
</p>
