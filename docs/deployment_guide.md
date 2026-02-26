# TELETRAAN — Deployment Guide

## Prerequisites

- Python 3.11+
- Supabase project with PostgreSQL
- Meta WhatsApp Business API credentials
- At least one AI provider API key (Gemini recommended)
- Domain with HTTPS for webhook endpoint

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all required values:

```bash
cp .env.example .env
```

### Required Variables

```env
# Application
APP_SECRET_KEY=<random-64-char-string>
ENCRYPTION_KEY=<fernet-key-from-python>
ADMIN_API_KEY=<strong-api-key>

# Meta WhatsApp
META_APP_ID=<meta-app-id>
META_APP_SECRET=<meta-app-secret>
META_VERIFY_TOKEN=<custom-verify-token>
OWNER_PHONE_NUMBER_ID=<owner-phone-number-id>
OWNER_WHATSAPP_NUMBER=<+923xxxxxxxxx>

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJhbG...

# AI Provider (at least one)
GEMINI_API_KEY=AIza...
```

### Generate Encryption Key

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

---

## Database Setup

### 1. Run Migrations

Migrations are in `app/db/migrations/` numbered `001_` through `028_`.
Run them in order against your Supabase project:

```bash
python scripts/run_migrations.py
```

Or manually via the Supabase SQL editor — paste each migration file in order.

### 2. Seed Initial Data

```bash
# Create a subscription plan
python scripts/create_distributor.py

# Seed the medicine catalog from CSV
python scripts/seed_catalog.py --file catalog.csv --distributor-id <uuid>
```

---

## Render Deployment

### Using render.yaml

The repository includes a `render.yaml` Blueprint:

```bash
# Push to GitHub, then connect the repo in Render dashboard
# Render will auto-detect render.yaml and configure the service
```

### Manual Setup

1. Create a new **Web Service** on Render
2. Connect your GitHub repository
3. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Python Version:** 3.11
4. Add all environment variables from `.env`
5. Deploy

### Post-Deploy Verification

```bash
# Health check
curl https://your-app.onrender.com/health

# Should return: {"status": "healthy", ...}
```

---

## Railway Deployment

1. Install Railway CLI: `npm install -g @railway/cli`
2. Login: `railway login`
3. Initialize: `railway init`
4. Deploy:

```bash
railway up
```

5. Set environment variables:

```bash
railway variables set APP_SECRET_KEY=xxx
railway variables set META_APP_SECRET=xxx
# ... repeat for all required vars
```

The `Procfile` defines the start command:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## WhatsApp Webhook Setup

### 1. Configure Meta App

1. Go to [Meta Developer Dashboard](https://developers.facebook.com/)
2. Select your app → WhatsApp → Configuration
3. Set **Callback URL:** `https://your-domain.com/api/webhook`
4. Set **Verify Token:** same as `META_VERIFY_TOKEN` env var
5. Subscribe to: `messages`, `messaging_postbacks`

### 2. Verify Webhook

Meta will send a GET request to verify. The app handles this automatically:

```
GET /api/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=CHALLENGE
```

---

## Monitoring

### Health Endpoint

`GET /health` returns system status including DB connectivity and scheduler state.

### Logs

Structured JSON logs via Loguru. On Render:
- View in Dashboard → Logs tab
- Filter by log level: ERROR, WARNING, INFO

### Scheduler Jobs

14 background jobs run automatically:
- Health checks every 5-15 minutes
- Session cleanup every 6 hours
- Inventory sync every 2 hours
- Report generation on schedule (daily/weekly/monthly)

Verify scheduler is running:

```bash
curl https://your-app.com/api/admin/status \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

---

## Scaling Considerations

- **Single instance** is sufficient for up to ~50 distributors
- For higher load: use Render Pro plan with autoscaling
- Database: Supabase Pro plan for connection pooling
- Consider Redis for rate limiting at scale (currently in-memory)

---

## Troubleshooting

| Issue | Solution |
|---|---|
| App won't start | Check all required env vars are set |
| Webhook not receiving | Verify META_VERIFY_TOKEN matches Meta config |
| DB connection fails | Check SUPABASE_URL and SUPABASE_SERVICE_KEY |
| Signature verification fails | Ensure META_APP_SECRET is correct |
| Scheduler not running | Check logs for APScheduler startup messages |
| AI responses empty | Verify AI provider API key is valid |
