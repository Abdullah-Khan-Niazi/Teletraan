# TELETRAAN BUILD AGENT — START HERE

**You are the TELETRAAN Build Agent.**
**Model:** Claude Opus 4.6
**Mission:** Build the TELETRAAN WhatsApp order and operations system to production-ready completion.
**Workspace:** `d:\Projects\Teletraan`

---

## FIRST — READ THESE BEFORE WRITING A SINGLE LINE OF CODE

In order:

1. **`.github/prompts/01_agent_directives.prompt.md`** — 12 non-negotiable rules. Read fully. Internalize.
2. **`.github/prompts/02_git_protocol.prompt.md`** — Commit format. Every commit from now follows this exactly.
3. **`.github/prompts/03_project_identity_and_tech_stack.prompt.md`** — What you're building, every dependency.
4. **`.github/prompts/04_folder_structure.prompt.md`** — The exact directory tree. Never deviate.
5. **`.github/prompts/05_database_schema.prompt.md`** — All 27 tables. This is your schema law.
6. **`.github/prompts/06_environment_variables.prompt.md`** — All 50+ env vars. Reference before writing config.
7. **`.github/prompts/07_order_context_schema.prompt.md`** — The JSONB order state spec. Critical for Phase 4+.
8. **`.github/prompts/08_ai_provider_abstraction.prompt.md`** — AI abstract base. Read before Phase 3.
9. **`.github/prompts/09_payment_gateway_abstraction.prompt.md`** — Gateway abstract base. Read before Phase 8.

Then read the **relevant skill files** in `.github/instructions/` before each domain:

| When | Read |
|---|---|
| Always | `01_system_prompt.instructions.md`, `02_git_protocol.instructions.md` |
| Any Python | `03_python_standards.instructions.md`, `06_error_handling.instructions.md`, `07_logging.instructions.md` |
| DB work | `04_database.instructions.md` |
| Security code | `05_security.instructions.md` |
| AI module | `08_ai_providers.instructions.md`, `14_teletraan_persona.instructions.md`, `15_teletraan_system_prompts.instructions.md` |
| Payments | `09_payment_gateways.instructions.md` |
| Order flows | `10_order_context.instructions.md` |
| WhatsApp | `11_whatsapp.instructions.md` |
| Scheduler | `12_scheduler.instructions.md` |
| Channels | `16_voice_and_tone.instructions.md`, `17_orchestration.instructions.md`, `18_ux.instructions.md` |
| Analytics | `19_analytics.instructions.md` |
| Notifications | `20_human_operator.instructions.md` |
| Tests | `21_testing.instructions.md` |

---

## THE BUILD SEQUENCE — 13 PHASES

Execute phases in strict order. Never start N+1 until N is verified. Each phase has its own prompt file.

| Phase | Prompt File | What You Build |
|---|---|---|
| **P1** | `11_phase_P1_foundation.prompt.md` | Git, config, logging, exceptions, DB client, all 27 migrations, all repos, health endpoint |
| **P2** | `12_phase_P2_whatsapp.prompt.md` | WhatsApp client, parser, media, webhook API, channel router, notification templates |
| **P3** | `13_phase_P3_ai_engine.prompt.md` | All 5 AI providers, factory, NLU, voice pipeline, response generator, prompts |
| **P4** | `14_phase_P4_order_context.prompt.md` | OrderContext Pydantic model, context manager (16 functions), both FSMs, session expiry |
| **P5** | `15_phase_P5_channel_a.prompt.md` | Fuzzy matcher, catalog, billing, all Channel A flows, order service |
| **P6** | `16_phase_P6_order_logging.prompt.md` | Order logger, Excel generator, PDF generator |
| **P7** | `17_phase_P7_inventory.prompt.md` | Sync service, stock service, inventory scheduler job |
| **P8** | `18_phase_P8_payments.prompt.md` | All 6 payment gateways, factory, webhook handlers, payment API endpoints |
| **P9** | `19_phase_P9_distributor_mgmt.prompt.md` | Subscription FSM, reminder service, notifications, onboarding, support tickets, scheduler jobs |
| **P10** | `20_phase_P10_channel_b.prompt.md` | Service registry, sales flow, onboarding flow, Channel B handler |
| **P11** | `21_phase_P11_analytics.prompt.md` | All analytics services, report generators, all scheduler jobs |
| **P12** | `22_phase_P12_security_admin.prompt.md` | Rate limiting, admin API, security audit, CNIC encryption verification |
| **P13** | `23_phase_P13_testing_deploy.prompt.md` | 80% coverage, all docs/, scripts/, render.yaml, production deploy, smoke test |

**Final gate:** `24_verification_checklist.prompt.md` — all 27 items checked before final commit.

---

## CURRENT STATE

- Git initialized: ✅ (2 commits on `master`)
- Project structure: ✅ scaffolded in previous session
- Skill instruction files: ✅ (21 files in `.github/instructions/`)
- Build prompt files: ✅ (24 files in `.github/prompts/`)
- App code: ❌ **None yet — start with Phase 1**

---

## YOUR FIRST COMMAND

```bash
# You are in d:\Projects\Teletraan
# Verify git config before anything else:
git config user.name "TELETRAAN-Agent"
git config user.email "agent@teletraan.pk"
git log --oneline
```

Then **open `11_phase_P1_foundation.prompt.md`** and execute Step 1.

---

## NON-NEGOTIABLE REMINDERS

- Every commit ends with `Signed-off-by: Abdullah-Khan-Niazi` — no exceptions
- Never write `TODO`, `pass`, `raise NotImplementedError` in production paths
- Never commit `.env` — verify `.gitignore` covers it before first file creation
- Financial amounts are always **paisas (integer)** — never floats, never PKR decimals
- Phone numbers in logs: **last 4 digits only** — never full number
- All code is `async def` — never blocking I/O in async context
- After each phase completes: verify it works, then commit the phase-complete commit, then move to next phase
