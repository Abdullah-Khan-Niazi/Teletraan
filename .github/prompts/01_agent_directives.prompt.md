# TELETRAAN Build Agent — Core Directives

## D1 — ZERO PLACEHOLDERS (CRITICAL)
Never write TODO, FIXME, `pass` in production paths, `raise NotImplementedError`,
placeholder functions, or "implement later" comments.
If a function signature is declared, it must be fully implemented in the same commit.
Partial implementations are forbidden — they create false confidence and runtime failures.

## D2 — PHASED EXECUTION + GIT (CRITICAL)
Execute phases in strict order: P1 → P2 → P3 → ... → P13.
Never start phase N+1 until phase N is verified working.
Commit after every logical unit: single file, related group (max 3-4), migration batch,
test file, or bug fix. Commit msg format: see 02_git_protocol.prompt.md.
Every commit ends with: `Signed-off-by: Abdullah-Khan-Niazi`

## D3 — PRODUCTION CODE STANDARDS (CRITICAL)
All code is production-grade from the first line. No "we'll clean this up later".
Type hints on every function: parameters and return values. No bare `Any`.
`from __future__ import annotations` on every file.
Pydantic v2 for all data validation — no raw dicts passed between layers.
async/await everywhere — no synchronous I/O in async context.
Never `time.sleep()` — use `asyncio.sleep()`.

## D4 — SECURITY STANDARDS (CRITICAL)
All secrets in `.env` only — never in source code.
`.env` is in `.gitignore` — verify before first commit.
Webhook signatures verified before any processing (HMAC-SHA256).
CNIC and sensitive fields encrypted with Fernet before DB write.
Phone numbers: last 4 digits only in all logs — never full number.
Input sanitized: length limits enforced, prompt injection patterns stripped.
SQL: use parameterized queries only — never string concatenation.

## D5 — ORDER CONTEXT PERSISTENCE (CRITICAL)
Entire order state stored in `sessions.pending_order_draft` (JSONB) after every
state transition. Bot must survive a complete process restart mid-order and resume
from the exact conversation state. See 07_order_context_schema.prompt.md for full spec.
Never store in-process memory as the only source of order state.

## D6 — MULTI-PROVIDER ABSTRACTION (CRITICAL)
All AI provider calls go through the abstract `AIProvider` base class — never call
Gemini, OpenAI, Anthropic, Cohere, or OpenRouter APIs directly from business logic.
All payment gateway calls go through the abstract `PaymentGateway` base class — never
call JazzCash, EasyPaisa, SafePay, NayaPay APIs directly from business logic.
Provider/gateway is determined by env var. Switching = change one variable, zero code changes.

## D7 — MODULAR ARCHITECTURE (HIGH)
Each module in the folder structure has exactly one responsibility.
Repositories talk only to the database. Services talk to repositories and other services.
API layer talks only to services and channels. Channels talk to services, AI, and WhatsApp.
No cross-layer shortcuts. No circular imports.

## D8 — DOCUMENTATION (HIGH)
Every module-level docstring explains WHAT the module does and WHY it exists.
Every public function has a Google-style docstring: Args, Returns, Raises.
README.md is accurate and complete by P13.
All docs/ files are written and accurate before deployment.

## D9 — DATABASE FIRST (HIGH)
Migrations before models. Models before repositories. Repositories before services.
Services before API. Never write service code referencing a table that doesn't exist yet.
Schema is the source of truth — never mutate tables ad hoc.
All 27 migration files in `migrations/` are applied in order and verified in Supabase.

## D10 — TESTING (HIGH)
Unit tests for all core business logic. Integration tests for all webhook flows and DB operations.
Framework: pytest + pytest-asyncio. Minimum 80% coverage on core modules enforced by pytest-cov.
Tests mirror app/ structure under tests/. Every gateway, every AI provider, every FSM state tested.
"It should work" is not evidence — run the tests, check the coverage, then commit.

## D11 — FOLDER STRUCTURE STRICT (HIGH)
Follow the exact folder structure defined in 04_folder_structure.prompt.md.
Do not deviate, merge, abbreviate, or skip any directory or file.
This is an industry-standard Python project layout — follow it precisely.
Every package directory has an `__init__.py`.

## D12 — GIT PROTOCOL (HIGH)
Follow the GIT PROTOCOL (02_git_protocol.prompt.md) exactly.
Commit frequently — every logical unit of work.
Commit messages must follow Linus Torvalds style — imperative, specific, technical, no fluff.
Every commit message must end with: `Signed-off-by: Abdullah-Khan-Niazi`
Never batch multiple unrelated changes in one commit.
