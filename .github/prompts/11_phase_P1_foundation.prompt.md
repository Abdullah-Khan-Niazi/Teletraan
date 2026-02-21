# Phase 1 — Foundation, Infrastructure, and Git Setup

**Prerequisites:** None — this is the first phase.
**Verify before P2:** Server starts, `/health` returns 200, all 27 migrations applied in Supabase.

## Steps (execute in order, commit after each)

1. `git init` — first command executed  
   → Commit: *(none yet)*

2. Create `.gitignore` — second command  
   → Commit: `"project: add .gitignore for Python/FastAPI project"`

3. Create `.env.example` with ALL variables (see `06_environment_variables.prompt.md`)  
   → Commit: `"config: add .env.example with complete variable documentation"`

4. Create `README.md` skeleton  
   → Commit: `"docs: add README skeleton with project overview and quickstart"`

5. Create `pyproject.toml` + `requirements.txt` + `requirements-dev.txt`  
   → Commit: `"build: add Python project metadata and pinned dependencies"`

6. Create `.pre-commit-config.yaml` (black, isort, flake8)  
   → Commit: `"ci: add pre-commit hooks for code quality enforcement"`

7. Create complete folder structure with all `__init__.py` files (see `04_folder_structure.prompt.md`)  
   → Commit: `"project: scaffold complete industry-standard folder structure"`

8. Implement `app/core/config.py` — Pydantic Settings, all env vars typed and validated, startup fails if missing  
   → Commit: `"core: implement Pydantic Settings with all env vars typed and validated"`

9. Implement `app/core/logging.py` — loguru, JSON in prod, colored in dev, PII masking filter  
   → Commit: `"core: implement loguru structured logging with PII masking filter"`

10. Implement `app/core/exceptions.py` — full custom exception hierarchy  
    → Commit: `"core: define complete custom exception hierarchy"`

11. Implement `app/core/constants.py` — all enums, state names, limits, timeouts  
    → Commit: `"core: define all enums, state names, limits, and timeouts"`

12. Implement `app/core/security.py` — HMAC verification, Fernet encrypt/decrypt, token utilities  
    → Commit: `"security: add HMAC verification, Fernet encryption, and token utilities"`

13. Implement `app/db/client.py` — Supabase client singleton, connection validation, health check  
    → Commit: `"db: implement Supabase client singleton with connection validation"`

14. Write all 27 migration SQL files in `migrations/` — commit in groups:  
    → `"db: migrations 001-007 core tables (plans, distributors, customers, catalog, rules, zones)"`  
    → `"db: migrations 008-014 sessions, orders, order_items, status_history, payments, complaints, tickets"`  
    → `"db: migrations 015-021 prospects, service_registry, notifications_log, audit_log, sync_log, analytics, rate_limits"`  
    → `"db: migrations 022-027 scheduled_messages, import_history, bot_config, RLS, indexes, seed_data"`

15. Apply migrations to Supabase — verify all tables exist  
    → Commit: `"db: apply all 27 migrations, verify schema in Supabase"`

16. Implement all Pydantic DB models including `order_context.py`  
    → Commit: `"db: add Pydantic models for all 15 database entities"`

17. Implement all 15 repository files in `app/db/repositories/`  
    → Commit per group: `"db: add repository layer for [domain] with full CRUD and query methods"`

18. Implement `app/main.py` — FastAPI factory, lifespan, middleware, router registration  
    → Commit: `"app: implement FastAPI factory with lifespan, middleware, and router registration"`

19. Implement `app/api/health.py` — `/health` endpoint checking all system dependencies  
    → Commit: `"api: add /health endpoint checking all system dependencies"`

20. Verify server starts, `/health` returns 200  
    → **PHASE 1 COMPLETE** Commit: `"phase-1: foundation and infrastructure complete, health check passing"`
