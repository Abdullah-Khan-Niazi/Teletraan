# GIT PROTOCOL SKILL

## SKILL: git-protocol | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines the complete git workflow for the TELETRAAN project.
Every commit tells a story. The git log is documentation. Future maintainers
(including you after a break) must be able to understand the history of
every decision from the commit log alone.

---

## INITIAL SETUP

Execute these commands at project start, before any other file is created:

```bash
git init
git config user.name "Abdullah-Khan-Niazi"
git config user.email "abdullahniazi078@gmail.com"
```

First commit must be ONLY the .gitignore:

```bash
# Create .gitignore first — nothing else
git add .gitignore
git commit -m "Initial commit: add .gitignore before any other files

Establishes the git ignore rules before any artifacts are created.
Prevents accidental commit of .env files, __pycache__, .venv,
compiled Python files, log directories, and IDE configuration.

This must always be the very first commit in any Python project.

Signed-off-by: Abdullah-Khan-Niazi"
```

---

## .gitignore MANDATORY CONTENTS

```
# Environment — NEVER commit
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/

# Testing
.pytest_cache/
.coverage
htmlcov/
coverage.xml

# Logs
logs/
*.log

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Temp files
tmp/
temp/
*.tmp

# Supabase local (if any)
.supabase/

# Generated files (not for version control)
reports/
exports/
```

---

## COMMIT FREQUENCY RULES

### COMMIT AFTER — these events ALWAYS trigger a commit:

| Event                            | Example commit summary                                                  |
| -------------------------------- | ----------------------------------------------------------------------- |
| Single file completed            | `db: implement customer repository with full CRUD`                      |
| Group of related files (max 3-4) | `db: add Pydantic models for order, order_items, and order_context`     |
| Migration file(s) applied        | `db: migrations 001-005 applied and verified in Supabase`               |
| Test file written                | `tests: add unit tests for billing service discount logic`              |
| Bug fixed                        | `fix: resolve session retry_count not resetting after state transition` |
| Phase complete                   | `phase-3: AI engine complete with 5 providers, NLU, and voice pipeline` |
| Configuration change             | `config: add SafePay and NayaPay gateway env vars to settings`          |
| Dependency added                 | `build: add cryptography and phonenumbers to requirements.txt`          |
| Documentation written            | `docs: add complete payment gateway integration guide`                  |

### NEVER batch these in one commit:

- Different modules (e.g., billing + fuzzy matcher in one commit)
- Feature + tests (separate commits for each)
- Bug fix + new feature
- Multiple migration files if they serve different domains

---

## COMMIT MESSAGE FORMAT — STRICT

```
<scope>: <summary in imperative mood, max 72 characters>
<blank line>
<body — multiple paragraphs allowed, each line max 72 chars>
<explain WHY, not WHAT — code shows WHAT>
<mention any non-obvious design decisions>
<note anything future maintainers must know>
<blank line>
Signed-off-by: Abdullah-Khan-Niazi
```

### Scope reference:

| Scope              | When to use                                                     |
| ------------------ | --------------------------------------------------------------- |
| `project`          | Project structure, scaffolding                                  |
| `core`             | config.py, exceptions.py, constants.py, logging.py, security.py |
| `db`               | Models, repositories, migrations, client                        |
| `api`              | FastAPI routes: webhook.py, admin.py, payments.py, health.py    |
| `whatsapp`         | WhatsApp API client, parser, message_types, media               |
| `ai`               | AI providers, NLU, voice, prompts, factory                      |
| `channels`         | Router, Channel A, Channel B handlers and flows                 |
| `channel-a`        | Channel A specific flows only                                   |
| `channel-b`        | Channel B specific flows only                                   |
| `payments`         | Gateway implementations, factory, webhook handlers              |
| `inventory`        | Catalog service, fuzzy matcher, sync service, stock service     |
| `orders`           | Order service, billing, context manager, logging service        |
| `reporting`        | Excel, PDF generators, analytics service                        |
| `scheduler`        | APScheduler setup and all job definitions                       |
| `notifications`    | WhatsApp notifier, templates                                    |
| `analytics`        | Analytics services                                              |
| `distributor-mgmt` | Subscription, reminders, onboarding, support, notifications     |
| `security`         | Security hardening, rate limiting, audit                        |
| `tests`            | Any test file                                                   |
| `docs`             | Any documentation file                                          |
| `scripts`          | Utility scripts in scripts/                                     |
| `deploy`           | render.yaml, Procfile, deployment verification                  |
| `fix`              | Bug fixes                                                       |
| `refactor`         | Code reorganization without behavior change                     |
| `ci`               | Pre-commit, GitHub Actions, linting config                      |
| `build`            | requirements.txt, pyproject.toml, dependencies                  |
| `config`           | .env.example, environment variable changes                      |

---

## COMMIT MESSAGE EXAMPLES — STUDY THESE

### GOOD: Infrastructure commit

```
core: implement Pydantic Settings with startup validation for all env vars

All required environment variables are now typed, validated, and
documented in a single Settings class using Pydantic BaseSettings.

The application will refuse to start if any required variable is missing
or has an invalid value, failing fast with a clear error message rather
than discovering missing config at runtime during a customer order.

Added validators for: ACTIVE_AI_PROVIDER (must be known provider),
ACTIVE_PAYMENT_GATEWAY (must be known gateway), APP_ENV (must be
dev/staging/production), ENCRYPTION_KEY (must be valid Fernet key).

Signed-off-by: Abdullah-Khan-Niazi
```

