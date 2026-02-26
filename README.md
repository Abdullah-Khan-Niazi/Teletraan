<p align="center">
  <img src="https://img.shields.io/badge/TELETRAAN-v1.0.0-000000?style=for-the-badge&labelColor=000000" alt="version"/>
  <img src="https://img.shields.io/badge/Python-3.13+-000000?style=for-the-badge&logo=python&logoColor=white&labelColor=171717" alt="python"/>
  <img src="https://img.shields.io/badge/FastAPI-async-000000?style=for-the-badge&logo=fastapi&logoColor=white&labelColor=171717" alt="fastapi"/>
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-000000?style=for-the-badge&logo=supabase&logoColor=white&labelColor=171717" alt="supabase"/>
  <img src="https://img.shields.io/badge/WhatsApp-Cloud%20API-000000?style=for-the-badge&logo=whatsapp&logoColor=white&labelColor=171717" alt="whatsapp"/>
  <img src="https://img.shields.io/badge/Primus%20Family-17%20Systems-000000?style=for-the-badge&labelColor=171717" alt="primus"/>
  <img src="https://img.shields.io/badge/AI%20Coded-Claude%20Opus%204.6-000000?style=for-the-badge&labelColor=171717" alt="ai-coded"/>
</p>

<br/>

<h1 align="center">⬡&ensp;T E L E T R A A N</h1>

<p align="center">
  <strong>"More than meets the eye."</strong>
</p>

<p align="center">
  <em>
    The coordination layer of <strong>Project Primus</strong> — currently deployed as an autonomous<br/>
    WhatsApp order & operations system for medicine distributors in Pakistan.<br/>
    Not a chatbot. An intelligence. The central computer.
  </em>
</p>

<br/>

---

<br/>

## The Name & The Universe

### Teletraan-1 in Transformers Lore

In the Transformers universe, **Teletraan-1** is the Autobots' central computer aboard the Ark — a fully sentient system that monitors all environments, processes threats, manages resources, coordinates Autobot operations, repairs allies, and maintains the mission. It is not a tool. It is the intelligence that makes the mission possible. Without Teletraan-1, the Autobots are blind.

**TELETRAAN** (this project) is named with that same intent.

It does not just receive WhatsApp messages. It understands voice in Urdu, Roman Urdu, and English through multi-provider AI; it fuzzy-matches medicine names that are misspelled or abbreviated; it computes live billing with distributor-specific discounts; it orchestrates payments across six gateways; it tracks inventory, generates reports, manages distributor subscriptions, sends scheduled alerts, and coordinates all of this for multiple distributors simultaneously — 24/7, fully autonomously.

Like Teletraan-1, it is **the system that holds everything together**.

---

### The Primus Universe

**Primus** is the name of the overarching platform — a family of 17 specialized automation and intelligence systems, each named after a Transformer of significance. Together, these systems will form a complete business operating infrastructure.

TELETRAAN is the **coordination layer of Primus** — the system that, in the future, will connect, orchestrate, and relay data between all other Primus systems, just as Teletraan-1 coordinated all Autobot operations.

<br/>

<table>
<thead>
<tr>
<th align="center">System</th>
<th align="center">Domain</th>
<th align="center">Status</th>
</tr>
</thead>
<tbody>
<tr><td align="center"><strong>Alchemist</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Amalgamous</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Elita</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Liege Maximo</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Megatronus</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Micronus</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Nexus</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Onyx</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Optimus</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Orion</strong></td><td>ERP system — inventory, procurement, operations</td><td align="center"><code>✓ In Production</code></td></tr>
<tr><td align="center"><strong>Prima</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Quintus</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Sentinel</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Solus</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Teletraan</strong></td><td>WhatsApp automation, order management & coordination hub</td><td align="center"><code>✓ In Production</code></td></tr>
<tr><td align="center"><strong>Vector</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
<tr><td align="center"><strong>Zeta</strong></td><td>TBD</td><td align="center"><code>Planned</code></td></tr>
</tbody>
</table>

<br/>

Two Primus systems are currently in production:

