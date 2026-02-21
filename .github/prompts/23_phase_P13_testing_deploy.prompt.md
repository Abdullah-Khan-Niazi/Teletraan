# Phase 13 — Testing, Documentation, Deployment

**Prerequisites:** Phase 12 complete and verified.
**Final phase — verify all 27 checklist items in `24_verification_checklist.prompt.md` before final commit.**

## Steps (execute in order, commit after each)

1. Complete all remaining unit and integration tests to reach 80% coverage  
   Run: `pytest --cov=app --cov-report=term-missing --cov-fail-under=80`  
   Fill gaps in: core modules, AI providers, payment gateways, FSMs, order context  
   → Commit: `"tests: complete test suite, 80%+ coverage on core modules"`

2. Write all `docs/` files:  
   - `docs/architecture.md` — system design, component interactions, data flows  
   - `docs/api_reference.md` — all endpoints, payloads, authentication  
   - `docs/database_schema.md` — all 27 tables with descriptions  
   - `docs/deployment_guide.md` — Render + Railway deployment steps  
   - `docs/onboarding_guide.md` — how to onboard a new distributor  
   - `docs/payment_gateways.md` — integration guide for each gateway  
   - `docs/ai_providers.md` — how to switch providers, provider notes  
   - `docs/conversation_flows.md` — visual/textual flow diagrams for Channel A and B  
   → Commit: `"docs: add architecture, schema, deployment, payment gateways, AI providers, flows guides"`

3. Write all `scripts/` utility files:  
   - `scripts/run_migrations.py` — runs all migrations in order against Supabase  
   - `scripts/seed_catalog.py` — seeds catalog from Excel/CSV file  
   - `scripts/create_distributor.py` — creates a distributor with full configuration  
   - `scripts/test_webhook_locally.py` — sends test payloads to local webhook  
   - `scripts/rotate_api_keys.py` — rotates API keys and updates `.env`  
   → Commit: `"scripts: add migrations runner, catalog seeder, distributor creator, webhook tester"`

4. Create `render.yaml` and `Procfile` for Render and Railway deployments  
   → Commit: `"deploy: add Render and Railway deployment configurations"`

5. Deploy to Render — verify `/health` green, webhook verified, scheduler jobs active  
   → Commit: `"deploy: production deployment on Render verified and live"`

6. Full end-to-end smoke test on **production**:  
   - Send message to Channel A → receive response  
   - Send voice order → transcription correct → order confirmed  
   - Payment link generated and confirmed (dummy gateway)  
   - Channel B flow: first message → qualified → service shown  
   - Scheduler: verify jobs running in Render logs  
   → Commit: `"test: production smoke test passed — all flows verified on live deployment"`

7. **FINAL COMMIT:** `"teletraan: v1.0.0 complete — production-ready, all features implemented, all tests passing"`