### GOOD: Feature commit

```
payments: implement SafePay checkout gateway with HMAC webhook verification

SafePay is Pakistan's Stripe equivalent — supports Visa, Mastercard,
UnionPay, and mobile wallets. This makes TELETRAAN accessible to
distributors who prefer card payments over mobile money.

Implementation generates a hosted checkout URL via SafePay's v1 API.
The checkout page handles all card processing on SafePay's PCI-DSS
compliant servers — we never touch card data.

Webhook verification uses HMAC-SHA256 with the SAFEPAY_WEBHOOK_SECRET.
Signature mismatch alerts the owner via WhatsApp after 3 failures in
10 minutes (potential replay attack indicator).

Idempotency: duplicate webhook callbacks are detected by checking
gateway_transaction_id in the payments table before processing.

Signed-off-by: Abdullah-Khan-Niazi
```

### GOOD: Bug fix commit

```
fix: resolve order context pricing_snapshot not updating on item removal

When a customer removed an item from their in-progress order, the
pending_order_draft.pricing_snapshot retained the old total, causing
the bill shown to the customer to include removed items.

Root cause: context_manager.remove_item_from_context() was setting
the item's cancelled flag correctly but not calling
_recalculate_pricing_snapshot() afterward.

The fix calls _recalculate_pricing_snapshot() as the final step of
all item mutations: add, remove, update quantity, apply discount.
Added a test that confirms snapshot matches sum of active items.

Signed-off-by: Abdullah-Khan-Niazi
```

### GOOD: Test commit

```
tests: add unit tests for NLU intent classification across all languages

Tests cover:
- 8 intent types across Urdu, English, and Roman Urdu inputs
- Ambiguous inputs that should return 'unclear' intent
- Prompt injection attempts that should be sanitized before AI call
- Entity extraction for medicine names with quantities and units
- Roman Urdu normalization of common medicine name misspellings

All tests mock the AI provider — we test the NLU logic, not the
underlying AI model. Provider-specific behavior is tested in
test_ai_providers.py.

Signed-off-by: Abdullah-Khan-Niazi
```

### BAD: Do not write these

```bash
# TOO VAGUE
git commit -m "fix bug"
git commit -m "update code"
git commit -m "add stuff"
git commit -m "working now"
git commit -m "changes"

# PAST TENSE (wrong mood)
git commit -m "added payment gateway"
git commit -m "fixed session issue"

# MISSING SIGNED-OFF-BY
git commit -m "payments: add JazzCash gateway"  # Missing signature!

# NO BODY ON COMPLEX CHANGES
git commit -m "orders: implement complete order flow with billing, context, confirmation"
# (This needs a body explaining the design decisions)
```

---

## BRANCH STRATEGY (SINGLE DEVELOPER)

For this project (solo developer + agent): use `main` branch only.
No feature branches needed — frequent small commits on main serve the same
purpose of atomic, reviewable history.

If you need to experiment with something risky:

```bash
git stash  # Save current work
# Try experiment
git stash pop  # Restore if experiment failed
```

---

## PHASE COMPLETION COMMITS

At the end of every phase, the commit summary must follow this format:

```
phase-N: <phase name> complete — <what was verified>

Phase N implementation is complete and verified. All components listed
in the phase plan have been implemented, tested, and committed.

What was built:
- <bullet 1>
- <bullet 2>
- <bullet 3>

Verification:
- <how each component was tested>
- <what passing state was confirmed>

Next phase: <brief description of what P(N+1) will build>

Signed-off-by: Abdullah-Khan-Niazi
```

---

## RECOVERING FROM MISTAKES

### If you accidentally committed a secret:

```bash
# DO NOT push. Rotate the secret immediately. Then:
git reset HEAD~1  # Undo last commit, keep changes
# Remove secret from file
git add -p  # Stage carefully, not the secret
git commit -m "security: remove accidentally staged credentials

Credentials were accidentally included in previous commit.
All affected API keys have been rotated before this commit.
Rotation confirmation: [note which keys were rotated]

Signed-off-by: Abdullah-Khan-Niazi"
```

### If you committed unfinished work and need to amend:

```bash
# Add the missing changes
git add <files>
git commit --amend --no-edit  # Add to previous commit
```

### If a commit needs a better message:

```bash
git commit --amend -m "better message here..."
# (Only before pushing)
```

---

## PRE-COMMIT HOOKS

The `.pre-commit-config.yaml` must run before every commit:

- `black` — auto-format code
- `isort` — sort imports
- `flake8` — lint check

If pre-commit fails, fix the issues before committing.
Never use `--no-verify` to bypass hooks.

---

## VIEWING HISTORY

Use these to verify your commit hygiene:

```bash
git log --oneline -20       # Quick overview of last 20 commits
git log --stat -5           # See what files changed in last 5 commits
git show HEAD               # See full last commit
git log --grep="Signed-off-by: Abdullah-Khan-Niazi"  # Verify all commits signed
```

Every commit in the final history must appear in `git log --grep="Signed-off-by"`.