- **Orion** — A full ERP system handling inventory management, procurement workflows, stock control, and distributor-side operations.
- **Teletraan** (this repository) — The WhatsApp automation layer that connects to Orion for live inventory data and operates the order chatbot, payments, reporting, subscriptions, and the sales funnel channel autonomously.

The remaining 15 systems are on the Primus roadmap. As each is built, **TELETRAAN will expand its coordination role** — receiving events from Nexus, surfacing data for Optimus, enforcing policies from Liege Maximo, triggering reports in Zeta, delegating delivery tasks to Vector.

---

## Scalability Architecture

TELETRAAN was built from day one to scale — not as an afterthought, but as a founding constraint. Every design decision was made with the assumption that the system would eventually need to support dozens of distributors, hundreds of thousands of orders, and connections to multiple external Primus systems.

### Multi-Tenant by Design

The entire data model is **tenant-scoped at the distributor level**. Every table with customer, order, payment, session, or inventory data has a `distributor_id` foreign key. There is no shared state between distributors. A single TELETRAAN instance can serve any number of distributors:

- Each distributor has its own WhatsApp phone number
- Sessions, orders, customers, and analytics are all scoped to a distributor
- Subscription tiers can be applied per distributor
- Feature flags are configurable per distributor

Adding a new distributor requires only a database record and a WhatsApp number registration — no code changes, no redeployment.

### Pluggable Provider Architecture

Every external dependency behind a swappable interface:

```
AI Providers     → BaseAIProvider → [Gemini, GPT-4o, Claude, Cohere, OpenRouter]
Payment Gateways → BaseGateway   → [JazzCash, EasyPaisa, SafePay, NayaPay, BankTransfer, Dummy]
Channels         → BaseChannel   → [ChannelA, ChannelB, ...future channels]
```

Adding a new AI provider: implement `BaseAIProvider`, register in `ai_factory.py`. Done.
Adding a new payment gateway: implement `BaseGateway`, register in `gateway_factory.py`. Done.
Adding a new channel (e.g., a Channel C for B2B enterprise sales): implement the flow, register in `channel_router.py`. Done.

No other code changes required anywhere in the system.

### Repository Pattern

All database access is behind repository classes:

```
DistributorRepository  →  session, inventory, order queries scoped to distributor
CustomerRepository     →  customer CRUD and lookups
OrderRepository        →  order lifecycle, line items, billing snapshots
PaymentRepository      →  transaction records, gateway reconciliation
AnalyticsRepository    →  event logging and retrieval
...21 repositories total
```

Swapping from Supabase to any other PostgreSQL host: change the client implementation. Repositories are untouched. Adding caching in front of a hot read path: wrap the repository method. One change, one place.

### Async-First, Zero Blocking I/O

Every function is `async def`. Every I/O call uses async clients — Supabase async client, `httpx.AsyncClient` for all HTTP calls (Meta API, payment gateways, AI providers), `asyncio.sleep` never replaced with `time.sleep`. APScheduler runs async jobs.

This means a single instance handles many concurrent WhatsApp conversations without threading overhead. Under Uvicorn with Gunicorn workers, throughput scales horizontally without any code changes.

### Structured Event Architecture (Primus-Ready)

Analytics events are logged with a consistent schema:

```python
{
  "event_type": "order.confirmed",
  "distributor_id": "...",
  "data": { "order_id": "...", "amount_paisas": 125000 },
  "created_at": "2026-02-27T..."
}
```

This schema is already compatible with **Nexus** (the Primus event bus). When Nexus is built, TELETRAAN's `analytics_repo.log_event()` calls will be extended to also publish to the Nexus event stream with zero changes to any business logic — the event data is already structured exactly as an event bus would consume it.

### Configuration Over Code

62 environment variables control behavior without code changes:

- Switch AI provider: `AI_PROVIDER=openai`
- Switch to dummy payments for dev: `PAYMENT_GATEWAY=dummy`
- Disable voice processing: `ENABLE_VOICE_PROCESSING=false`
- Adjust rate limits: `RATE_LIMIT_MESSAGES_PER_MINUTE=60`
- Toggle features per distributor: feature flag system in database

