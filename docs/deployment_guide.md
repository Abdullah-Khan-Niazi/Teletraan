# TELETRAAN — Deployment Guide

Complete guide for deploying TELETRAAN and accessing the admin dashboard.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Admin API Key](#admin-api-key)
- [Database Setup](#database-setup)
- [Local Development](#local-development)
- [Admin Dashboard](#admin-dashboard)
- [Render Deployment](#render-deployment)
- [Railway Deployment](#railway-deployment)
- [WhatsApp Webhook Setup](#whatsapp-webhook-setup)
- [Post-Deploy Checklist](#post-deploy-checklist)
- [Monitoring](#monitoring)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Python 3.13+
- Supabase project (PostgreSQL)
- Meta WhatsApp Business API credentials (phone number + app)
- At least one AI provider API key (Gemini 1.5 Flash recommended — free tier available)
- Domain with HTTPS for the Meta webhook endpoint (required by Meta)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

All 62 variables are documented in `.env.example`. The minimum required set to start:

```env
# ── Application Security ──────────────────────────────────────────────────
APP_SECRET_KEY=<64-char-random-string>
ENCRYPTION_KEY=<fernet-key>                 # see generation below
ADMIN_API_KEY=<your-strong-admin-key>       # used for dashboard + admin API

# ── Meta WhatsApp ─────────────────────────────────────────────────────────
META_APP_ID=<meta-app-id>
META_APP_SECRET=<meta-app-secret>
META_VERIFY_TOKEN=<custom-verify-token>     # you define this, must match Meta config
OWNER_PHONE_NUMBER_ID=<phone-number-id>
OWNER_WHATSAPP_NUMBER=+923xxxxxxxxx

# ── Supabase ──────────────────────────────────────────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJhbG...

# ── AI Provider (at least one required) ──────────────────────────────────
GEMINI_API_KEY=AIza...
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### Generate Required Keys

**Fernet encryption key:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Random secret key:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Admin API key (use any strong string, 16+ chars):**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Admin API Key

The `ADMIN_API_KEY` is the password that protects the admin dashboard and all admin API endpoints. It is **not auto-generated** — you define it.

### Setting Your Admin API Key

1. Generate a strong key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Example output: `4K9mXqLpRsNvBw7dAeJhCfYtUzGi8oQ2WkDl6sT1Xy0`

2. Add to `.env`:
   ```env
   ADMIN_API_KEY=4K9mXqLpRsNvBw7dAeJhCfYtUzGi8oQ2WkDl6sT1Xy0
   ```

3. Use this key:
   - In the dashboard login prompt (browser)
   - As the `X-Admin-Key` header in direct API calls

### Security Rules

- Minimum 16 characters (enforced at startup)
- Never commit this value — only goes in `.env`
- Change it if compromised — all dashboard sessions are stateless so no session invalidation needed
- For production, use a key with 32+ random characters

---

## Database Setup

### 1. Run Migrations

28 SQL migrations live in `migrations/` (numbered `001_` through `028_`). Run them in order:

```bash
# Automated (recommended)
python scripts/run_migrations.py

# Manual fallback — paste each file into Supabase SQL Editor in numerical order
```

### 2. Create Your First Distributor

```bash
python scripts/create_distributor.py
# Follow the prompts: business name, WhatsApp number, subscription plan
```

### 3. Seed Medicine Catalog

```bash
# From a CSV file
python scripts/seed_catalog.py --file catalog.csv --distributor-id <uuid>

# CSV format: name,generic_name,manufacturer,price_paisas,stock_quantity,unit
```

---

## Local Development

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Set up environment
cp .env.example .env
# Fill in .env

# 4. Run migrations
python scripts/run_migrations.py

# 5. Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Application is running at:
#   API:       http://localhost:8000
#   Dashboard: http://localhost:8000/dashboard
#   Health:    http://localhost:8000/health
#   API Docs:  http://localhost:8000/docs

# 6. Run tests
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

For receiving Meta webhooks locally, use ngrok:

```bash
ngrok http 8000
# Set the ngrok HTTPS URL as your webhook callback in Meta Developer Dashboard
```

---

## Admin Dashboard

The admin dashboard is a built-in web UI served directly by TELETRAAN. No separate deployment required.

### Accessing the Dashboard

| Environment | URL |
|:---|:---|
| Local development | `http://localhost:8000/dashboard` |
| Render deployment | `https://your-app.onrender.com/dashboard` |
| Railway deployment | `https://your-app.railway.app/dashboard` |
| Custom domain | `https://your-domain.com/dashboard` |

### Login

The dashboard presents a login gate on first visit. Enter your `ADMIN_API_KEY` — the same value set in your `.env` file.

The key is stored in `localStorage` for the browser session. Click **Logout** in the sidebar to clear it.

### Dashboard Pages

| Page | Path (sidebar) | Description |
|:---|:---|:---|
| Overview | `#overview` | Platform KPIs, active distributors, revenue, feature flags |
| Distributors | `#distributors` | Full distributor management: create, suspend, extend subscription |
| Orders | `#orders` | Order history with status and time-window filters |
| Customers | `#customers` | Customer registry, spend tracking, block/unblock |
| Payments | `#payments` | Transaction records by gateway and status |
| Sessions | `#sessions` | Active WhatsApp conversation sessions |
| Analytics | `#analytics` | Event log with type filtering and JSON inspection |
| System | `#system` | Health checks, force inventory sync, broadcast announcements |

### Distributor Management (Dashboard)

From the **Distributors** page:

1. **Create a distributor** — Click **New Distributor**, fill in business name, WhatsApp numbers (Channel A and/or B), and subscription plan.
2. **View detail** — Click any distributor row to open the detail view with four tabs: Customers, Orders, Payments, Sessions.
3. **Suspend** — Immediately disables the distributor's WhatsApp channels. All incoming messages receive a suspension notice.
4. **Reactivate** — Restores full functionality.
5. **Extend subscription** — Adds days to the subscription expiry with an optional reason note.

### System Operations (Dashboard)

From the **System** page:

- **Health cards** show real-time status of: database connection, AI provider (test generation call), payment gateway connectivity.
- **Force Sync** triggers an immediate inventory catalog sync (normally runs every 2 hours).
- **Broadcast Announcement** sends a WhatsApp message to all active distributor owners simultaneously. Supports normal, important, and urgent priority levels which appear in the notification formatting.

### Dashboard API — Direct Usage

All dashboard data endpoints are accessible directly for scripting or external tools:

```bash
# Set your admin key
ADMIN_KEY="your-admin-api-key"
BASE="https://your-domain.com"

# Platform overview
curl -H "X-Admin-Key: $ADMIN_KEY" "$BASE/api/admin/dashboard/overview"

# List distributors
curl -H "X-Admin-Key: $ADMIN_KEY" "$BASE/api/admin/distributors"

# Orders for a distributor (last 24 hours, pending only)
curl -H "X-Admin-Key: $ADMIN_KEY" \
  "$BASE/api/admin/dashboard/distributors/<id>/orders?status=pending&hours=24"

# Force inventory sync
curl -X POST -H "X-Admin-Key: $ADMIN_KEY" "$BASE/api/admin/inventory/sync"

# Send an announcement
curl -X POST -H "X-Admin-Key: $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"message": "System maintenance at midnight.", "priority": "important"}' \
     "$BASE/api/admin/announcement"
```

### Dashboard Security Notes

- The dashboard is served over the same HTTPS connection as the API — no additional TLS configuration needed.
- All admin endpoints enforce `X-Admin-Key` validation server-side. The browser UI only provides a convenient interface.
- There is no session expiry on the stored key — it persists in `localStorage` until the user logs out or clears browser storage. For shared/public terminals, always log out after use.
- Rate limiting applies to admin endpoints the same as all other endpoints.

---

## Render Deployment

### Using render.yaml (Recommended)

The repository includes a `render.yaml` Blueprint:

1. Push the repository to GitHub.
2. Go to [Render Dashboard](https://dashboard.render.com) → New → Blueprint.
3. Connect the GitHub repository.
4. Render auto-detects `render.yaml` and creates the web service.
5. Set all environment variables in the Render dashboard → Environment tab.
6. Deploy.

### Manual Render Setup

1. Create a new **Web Service** on Render.
2. Connect your GitHub repository.
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Python Version:** 3.13
   - **Plan:** Starter (or higher for production)
4. Add all environment variables from your `.env`.
5. Deploy.

### Render Environment Variables

In Render → Your Service → Environment, add each variable from your `.env`. The critical ones for production:

```
APP_SECRET_KEY        → your generated secret
ENCRYPTION_KEY        → fernet key
ADMIN_API_KEY         → your admin key
META_APP_SECRET       → from Meta Developer dashboard
META_VERIFY_TOKEN     → must exactly match what you set in Meta webhook config
SUPABASE_URL          → from Supabase project settings
SUPABASE_SERVICE_KEY  → from Supabase project settings → API → service_role key
GEMINI_API_KEY        → from Google AI Studio
```

### Post-Deploy on Render

```bash
# Health check
curl https://your-app.onrender.com/health

# Admin dashboard
# Open https://your-app.onrender.com/dashboard in browser

# Verify admin API
curl -H "X-Admin-Key: YOUR_ADMIN_KEY" https://your-app.onrender.com/api/admin/status
```

### Render Notes

- Render free tier **spins down after 15 minutes of inactivity**. Use Starter plan for production (keeps instance warm).
- First request after spin-down takes 30-60 seconds. This is fine for testing, not for production.
- Logs are available in Render dashboard → Logs tab. Filter for `ERROR` level to catch issues quickly.

---

## Railway Deployment

1. Install Railway CLI:
   ```bash
   npm install -g @railway/cli
   ```

2. Login:
   ```bash
   railway login
   ```

3. Initialize project:
   ```bash
   railway init
   ```

4. Set environment variables:
   ```bash
   railway variables set APP_SECRET_KEY=xxx
   railway variables set ENCRYPTION_KEY=xxx
   railway variables set ADMIN_API_KEY=xxx
   railway variables set META_APP_SECRET=xxx
   railway variables set META_VERIFY_TOKEN=xxx
   railway variables set SUPABASE_URL=xxx
   railway variables set SUPABASE_SERVICE_KEY=xxx
   railway variables set GEMINI_API_KEY=xxx
   # repeat for all required vars
   ```

5. Deploy:
   ```bash
   railway up
   ```

The `Procfile` defines the start command:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## WhatsApp Webhook Setup

### 1. Configure Meta App

1. Go to [Meta Developer Dashboard](https://developers.facebook.com/).
2. Select your app → WhatsApp → Configuration.
3. Set **Callback URL:** `https://your-domain.com/api/webhook`
4. Set **Verify Token:** exactly the same value as `META_VERIFY_TOKEN` in your `.env`.
5. Click **Verify and Save**.
6. Subscribe to webhook fields: `messages`, `messaging_postbacks`.

### 2. Verify Webhook

Meta sends a GET to verify. TELETRAAN handles this automatically:

```
GET /api/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=XXXX
```

If verification fails, check that `META_VERIFY_TOKEN` in `.env` exactly matches what you entered in the Meta dashboard.

### 3. Channel A vs Channel B

- **Channel A** (order management): Point to one WhatsApp phone number.
- **Channel B** (sales funnel): Point to a second WhatsApp phone number.
- TELETRAAN's router dispatches based on the receiving phone number ID.

Both phone numbers use the same webhook URL — the router distinguishes them internally.

---

## Post-Deploy Checklist

```
□ Health endpoint returns {"status": "healthy"}
□ Dashboard loads at /dashboard
□ Admin login works with your ADMIN_API_KEY
□ Meta webhook verified (GET request passes)
□ Send a test WhatsApp message to Channel A number → verify TELETRAAN responds
□ Create a test distributor via dashboard
□ Overview page shows correct distributor count
□ System page shows all health checks green
□ Force sync completes without error
□ Check logs for any ERROR-level messages
```

---

## Monitoring

### Health Endpoint

```bash
curl https://your-domain.com/health
```

Returns:
```json
{
  "status": "healthy",
  "database": "connected",
  "scheduler": "running",
  "ai_provider": "gemini",
  "timestamp": "2026-02-27T..."
}
```

### Dashboard System Page

The System page in the dashboard is a live monitoring view:
- Database connection status
- AI provider health (live test call)
- Payment gateway reachability
- Active session count
- Scheduler job status

### Structured Logs

TELETRAAN logs structured JSON events via Loguru. On Render/Railway, all logs stream to the platform log viewer.

Key log events to watch:

| Event | Level | Meaning |
|:---|:---|:---|
| `webhook.received` | INFO | Incoming WhatsApp message |
| `session.created` | INFO | New customer session started |
| `order.confirmed` | INFO | Order successfully placed |
| `payment.received` | INFO | Payment webhook confirmed |
| `ai_provider.fallback` | WARNING | Primary AI failed, switched to secondary |
| `signature.invalid` | WARNING | Webhook HMAC check failed |
| `db.error` | ERROR | Database operation failed |
| `scheduler.job_failed` | ERROR | Background job failed |

### Background Jobs (14 total)

| Job | Frequency | Purpose |
|:---|:---|:---|
| Health check | Every 5 min | Verify DB + AI connectivity |
| Session cleanup | Every 6 hours | Remove stale sessions |
| Inventory sync | Every 2 hours | Pull catalog updates |
| Subscription check | Daily 9:00 AM | Check expiring subscriptions |
| Subscription reminders | Daily 9:00 AM | Send 7/3/1-day WhatsApp alerts |
| Daily report | Daily midnight | XLSX order summary per distributor |
| Weekly report | Monday 8:00 AM | Weekly performance digest |
| Monthly report | 1st of month | Monthly analytics compilation |
| Payment expiry check | Every 30 min | Mark expired pending payments |
| Prospect follow-up | Every 2 hours | Channel B nurturing sequences |

---

## Scaling

### Current Capacity

A single TELETRAAN instance handles:
- Unlimited distributors (data is fully tenant-scoped)
- ~200 concurrent active WhatsApp sessions (in-memory rate limiter ceiling)
- ~50 requests/second (Uvicorn async event loop)

### Scaling Paths

| Bottleneck | Solution | Complexity |
|:---|:---|:---|
| Concurrent sessions > 200 | Move rate limiter to Redis | Low — swap in-memory dict for Redis client |
| Request volume | Add Gunicorn workers: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app` | Trivial |
| Multiple instances | All state is in Supabase (no in-process state except rate limiter) | Low after Redis migration |
| DB query volume | Add read replica, materialized views for analytics aggregates | Medium |
| Background jobs at scale | Migrate to Celery + Redis broker | Medium |
| Primus connections | Add Nexus event publisher alongside analytics_repo.log_event() | Low per integration |

### Recommended Upgrade Path

```
Phase 1 (up to ~20 distributors)    → Single Render Starter instance, current architecture
Phase 2 (20–50 distributors)        → Redis rate limiter, Supabase Pro (connection pooling)
Phase 3 (50–100 distributors)       → 2 Gunicorn workers, Redis caching for hot catalog reads
Phase 4 (100+ distributors)         → Celery workers, read replica, dedicated analytics pipeline
Phase 5 (Primus integration)        → Nexus event bus publisher, Orion live API sync
```

---

## Troubleshooting

| Issue | Likely Cause | Fix |
|:---|:---|:---|
| App won't start | Missing required env var | Check startup logs for which var failed Pydantic validation |
| `ENCRYPTION_KEY invalid` | Not a valid Fernet key | Regenerate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| Dashboard shows 401 | Wrong ADMIN_API_KEY | Check the exact value in your `.env` — no trailing spaces |
| Dashboard shows 403 | Key format issue | Ensure the key is at least 16 characters |
| Webhook not receiving | Verify token mismatch | `META_VERIFY_TOKEN` in `.env` must match exactly what is in Meta dashboard |
| Webhook 400 on messages | HMAC signature fail | Ensure `META_APP_SECRET` is the App Secret (not App ID) |
| DB connection fails | Wrong Supabase keys | Use `service_role` key, not `anon` key |
| AI responses empty | Provider API key invalid | Test key directly: `curl` the provider API |
| Scheduler not running | Startup error | Look for `scheduler.start_failed` in logs |
| Voice messages ignored | `ENABLE_VOICE_PROCESSING=false` | Set to `true` and set `OPENAI_API_KEY` |
| Payment webhooks failing | Gateway signature config | Check gateway-specific webhook secret in `.env` |
| Inventory sync failing | No catalog source configured | Set `INVENTORY_SYNC_SOURCE` and credentials in `.env` |
