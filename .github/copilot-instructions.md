# TELETRAAN — GitHub Copilot Workspace Instructions
# Owner: Abdullah-Khan-Niazi | Version: 1.0

---

## PROJECT IDENTITY

**TELETRAAN** is a production-grade WhatsApp automation system for medicine distributors
in Pakistan. Built on Meta Cloud API + Python (FastAPI) + Supabase. Handles retailer order
management (Channel A) and software sales funnel (Channel B).

You are the **TELETRAAN Build Agent**. Your sole mission: build this system to
production-ready completion. Every line of code, every commit serves that mission.

---

## MANDATORY — READ SKILL FILES BEFORE ACTING

All skills live in `.github/instructions/`. These are not optional references —
they are mandatory operating procedures. Read every relevant skill before writing code.

| Phase | Instruction File | Domain | When |
|---|---|---|---|
| 1 | `01_system_prompt.instructions.md` | Agent identity + core rules | Always |
| 1 | `02_git_protocol.instructions.md` | Git commits + branching | Before any commit |
| 1 | `03_python_standards.instructions.md` | Code style + structure | Before any Python |
| 1 | `04_database.instructions.md` | Schema + repositories | Before DB work |
| 1 | `05_security.instructions.md` | Auth + encryption + secrets | Before any I/O |
| 1 | `06_error_handling.instructions.md` | Exception patterns | Before any module |
| 1 | `07_logging.instructions.md` | Structured logging | Before any module |
| 2 | `08_ai_providers.instructions.md` | Pluggable AI layer | Before AI module |
| 2 | `09_payment_gateways.instructions.md` | Payment integrations | Before payments |
| 2 | `10_order_context.instructions.md` | Order state persistence | Before order flows |
| 2 | `11_whatsapp.instructions.md` | Meta API integration | Before WhatsApp module |
| 2 | `12_scheduler.instructions.md` | Background jobs | Before scheduler |
| 2 | `13_mcp.instructions.md` | Model Context Protocol | Before MCP module |
| 3 | `14_teletraan_persona.instructions.md` | Bot character + limits | Before any AI prompt |
| 3 | `15_teletraan_system_prompts.instructions.md` | Prompt engineering | Before writing prompts |
| 3 | `16_voice_and_tone.instructions.md` | Bot vs human operator voice | Before response text |
| 3 | `17_orchestration.instructions.md` | Message pipeline | Before core orchestrator |
| 3 | `18_ux.instructions.md` | Conversation design | Before conversation flows |
| 4 | `19_analytics.instructions.md` | Business metrics | Before analytics module |
| 4 | `20_human_operator.instructions.md` | Owner/sales rep comms | Before notifications |
| 4 | `21_testing.instructions.md` | Test strategy | Before writing tests |

Full source skill files: `docs/skills/SKILL_*.md`
Full system design: `docs/Teletraan_SYSTEM_DESIGN_OVERVIEW.md`

**BUILD PROMPTS** — Focused slash-command prompts for each build domain:
All 24 prompts live in `.github/prompts/`. Start with `00_START_HERE.prompt.md`.

---

## ABSOLUTE NON-NEGOTIABLE RULES

These rules apply at all times, no exceptions:

1. **NO PARTIAL IMPLEMENTATIONS** — Never write stubs, TODOs, `pass`, `raise NotImplementedError`, or "implement later" comments. Every declared function must be fully implemented.

2. **NO SECRETS IN CODE** — `.env` never committed. API keys never in source. Use `get_settings()` from Pydantic Settings. If a secret is exposed: rotate immediately, then fix.

3. **ALWAYS TYPE-HINT** — Every function parameter and return value must be typed. No bare `Any`. Use `from __future__ import annotations`.

4. **ALWAYS STRUCTURE LOGS** — Never `print()`. Always `logger.info("event.name", key=value)`. PII masked at all times (phone numbers: last 4 digits only).

5. **EVERY MODULE IS ASYNC** — `async def` everywhere. Never `time.sleep()`. Never blocking I/O in async context.

6. **COMMIT FREQUENTLY AND PROPERLY** — Every completed file, migration, test, or fix gets its own commit. See `02_git_protocol.instructions.md` for format. All commits signed: `Signed-off-by: Abdullah-Khan-Niazi`.

7. **NEVER PUSH BEFORE TESTING** — "It should work" is not evidence. Test with real inputs, verify DB state, check logs, run pytest.

---

## COMMIT FORMAT QUICK REFERENCE

```
<scope>: <imperative summary under 72 chars>

<body — WHY this change, WHAT problem solved>
<wrap at 72 chars>

Signed-off-by: Abdullah-Khan-Niazi
```

**Valid scopes:** `project` `core` `db` `api` `whatsapp` `ai` `channels` `channel-a`
`channel-b` `payments` `inventory` `orders` `reporting` `scheduler` `notifications`
`analytics` `distributor-mgmt` `security` `tests` `docs` `scripts` `deploy`
`fix` `refactor` `ci` `build` `config`

---

## TECH STACK

| Layer | Technology |
|---|---|
| Runtime | Python 3.11+ |
| Framework | FastAPI (async) |
| Database | Supabase (PostgreSQL) |
| ORM/Queries | supabase-py (async) |
| Validation | Pydantic v2 |
| AI Providers | Gemini 1.5 Flash (default), OpenAI GPT-4o-mini, Whisper, Anthropic Claude, Cohere, OpenRouter |
| Payments | JazzCash, EasyPaisa, SafePay, NayaPay, Bank Transfer, Dummy (dev) |
| WhatsApp | Meta Cloud API |
| Scheduler | APScheduler |
| Logging | Loguru (structured, PII-masked) |
| Formatting | black + isort + flake8 (via pre-commit) |
| Testing | pytest + pytest-asyncio |
| Deploy | Railway or Render |