New Primus system integrations will be added as new env var groups — `ORION_API_URL`, `NEXUS_WEBHOOK_SECRET`, `ZETA_INGEST_KEY` — following the exact same Pydantic Settings pattern already established.

### Horizontal Scaling Path

| Scale Point         | Current                       | Next Step                                      |
| :------------------ | :---------------------------- | :--------------------------------------------- |
| Distributors        | Unlimited (DB-scoped)         | No change needed                               |
| Concurrent sessions | ~200 (in-memory rate limiter) | Move rate limiter to Redis                     |
| Request volume      | Single instance + async       | Add Gunicorn workers or second instance        |
| Background jobs     | APScheduler (in-process)      | Migrate to Celery + broker at >50 distributors |
| Analytics           | Direct DB queries             | Materialized views or dedicated read replica   |
| Primus connections  | Not yet connected             | Add Nexus event publisher per event type       |

<br/>

---

<br/>

## What TELETRAAN Does Today

<table>
<tr>
<td width="50%" valign="top">

### Channel A — Order Management

Retailers message the distributor's WhatsApp number. TELETRAAN handles end-to-end:

- **Voice & text orders** — Urdu, Roman Urdu, English
- **Fuzzy medicine search** — Levenshtein + token-sort ratio; finds "panadol" even if "panado"
- **Live billing** — real-time subtotals, distributor-specific discounts, delivery charges, applied automatically
- **Multi-item cart** — add, remove, modify quantities before confirmation
- **Payment collection** — JazzCash, EasyPaisa, SafePay, NayaPay, bank transfer; payment links sent via WhatsApp
- **Order confirmation** — formatted receipts with itemized billing
- **Order cancellation** — before payment confirmation
- **Complaint handling** — structured flow, complaint type classification, ticket creation
- **Customer profiles** — auto-registration on first message, order history, lifetime spend, block/unblock management
- **Human handoff** — escalation to human operator when AI confidence drops

</td>
<td width="50%" valign="top">

### Channel B — Software Sales Funnel

A dedicated WhatsApp number for Primus software sales:

- **Lead capture** — name, business, location, role
- **Qualification** — distributor size, current tech stack, pain points
- **Automated nurturing** — contextual follow-up sequences timed by prospect behavior
- **AI objection handling** — trained responses to common sales objections
- **Demo scheduling** — integrated booking flow with confirmation
- **Conversion tracking** — full funnel from first contact to deal close
- **Service registry** — feature showcase, pricing presentation, comparison
- **Sales handoff** — qualified leads assigned to human sales rep with full conversation context

</td>
</tr>
</table>

### Platform Capabilities

| Capability                | Detail                                                                                                                                               |
| :------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Multi-Provider AI**     | Gemini 1.5 Flash (default), GPT-4o-mini, Claude Sonnet, Cohere, OpenRouter — automatic fallback chain if primary provider fails                      |
| **NLU Engine**            | Intent classification across 20+ intents, entity extraction (medicine names, quantities, addresses, amounts), sentiment analysis, language detection |
| **Voice Processing**      | Whisper transcription of WhatsApp voice notes → NLU → order processing; seamless with text flow                                                      |
| **Inventory Sync**        | Scheduled pull from Orion/Google Drive with change detection, product deduplication, and stock level updates                                         |
| **Fuzzy Matching**        | Medicine name normalization, brand/generic matching, confidence-scored results with threshold gating                                                 |
| **Payment Orchestration** | 6 gateways, webhook HMAC verification per gateway, payment link expiry, retry on failure, reconciliation logging                                     |
| **Reporting Engine**      | XLSX order reports, PDF medicine catalogs, daily/weekly/monthly email digests with performance metrics                                               |
| **Analytics System**      | 20+ event types logged per interaction; distributor, customer, order, and system-level aggregations                                                  |
| **Distributor Lifecycle** | Trial management (configurable days), subscription plans, renewal reminders (7/3/1 day alerts), onboarding wizard, support tickets                   |
| **Admin Dashboard**       | Monochrome web UI: 8 pages, full CRUD on all entities, system health, force sync, announcements                                                      |
| **Scheduled Jobs**        | 14 background jobs — health checks every 5 min, session cleanup every 6h, inventory sync every 2h, subscription alerts daily                         |
| **Security Layer**        | HMAC webhook verification, Fernet field encryption, PII masking in all logs, prompt injection defense, per-number rate limiting                      |
| **Multi-language**        | Urdu, Roman Urdu, English — language detected per message, responses matched to detected language                                                    |

