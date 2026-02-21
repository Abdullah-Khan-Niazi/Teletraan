# TELETRAAN — SKILLS INDEX
# Owner: Abdullah-Khan-Niazi
# Version: 2.0 (21 skills total)
# Read this file FIRST before reading any individual skill.

---

## WHAT ARE SKILLS

Skills are protocol documents that define HOW things must be done in the TELETRAAN
project. They are not optional reference material. They are mandatory operating
procedures. Every skill file must be read before working on the area it covers.

The build agent must read every relevant skill before writing a single line of code
in that domain. Skills prevent mistakes that are expensive to fix later.

---

## SKILL FILES — READ ORDER FOR NEW AGENT

### PHASE 1 — FOUNDATION (Read before any code)

| # | File | Domain | Read When |
|---|---|---|---|
| 1 | SKILL_system_prompt.md | Agent identity and core constraints | Before anything |
| 2 | SKILL_git_protocol.md | Git commits and branching | Before first commit |
| 3 | SKILL_python_standards.md | Code style and structure | Before writing Python |
| 4 | SKILL_database.md | Schema, migrations, repositories | Before touching DB |
| 5 | SKILL_security.md | Auth, encryption, secrets | Before any I/O code |
| 6 | SKILL_error_handling.md | Exception handling | Before any I/O module |
| 7 | SKILL_logging.md | Structured logging | Before any module |

### PHASE 2 — CORE SYSTEMS (Read before building those systems)

| # | File | Domain | Read When |
|---|---|---|---|
| 8 | SKILL_ai_providers.md | Pluggable AI layer | Before AI module |
| 9 | SKILL_payment_gateways.md | Pluggable payment layer | Before payments module |
| 10 | SKILL_order_context.md | Order state persistence | Before order flows |
| 11 | SKILL_whatsapp.md | Meta API integration | Before WhatsApp module |
| 12 | SKILL_scheduler.md | Background jobs | Before scheduler module |
| 13 | SKILL_mcp.md | Model Context Protocol tools | Before MCP module |

### PHASE 3 — INTELLIGENCE LAYER (Read before building AI/conversation)

| # | File | Domain | Read When |
|---|---|---|---|
| 14 | SKILL_teletraan_persona.md | Bot character and hard limits | Before any AI prompt |
| 15 | SKILL_teletraan_system_prompts.md | Prompt engineering rules | Before writing prompts |
| 16 | SKILL_voice_and_tone.md | Bot voice vs human operator voice | Before any response text |
| 17 | SKILL_orchestration.md | Message pipeline coordination | Before core orchestrator |
| 18 | SKILL_ux.md | Conversation design and flow | Before any conversation flow |

### PHASE 4 — OPERATIONS (Read before completing project)

| # | File | Domain | Read When |
|---|---|---|---|
| 19 | SKILL_analytics.md | Business metrics and reporting | Before analytics module |
| 20 | SKILL_human_operator.md | Owner/sales rep communication | Before notification templates |
| 21 | SKILL_testing.md | Test strategy and coverage | Before writing tests |
| 22 | SKILL_documentation.md | Docs and docstrings | Before finishing any module |

---

## NON-NEGOTIABLE RULES (COMBINED FROM ALL SKILLS)

### Code Rules
1. Every commit ends with: `Signed-off-by: Abdullah-Khan-Niazi`
2. Zero placeholders — no TODO, FIXME, pass, stub anywhere in production paths
3. All amounts in paisas (integer BIGINT) — never float, never PKR directly
4. All phone numbers masked in logs — show only last 4 digits
5. All secrets from environment — never hardcoded anywhere
6. Type hints on every function — no exceptions
7. Google-style docstring on every public function — no exceptions
8. 80%+ test coverage on core modules — enforced in CI

### Security Rules
9. HMAC verification on every incoming webhook — before any processing
10. Payment gateway webhook always returns 200 — handle idempotency internally
11. Dummy gateway never activatable in production — hard-enforced in factory
12. No card numbers or sensitive data accepted in chat — redirect to payment link

