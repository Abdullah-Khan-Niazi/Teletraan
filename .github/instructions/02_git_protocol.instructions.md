---
applyTo: "**"
---

# SKILL 02 — GIT PROTOCOL
## Source: `docs/skills/SKILL_git_protocol.md`

---

## COMMIT FORMAT — STRICT

```
<scope>: <imperative summary, max 72 chars>

<body — WHY this change, WHAT problem solved>
<wrap at 72 chars per line>
<explain non-obvious design decisions>
<note what future maintainers must know>

Signed-off-by: Abdullah-Khan-Niazi
```

**All commits MUST end with `Signed-off-by: Abdullah-Khan-Niazi`.**
Missing signature = invalid commit.

---

## SCOPE REFERENCE

| Scope | Use for |
|---|---|
| `project` | Project structure, scaffolding |
| `core` | config.py, exceptions.py, constants.py, logging.py, security.py |
| `db` | Models, repositories, migrations, client |
| `api` | FastAPI routes: webhook.py, admin.py, payments.py, health.py |
| `whatsapp` | WhatsApp API client, parser, message_types, media |
| `ai` | AI providers, NLU, voice, prompts, factory |
| `channels` | Router, Channel A/B handlers and flows |
| `channel-a` | Channel A specific flows only |
| `channel-b` | Channel B specific flows only |
| `payments` | Gateway implementations, factory, webhook handlers |
| `inventory` | Catalog service, fuzzy matcher, sync service, stock service |
| `orders` | Order service, billing, context manager, logging service |
| `reporting` | Excel, PDF generators, analytics service |
| `scheduler` | APScheduler setup and all job definitions |
| `notifications` | WhatsApp notifier, templates |
| `analytics` | Analytics services |
| `distributor-mgmt` | Subscription, reminders, onboarding, support |
| `security` | Security hardening, rate limiting, audit |
| `tests` | Any test file |
| `docs` | Any documentation file |
| `scripts` | Utility scripts in scripts/ |
| `deploy` | render.yaml, Procfile, deployment verification |
| `fix` | Bug fixes |
| `refactor` | Code reorganization without behavior change |
| `ci` | Pre-commit, GitHub Actions, linting config |
| `build` | requirements.txt, pyproject.toml, dependencies |
| `config` | .env.example, environment variable changes |

---

## COMMIT FREQUENCY RULES

**COMMIT AFTER each of these events:**
- Single file completed
- Group of related files (max 3-4)
- Migration file(s) applied
- Test file written
- Bug fixed
- Phase complete
- Configuration change
- Dependency added

**NEVER batch in one commit:**
- Different modules
- Feature + tests (separate commits)
- Bug fix + new feature
- Multiple migrations serving different domains

---

## COMMIT MESSAGE EXAMPLES

### GOOD

```
core: implement Pydantic Settings with startup validation for all env vars

All required environment variables are now typed, validated, and
documented in a single Settings class using Pydantic BaseSettings.

The application will refuse to start if any required variable is
missing or has an invalid value, failing fast with a clear error
message rather than discovering missing config at runtime.

Signed-off-by: Abdullah-Khan-Niazi
```

```
fix: resolve order context pricing_snapshot not updating on item removal

Root cause: context_manager.remove_item_from_context() was setting
the item's cancelled flag correctly but not calling
_recalculate_pricing_snapshot() afterward.

Signed-off-by: Abdullah-Khan-Niazi
```

### BAD — never write these

```bash
git commit -m "fix bug"            # too vague
git commit -m "update code"        # too vague
git commit -m "added payment"      # past tense
git commit -m "payments: add ..."  # MISSING Signed-off-by!
```

---

## BRANCH STRATEGY

Use `main` branch only (solo developer). Frequent small commits serve the same
purpose as feature branches. For risky experiments: `git stash` and restore.

---

## PHASE COMPLETION COMMIT FORMAT

```
phase-N: <phase name> complete — <what was verified>

Phase N implementation is complete and verified. All components listed
in the phase plan have been implemented, tested, and committed.

What was built:
- <bullet 1>
- <bullet 2>

Verification:
- <how each component was tested>

Next phase: <brief description of what P(N+1) will build>

Signed-off-by: Abdullah-Khan-Niazi
```

---

## RECOVERING FROM MISTAKES

### Accidentally committed a secret:
```bash
# DO NOT push. Rotate the secret immediately. Then:
git reset HEAD~1  # Undo last commit, keep changes
# Remove secret from file
git add -p        # Stage carefully
git commit -m "security: remove accidentally staged credentials..."
```

### Amend last commit (before push only):
```bash
git add <files>
git commit --amend --no-edit
```

---

## PRE-COMMIT HOOKS

`.pre-commit-config.yaml` must run: `black` → `isort` → `flake8`
Never use `--no-verify` to skip hooks.