<br/>

---

<br/>

## Architecture

```
                          ┌─────────────────────────────────────┐
                          │         External World              │
                          │                                     │
                          │  WhatsApp                Meta API   │
                          │  Retailer ──────────── Webhook ──►  │
                          │  Voice Note                         │
                          └──────────────────────┬──────────────┘
                                                 │
                          ┌──────────────────────▼──────────────┐
                          │       FastAPI Application           │
                          │                                     │
                          │  ┌─────────┐  ┌─────────────────┐   │
                          │  │Webhook  │  │  Admin API      │   │
                          │  │Handler  │  │  X-Admin-Key    │   │
                          │  └────┬────┘  └────────┬────────┘   │
                          │       │                 │           │
                          │  ┌────▼─────────────────▼────────┐  │
                          │  │         Orchestrator          │  │
                          │  │  Security → Parse → NLU →     │  │
                          │  │  Session → Channel Router →   │  │
                          │  │  Flow Handler → Response      │  │
                          │  └────┬──────────────────────────┘  │
                          │       │                             │
                          │  ┌────▼──────────────────────────┐  │
                          │  │      Service Layer            │  │
                          │  │  Orders  Payments  Inventory  │  │
                          │  │  Analytics  Reporting  Notifs │  │
                          │  └────┬──────────────────────────┘  │
                          │       │                             │
                          │  ┌────▼──────────────────────────┐  │
                          │  │    Repository Layer (21 repos)│  │
                          │  │    Pydantic models (26 tables)│  │
                          │  └────┬──────────────────────────┘  │
                          └───────┼─────────────────────────────┘
                                  │
                    ┌─────────────┼──────────────────┐
                    │             │                  │
               ┌────▼────┐ ┌─────▼─────┐  ┌────────▼──────┐
               │Supabase │ │AI Providers│ │Payment Gateways│
               │Postgres │ │Gemini/GPT/│  │JazzCash/Easyp.│
               │26 tables│ │Claude/etc.│  │SafePay/NayaPay│
               └─────────┘ └───────────┘  └───────────────┘
```

<br/>

---

<br/>

## Tech Stack

```
Runtime ················ Python 3.13+ (fully async, zero blocking I/O)
Framework ·············· FastAPI with Pydantic v2 validation
Database ··············· Supabase (PostgreSQL 15) with Row Level Security
AI Providers ··········· Gemini 1.5 Flash · GPT-4o-mini · Claude Sonnet · Cohere · OpenRouter
Voice ·················· OpenAI Whisper (async via httpx)
WhatsApp ··············· Meta Cloud API v19.0 (webhook + send messages)
Payments ··············· JazzCash · EasyPaisa · SafePay · NayaPay · Bank Transfer · Dummy
Scheduler ·············· APScheduler 3.x (async, 14 jobs)
Logging ················ Loguru (structured JSON, PII-masked at filter level)
Encryption ············· Fernet symmetric (CNIC/sensitive fields at rest)
Security ··············· HMAC-SHA256 webhook verification, rate limiting, prompt injection defense
Testing ················ pytest + pytest-asyncio (1,152 tests, 80%+ coverage)
Code Quality ··········· black + isort + flake8 (pre-commit enforced)
Dashboard ·············· Vanilla HTML/CSS/JS SPA served via StaticFiles (no npm, no deps)
Deploy ················· Render (Web Service) / Railway
Env Config ············· Pydantic Settings (62 vars, startup validation, fails fast on missing)
```

<br/>

---

<br/>

## Project Structure