### Architecture Rules
13. AI provider and payment gateway switchable via env var — zero code changes
14. OrderContext persisted before every WhatsApp response — never memory-only
15. Every scheduler job is idempotent — running twice has same effect as once
16. Every except block logs and acts — no silent swallowing
17. All MCP tool calls validated against distributor_id before execution
18. Context saved (step N) always before WhatsApp send (step N+1)

### Bot Persona Rules
19. TELETRAAN never pretends to be human when sincerely asked
20. TELETRAAN never gives medical advice — redirect to doctor
21. Every customer-facing error message uses the template from errors.py — never raw exceptions
22. Every bot response ≤ 5 lines (except bill summary ≤ 20 lines, onboarding ≤ 10 lines)

---

## SKILLS COVERAGE MAP

| Module | Skills Required |
|---|---|
| app/core/config.py | SKILL_python_standards, SKILL_security |
| app/core/security.py | SKILL_security |
| app/core/logging.py | SKILL_logging |
| app/core/orchestrator.py | SKILL_orchestration, SKILL_error_handling |
| app/core/channel_a_orchestrator.py | SKILL_orchestration, SKILL_ux, SKILL_voice_and_tone |
| app/core/channel_b_orchestrator.py | SKILL_orchestration, SKILL_human_operator |
| app/core/fsm.py | SKILL_orchestration, SKILL_ux |
| app/db/** | SKILL_database, SKILL_python_standards |
| app/ai/base.py | SKILL_ai_providers |
| app/ai/providers/** | SKILL_ai_providers, SKILL_error_handling |
| app/ai/prompts/** | SKILL_teletraan_system_prompts, SKILL_teletraan_persona, SKILL_voice_and_tone |
| app/mcp/** | SKILL_mcp, SKILL_security, SKILL_error_handling |
| app/payments/base.py | SKILL_payment_gateways |
| app/payments/gateways/** | SKILL_payment_gateways, SKILL_security, SKILL_error_handling |
| app/whatsapp/** | SKILL_whatsapp, SKILL_error_handling |
| app/channels/** | SKILL_order_context, SKILL_whatsapp, SKILL_ux |
| app/orders/context_store.py | SKILL_order_context, SKILL_database |
| app/scheduler/** | SKILL_scheduler, SKILL_error_handling |
| app/analytics/** | SKILL_analytics, SKILL_database |
| app/notifications/owner.py | SKILL_human_operator, SKILL_voice_and_tone |
| app/notifications/errors.py | SKILL_ux, SKILL_voice_and_tone |
| app/api/webhook.py | SKILL_whatsapp, SKILL_security |
| app/api/payments.py | SKILL_payment_gateways, SKILL_security |
| tests/** | SKILL_testing |
| All Python files | SKILL_python_standards, SKILL_documentation, SKILL_logging |
| All commits | SKILL_git_protocol |

---

## QUICK REFERENCE — WHICH SKILL ANSWERS WHICH QUESTION?

| Question | Skill |
|---|---|
| "How do I write a commit message?" | SKILL_git_protocol |
| "How do I add a new AI provider?" | SKILL_ai_providers |
| "How do I add a new payment gateway?" | SKILL_payment_gateways |
| "What fields go in OrderContext?" | SKILL_order_context |
| "How do I write a system prompt?" | SKILL_teletraan_system_prompts |
| "What should TELETRAAN sound like?" | SKILL_teletraan_persona, SKILL_voice_and_tone |
| "How do I add a new MCP tool?" | SKILL_mcp |
| "How does a message go from webhook to response?" | SKILL_orchestration |
| "How should the owner notification look?" | SKILL_human_operator |
| "What UX rules apply to bot messages?" | SKILL_ux |
| "How do I set up a scheduled job?" | SKILL_scheduler |
| "How do I handle a DB error?" | SKILL_error_handling |
| "What goes in the daily analytics?" | SKILL_analytics |
| "How do I structure a test file?" | SKILL_testing |
