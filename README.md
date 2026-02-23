# TELETRAAN

**;)**

WhatsApp Intelligent Order and Operations Automation System for medicine
distributors in Pakistan. Built on Meta Cloud API, Python (FastAPI), and
Supabase.

---

## Features

- **Channel A — Order Management:** Retailers place medicine orders via
  WhatsApp with voice/text, fuzzy search, live billing, and discount
  negotiation.
- **Channel B — Sales Funnel:** Software sales outreach for prospective
  distributors through a dedicated WhatsApp number.
- **Multi-Provider AI:** Pluggable AI engine (Gemini, OpenAI, Anthropic,
  Cohere, OpenRouter) with automatic fallback.
- **Payment Gateways:** JazzCash, EasyPaisa, SafePay, NayaPay, bank
  transfer, and a dev-only dummy gateway.
- **Inventory Sync:** Scheduled catalog import from Google Drive/Supabase
  Storage with stock tracking.
- **Reporting:** Excel order logs and PDF catalogs delivered via WhatsApp
  and email.
- **Analytics:** Order, customer, distributor, and system-level metrics.
- **Distributor Management:** Subscription lifecycle, onboarding,
  reminders, and support tickets.

---

## Tech Stack

| Layer        | Technology                                                |
| ------------ | --------------------------------------------------------- |
| Runtime      | Python 3.11+                                              |
| Framework    | FastAPI (fully async)                                     |
| Database     | Supabase (PostgreSQL)                                     |
| AI Providers | Gemini 1.5 Flash, GPT-4o-mini, Claude, Cohere, OpenRouter |
| Payments     | JazzCash, EasyPaisa, SafePay, NayaPay, Bank Transfer      |
| WhatsApp     | Meta Cloud API v19.0                                      |
| Scheduler    | APScheduler                                               |
| Logging      | Loguru (structured, PII-masked)                           |
| Deploy       | Render / Railway                                          |

---

## Quickstart

```bash
# 1. Clone
git clone <repo-url> && cd teletraan

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Fill in .env with real values

# 5. Run migrations
python scripts/run_migrations.py

# 6. Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Project Structure

```
app/
├── api/          # FastAPI routes (webhook, health, admin, payments)
├── core/         # Config, logging, exceptions, constants, security
├── db/           # Supabase client, models, repositories
├── whatsapp/     # Meta Cloud API client, parser, media
├── ai/           # AI provider abstraction, NLU, voice, prompts
├── channels/     # Channel A (orders) and Channel B (sales)
├── payments/     # Payment gateway abstraction
├── inventory/    # Catalog, stock, sync, fuzzy matcher
├── orders/       # Order service, billing, context manager
├── reporting/    # Excel/PDF generators, analytics service
├── scheduler/    # APScheduler setup and job definitions
├── notifications/ # WhatsApp notifier and message templates
├── analytics/    # Order, customer, distributor, system analytics
├── distributor_mgmt/ # Subscription, reminders, onboarding, support
└── main.py       # FastAPI app factory
migrations/       # 27 SQL migration files
tests/            # Unit and integration tests
scripts/          # Utility scripts
docs/             # Architecture, API reference, guides
```

---

## Environment Variables

See [`.env.example`](.env.example) for the complete list with descriptions.

---

## API Endpoints

| Method     | Path                               | Description                       |
| ---------- | ---------------------------------- | --------------------------------- |
| `GET`      | `/health`                          | System health check               |
| `GET`      | `/api/webhook`                     | Meta webhook verification         |
| `POST`     | `/api/webhook`                     | Meta webhook incoming messages    |
| `POST`     | `/api/payments/{gateway}/callback` | Payment gateway callbacks         |
| `GET/POST` | `/api/admin/*`                     | Admin API (X-Admin-Key protected) |

---

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — System architecture
- [`docs/api_reference.md`](docs/api_reference.md) — API reference
- [`docs/database_schema.md`](docs/database_schema.md) — Database schema
- [`docs/deployment_guide.md`](docs/deployment_guide.md) — Deployment guide
- [`docs/onboarding_guide.md`](docs/onboarding_guide.md) — Distributor onboarding
- [`docs/payment_gateways.md`](docs/payment_gateways.md) — Payment integration
- [`docs/ai_providers.md`](docs/ai_providers.md) — AI provider guide
- [`docs/conversation_flows.md`](docs/conversation_flows.md) — Conversation design

---

## License

Proprietary — All rights reserved.

**Owner:** Abdullah-Khan-Niazi