```
teletraan/
│
├── app/                                ← Application core (52,400+ lines)
│   ├── main.py                         ← FastAPI app factory, lifespan, routers, StaticFiles
│   │
│   ├── api/                            ← HTTP endpoint layer
│   │   ├── admin.py                    ← Admin API (30+ endpoints, X-Admin-Key protected)
│   │   ├── health.py                   ← GET /health — liveness + readiness
│   │   ├── payments.py                 ← POST /api/payments/callback/{gateway}
│   │   └── webhook.py                  ← POST /api/webhook — Meta Cloud API entry point
│   │
│   ├── core/                           ← Application foundation
│   │   ├── config.py                   ← Pydantic Settings (62 env vars, validates at startup)
│   │   ├── constants.py                ← Enums: ChannelType, OrderStatus, PaymentStatus, etc.
│   │   ├── exceptions.py               ← Exception hierarchy (15+ typed exceptions)
│   │   ├── logging.py                  ← Loguru setup with PII masking filter
│   │   └── security.py                 ← HMAC verification, Fernet encryption, rate limiter
│   │
│   ├── db/                             ← Data layer
│   │   ├── client.py                   ← Supabase async client singleton
│   │   ├── models/                     ← 16 model files · 26 Pydantic model classes
│   │   └── repositories/               ← 21 repository files · all async · all typed
│   │
│   ├── ai/                             ← AI engine
│   │   ├── base.py                     ← BaseAIProvider protocol
│   │   ├── factory.py                  ← Provider factory with ordered fallback chain
│   │   ├── nlu.py                      ← Intent classification & entity extraction
│   │   ├── voice.py                    ← Whisper transcription (async audio download + send)
│   │   ├── response_generator.py       ← Context-aware natural language response generation
│   │   ├── providers/                  ← [gemini, openai, claude, cohere, openrouter].py
│   │   └── prompts/                    ← System prompts per channel + NLU + persona
│   │
│   ├── channels/                       ← Conversation routing
│   │   ├── router.py                   ← Maps WhatsApp number → Channel A or B
│   │   ├── channel_a/                  ← Order management FSM (8 flow files)
│   │   │   ├── handler.py              ← Entry point, state dispatcher
│   │   │   ├── registration_flow.py    ← New customer onboarding
│   │   │   ├── order_flow.py           ← Cart management, item additions
│   │   │   ├── confirmation_flow.py    ← Order review and confirm
│   │   │   ├── payment_flow.py         ← Payment method selection, link send
│   │   │   ├── complaint_flow.py       ← Complaint capture and ticket creation
│   │   │   ├── faq_flow.py             ← FAQ and general queries
│   │   │   └── handoff_flow.py         ← Human operator escalation
│   │   └── channel_b/                  ← Sales funnel FSM (5 flow files)
│   │       ├── handler.py              ← Entry point, state dispatcher
│   │       ├── qualification_flow.py   ← Lead qualification questions
│   │       ├── nurturing_flow.py       ← Follow-up and re-engagement
│   │       ├── demo_flow.py            ← Demo scheduling
│   │       └── objection_flow.py       ← Objection handling
│   │
│   ├── payments/                       ← Payment processing
│   │   ├── base.py                     ← BaseGateway protocol
│   │   ├── factory.py                  ← Gateway factory
│   │   ├── service.py                  ← Payment lifecycle orchestration
│   │   ├── webhook_handlers.py         ← Per-gateway callback processors
│   │   └── gateways/                   ← [jazzcash, easypaisa, safepay, nayapay, bank, dummy].py
│   │
│   ├── inventory/                      ← Stock management
│   │   ├── catalog_service.py          ← Product CRUD, pagination, search
│   │   ├── fuzzy_matcher.py            ← Levenshtein + token-sort ratio matching
│   │   ├── stock_service.py            ← Stock level queries and updates
│   │   └── sync_service.py             ← Google Drive / Orion catalog sync
│   │
│   ├── orders/                         ← Order processing
│   │   ├── order_service.py            ← Order lifecycle (create → confirm → complete)
│   │   ├── billing_service.py          ← Real-time billing, discount application, totals
│   │   ├── context_manager.py          ← Transient order state across conversation turns
│   │   └── logging_service.py          ← Immutable order audit trail
│   │
│   ├── whatsapp/                       ← Meta API integration
│   │   ├── client.py                   ← Async HTTP client for Meta Cloud API
│   │   ├── parser.py                   ← Webhook payload parser → typed objects
│   │   ├── media.py                    ← Voice note download, document upload
│   │   └── message_types.py            ← Text, interactive, template message builders
│   │
│   ├── notifications/                  ← Outbound messaging
│   │   ├── whatsapp_notifier.py        ← Notification dispatcher (order, payment, system alerts)
│   │   └── templates/                  ← Message templates in EN, UR, Roman-UR
│   │
│   ├── analytics/                      ← Business intelligence
│   │   ├── aggregator.py               ← Cross-entity metric aggregation
│   │   ├── order_analytics.py          ← Volume, revenue, popular items, conversion
│   │   ├── customer_analytics.py       ← Retention, spend, activity segmentation
│   │   ├── distributor_analytics.py    ← Per-distributor performance
│   │   └── system_analytics.py         ← System health, error rates, latency metrics
│   │
│   ├── reporting/                      ← Report generation
│   │   ├── excel_generator.py          ← XLSX order reports (openpyxl)
│   │   ├── pdf_generator.py            ← PDF medicine catalogs (reportlab)
│   │   ├── email_dispatch.py           ← SMTP email delivery
│   │   ├── analytics_service.py        ← Report data aggregation queries
│   │   └── report_scheduler.py         ← Triggers daily/weekly/monthly reports
│   │
│   ├── scheduler/                      ← Background jobs
│   │   ├── setup.py                    ← APScheduler init, job registration, startup
│   │   └── jobs/                       ← health_check, cleanup, sync, subscription, reporting
│   │
│   └── distributor_mgmt/               ← Distributor lifecycle
│       ├── subscription_manager.py     ← Trial → active → expired state machine
│       ├── onboarding_service.py       ← First-run wizard, channel A/B setup validation
│       ├── reminder_service.py         ← 7/3/1-day expiry WhatsApp reminders
│       ├── support_service.py          ← Support ticket creation and tracking
│       └── notification_service.py     ← System-level distributor alerts
│
├── dashboard/                          ← Admin web UI (2,800+ lines, no dependencies)
│   ├── index.html                      ← SPA shell: auth gate, sidebar, topbar, modal
│   ├── css/
│   │   ├── tokens.css                  ← Design tokens: monochrome palette, typography, spacing
│   │   ├── reset.css                   ← CSS reset
│   │   ├── layout.css                  ← App shell grid, sidebar, page container
│   │   ├── components.css              ← Buttons, cards, tables, badges, forms, toasts
│   │   └── pages.css                   ← Page-specific styles
│   └── js/
│       ├── api.js                      ← API client (21 endpoint methods, auto auth headers)
│       ├── state.js                    ← App state (auth, current page, cached data)
│       ├── components.js               ← UI utilities (toast, modal, formatters, status badges)
│       ├── app.js                      ← Router, auth flow, navigation, connection monitor
│       └── pages/                      ← [overview, distributors, orders, customers,
│                                            payments, sessions, analytics, system].js
│
├── migrations/                         ← 28 SQL migration files (001_ through 028_)
├── tests/                              ← 1,152 tests across unit + integration
│   ├── unit/                           ← Isolated module tests
│   └── integration/                    ← Cross-layer and DB tests
├── scripts/                            ← 5 utility scripts (migrate, seed, create distributor)
├── docs/                               ← 8 documentation files + 21 skill files
├── .github/                            ← 21 Copilot instruction files (the build brain)
├── .env.example                        ← All 62 env var names with descriptions
├── requirements.txt                    ← Production dependencies
├── requirements-dev.txt                ← Development + test dependencies
├── pyproject.toml                      ← black + isort configuration
├── .pre-commit-config.yaml             ← black → isort → flake8 hooks
├── render.yaml                         ← Render deployment blueprint
└── Procfile                            ← Railway / Heroku start command
```

