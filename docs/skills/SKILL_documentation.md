# SKILL: Documentation Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before writing any documentation or finishing any module.

---

## IDENTITY

This skill defines documentation requirements for TELETRAAN. Code without
documentation is a liability. Every module must be understandable to a developer
who has never seen it before — purely from reading the code and its docs.
Documentation is written alongside code, not after.

---

## README.md — ROOT LEVEL

The root README.md must contain all of:

```markdown
# TELETRAAN
WhatsApp Intelligent Order & Operations System — Pakistan Medicine Distribution

## What It Does
[2-paragraph plain English description]

## Architecture Overview
[ASCII diagram of system components]

## Quick Start (Local Development)
[Step-by-step — clone, .env setup, migrations, run]

## Project Structure
[Folder tree with 1-line description per directory]

## Environment Variables
[Table: Variable | Required | Default | Description]

## Running Tests
[Exact pytest commands]

## Deployment
[Link to docs/deployment_guide.md]

## Payment Gateways
[Link to docs/payment_gateways.md — which are supported, how to switch]

## AI Providers
[Link to docs/ai_providers.md — which are supported, how to switch]
```

---

## docs/ DIRECTORY — ALL FILES REQUIRED

### docs/architecture.md
- System ASCII topology diagram (both channels)
- Component responsibilities
- Data flow description
- Multi-tenant isolation explanation

### docs/database_schema.md
- Every table with column descriptions
- Relationship diagram (ASCII or described)
- Index rationale
- RLS policy description

### docs/deployment_guide.md
- Render deployment step-by-step
- Railway deployment step-by-step
- Environment variable setup guide
- Meta webhook URL registration steps
- Supabase project setup steps
- First distributor onboarding steps

### docs/onboarding_guide.md
- How to onboard a new distributor (from system owner perspective)
- Required information to collect from distributor
- Steps in the automated onboarding sequence
- What the distributor will receive and when

### docs/conversation_flows.md
- All Channel A FSM states with ASCII state diagram
- All Channel B FSM states with ASCII state diagram
- All interrupt commands and their behavior
- OrderContext lifecycle diagram

### docs/payment_gateways.md
- Supported gateways table: Gateway | Status | Auth Method | Supported Operations
- How to switch active gateway (env var)
- How to add a new gateway (implement base class)
- Per-gateway setup instructions (what credentials to get and where)
- Webhook URL format per gateway

### docs/ai_providers.md
- Supported providers table: Provider | Status | Text Model | Audio Model
- How to switch active provider (env var)
- How to add a new provider (implement base class)
- Per-provider setup (API key sources)
- Urdu language support notes per provider

### docs/api_reference.md
- All admin API endpoints
- Request/response schemas
- Authentication (X-Admin-Key)
- Example curl commands

---

## MODULE-LEVEL DOCSTRINGS — EVERY FILE

Every Python file must start with a module docstring:

```python
"""Order context store — durable persistence of in-flight order drafts.

This module implements the complete lifecycle of the OrderContext: creation,
loading, saving (with optimistic concurrency), billing recomputation, finalization,
and clearing. All order state is persisted to Supabase before any WhatsApp response
is sent, ensuring orders survive process restarts and session timeouts.

Key class: ContextStore
Key model: OrderContext (defined in app/db/models/session.py)
"""
```

---

## CLASS DOCSTRINGS — EVERY PUBLIC CLASS

```python
class BillingService:
    """Calculates order bills, applies discount rules, and computes delivery charges.

    All amounts are in paisas (PKR × 100) as integers to avoid floating-point
    precision errors. Discount rules are applied in priority order (highest first).
    Non-stackable rules are mutually exclusive — only the highest-priority rule applies.

    Attributes:
        discount_repo: Repository for fetching active discount rules.
        delivery_zone_repo: Repository for fetching zone delivery charges.
    """
```

---

## FUNCTION DOCSTRINGS — EVERY PUBLIC FUNCTION

Google style. Args, Returns, Raises sections required when applicable.
See SKILL_python_standards.md for the template.

---

## .env.example — ALWAYS UP TO DATE

Every time a new environment variable is added to config.py, it MUST be added
to .env.example immediately in the same commit.

Format:
```bash
# ── Application ──────────────────────────────────────────────
APP_ENV=development           # Required. Values: development, staging, production
APP_HOST=0.0.0.0
APP_PORT=8000
APP_SECRET_KEY=               # Required. 64-char random string. Generate: openssl rand -hex 32
ADMIN_API_KEY=                # Required. Set a strong random string.
LOG_LEVEL=INFO                # Values: DEBUG, INFO, WARNING, ERROR
ENCRYPTION_KEY=               # Required. Fernet key. Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## INLINE COMMENTS — WHEN TO USE

Add inline comments for:
- Non-obvious business logic ("Paisas not PKR — avoid float precision")
- Security-critical code ("Constant-time comparison to prevent timing attacks")
- Workarounds ("APScheduler requires coalesce=True to prevent reminder storms")
- Config values with non-obvious meaning ("Grace period: 3 days after expiry before suspension")

Do NOT add comments that merely restate the code:
```python
# Get customer by phone  ← USELESS — the function name already says this
customer = await customer_repo.get_by_phone(phone)
```

---

## OPENAPI DOCUMENTATION

FastAPI auto-generates OpenAPI docs at `/docs` (dev only).
Enhance with:
- `summary` and `description` on every route
- `response_model` on every route
- `responses` dict for non-200 status codes
- `tags` for grouping in the docs UI

```python
@router.post(
    "/webhook",
    summary="Receive WhatsApp webhook events",
    description="Receives and processes all incoming WhatsApp messages and status updates. HMAC-SHA256 verified.",
    responses={403: {"description": "Invalid webhook signature"}},
    tags=["webhook"],
)
```

---

## CHANGELOG — KEPT IN COMMITS

TELETRAAN does not maintain a separate CHANGELOG.md file.
The git log IS the changelog — this is why commit messages must be detailed.
Use `git log --oneline --graph` to review project history.

---

## SCRIPTS DOCUMENTATION

Every script in `/scripts/` must have:
- Module-level docstring explaining purpose and usage
- `if __name__ == "__main__":` block
- `argparse` or similar for any CLI arguments
- `--help` output that clearly explains all arguments and their effects

Example: `python scripts/create_distributor.py --help` should print a clear guide.