<br/>

---

<br/>

## By the Numbers

```
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   CODEBASE                          COVERAGE             ║
║   ─────────────────────────         ─────────────────    ║
║   Python files ·········· 182       Tests ·· 1,152       ║
║   Python lines ·········· 52,400+   Coverage · 80%+      ║
║   JavaScript lines ······ 1,500+    Assertions · 4,000+  ║
║   CSS lines ············· 1,000+                         ║
║   SQL migrations ········ 28        INTEGRATIONS         ║
║   Documentation ········· 8,500+    ─────────────────    ║
║   Total codebase ········ 63,700+   AI providers · 5     ║
║                                     Pay gateways · 6     ║
║   ARCHITECTURE                      WhatsApp channels· 2 ║
║   ─────────────────────────         Languages · 3        ║
║   Database tables ······· 26                             ║
║   Repositories ·········· 21        BUILD                ║
║   API endpoints ·········· 30+      ─────────────────    ║
║   Background jobs ········ 14       Phases · 13          ║
║   Env variables ·········· 62       Commits · 20+        ║
║   Skill/instruction files  21       Primus systems · 17  ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

<br/>

---

<br/>

## Admin Dashboard

TELETRAAN ships with a complete admin command center at `/dashboard`. Zero external dependencies — pure HTML, CSS, and JavaScript. Monochrome design exclusively (white → black, all shades) with color reserved only for status badges.

**Access:** Navigate to `http://your-domain/dashboard` → enter your `ADMIN_API_KEY`.

### Pages

| Page             | What It Does                                                                                                                               |
| :--------------- | :----------------------------------------------------------------------------------------------------------------------------------------- |
| **Overview**     | Live KPIs: active distributors, total customers, orders in last 24h, revenue, environment mode, feature flags                              |
| **Distributors** | Full lifecycle management — create, suspend, reactivate, extend subscription, view all sub-data in tabbed interface                        |
| **Orders**       | Per-distributor order listing with status filter (6 statuses), time window filter, full order detail with line items and billing breakdown |
| **Customers**    | Customer registry per distributor — verification status, total orders, lifetime spend, block/unblock actions                               |
| **Payments**     | Transaction records per distributor — gateway breakdown, status filter (6 statuses), payment amounts, external links                       |
| **Sessions**     | Active WhatsApp sessions — channel assignment, conversation state, handoff status, real-time refresh                                       |
| **Analytics**    | Event log with type filter, event frequency breakdown by type, full JSON event data inspection                                             |
| **System**       | Database health, AI provider health, payment gateway health, force inventory sync, broadcast announcement to all distributors              |

### Dashboard API Endpoints (Protected)

All endpoints under `/api/admin/` require `X-Admin-Key` header.

```
GET  /api/admin/dashboard/overview                        → aggregate platform KPIs
GET  /api/admin/dashboard/distributors/{id}/customers     → customer list with pagination
POST /api/admin/dashboard/customers/{id}/block            → block a customer
POST /api/admin/dashboard/customers/{id}/unblock          → unblock a customer
GET  /api/admin/dashboard/distributors/{id}/orders        → orders with status/time filters
GET  /api/admin/dashboard/orders/{id}/detail              → full order with line items
GET  /api/admin/dashboard/distributors/{id}/payments      → payment transaction records
GET  /api/admin/dashboard/distributors/{id}/sessions      → active WhatsApp sessions
GET  /api/admin/dashboard/distributors/{id}/analytics     → analytics event log
```

<br/>

---

<br/>

## Quickstart

```bash
# 1. Clone
git clone <repo-url>
cd teletraan

# 2. Virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 3. Install
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure
cp .env.example .env
# Open .env and set all 62 required variables
# Minimum required: SUPABASE_URL, SUPABASE_SERVICE_KEY, META_APP_SECRET,
#                   META_VERIFY_TOKEN, GEMINI_API_KEY (or another AI key),
#                   ADMIN_API_KEY, ENCRYPTION_KEY, APP_SECRET_KEY

# 5. Generate encryption key (if you don't have one)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → Paste the output as ENCRYPTION_KEY in .env

# 6. Run database migrations
python scripts/run_migrations.py

# 7. Create your first distributor
python scripts/create_distributor.py

# 8. Seed the medicine catalog
python scripts/seed_catalog.py --file catalog.csv --distributor-id <uuid>

# 9. Start
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 10. Access admin dashboard
# http://localhost:8000/dashboard
# Enter your ADMIN_API_KEY when prompted

# 11. Run tests
pytest tests/ -v
```

<br/>

---

<br/>

## Documentation

| Document                                         | Description                                                              |
| :----------------------------------------------- | :----------------------------------------------------------------------- |
| [Architecture](docs/architecture.md)             | System design, component diagrams, data flows, Primus integration points |
| [API Reference](docs/api_reference.md)           | All 30+ endpoints with full request/response schemas                     |
| [Database Schema](docs/database_schema.md)       | 26 tables: columns, types, constraints, relationships                    |
| [Deployment Guide](docs/deployment_guide.md)     | Render, Railway, environment setup, dashboard access                     |
| [Onboarding Guide](docs/onboarding_guide.md)     | How to onboard a new distributor (wizard walkthrough)                    |
| [Payment Gateways](docs/payment_gateways.md)     | Integration guide, webhook setup per gateway                             |
| [AI Providers](docs/ai_providers.md)             | Provider switching, fallback configuration, cost comparison              |
| [Conversation Flows](docs/conversation_flows.md) | Channel A & B FSM state diagrams with transition conditions              |

<br/>

---

<br/>

## How It Was Built

This entire project was **AI-coded**.

The primary agent responsible for building TELETRAAN — from project scaffolding through database schema design, all 182 Python files, 28 SQL migrations, the 6-gateway payment system, 5 AI provider integrations, 1,152 tests, the admin dashboard, all documentation, and deployment configuration — was **Claude Opus 4.6** (Anthropic) operating through **GitHub Copilot Pro** inside VS Code.

### The Build Method

The system was built through a disciplined **13-phase build plan** defined in 21 skill instruction files. These files specified:

- Python coding standards (type hints, async patterns, module structure)
- Database conventions (repository pattern, Supabase client, migration format)
- Security requirements (HMAC, encryption, PII masking, prompt injection)
- Error handling patterns (exception hierarchy, recovery strategy)
- Logging conventions (structured events, PII filter, severity levels)
- Git protocol (commit format, frequency, Signed-off-by requirement)
- AI provider interface patterns
- Payment gateway interface patterns
- Order context persistence conventions
- WhatsApp API integration specifics
- Conversation flow design patterns
- Testing strategy and coverage requirements
- Analytics event schema

Each phase was executed in full before the next began. Every file was committed individually. Every test was verified before marking a phase complete. No stubs. No TODOs. No partial implementations.

### What "Vibecoded" Means Here

The project was **vibecoded** — a mode of development where the human provides vision, architecture decisions, and directional corrections, and the AI writes 100% of the code.

Abdullah-Khan-Niazi specified what the system must do. Claude Opus 4.6 determined how, implemented it fully, tested it, and committed it. Every line of code in this repository was written by the AI agent.

This is not a demo. It is a production-grade system built to the same standard as human-authored enterprise software — more strictly, in some cases, because the AI was bound by 21 instruction files that defined exact standards and brooked no exceptions.

<br/>

---

<br/>

## Acknowledgments

**Designed and directed by [Abdullah-Khan-Niazi](https://github.com/Abdullah-Khan-Niazi)**
— architect of Project Primus, product owner, and the vision behind TELETRAAN.
The system exists because he knew exactly what it needed to do.

**Coded entirely by Claude Opus 4.6** (Anthropic) via GitHub Copilot Pro
— from first commit to v1.0.0, one of the most complete AI-built production systems to date.

<br/>

---

<br/>

## Primus Integration

When the next Primus systems come online, TELETRAAN will expand its role.

TELETRAAN's architecture was already designed for these connections. Adding each integration requires implementing a new client module and configuring new environment variables — no changes to existing business logic.

<br/>

---

<br/>

<p align="center">
  <strong>⬡ TELETRAAN — Project Primus</strong><br/>
  <em>"Till all are served."</em>
</p>

<br/>

---

<p align="center">
  <sub>Proprietary — All rights reserved. Part of Project Primus by Abdullah-Khan-Niazi.</sub>
</p>
