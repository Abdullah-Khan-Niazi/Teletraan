# TELETRAAN Git Protocol — Mandatory Commit Standard

## Setup (Phase 1 — first commands)

```bash
git init                                       # first command
# Create .gitignore — commit it alone
git config user.name "Abdullah-Khan-Niazi"   # set name
git config user.email "abdullahniazi078@gmail.com"
# Initial commit: .gitignore + .env.example + README skeleton only
```

## Commit Frequency Rules

- Commit after every completed file or tightly related group (max 3-4 files)
- Commit after every migration file or related migration group
- Commit at the end of every phase — a "phase complete" commit
- Commit after every test file written
- Commit after fixing any bug discovered during testing
- Never let more than one logical feature accumulate without committing
- If a file is modified, commit the modification separately from additions

## Commit Message Format

```
<scope>: <imperative summary, max 72 chars>

<body — WHY this change, WHAT problem solved>
<wrap at 72 chars per line>
<explain non-obvious decisions>

Signed-off-by: Abdullah-Khan-Niazi
```

**All commits MUST end with `Signed-off-by: Abdullah-Khan-Niazi`. Missing = invalid commit.**

## Valid Scopes

`project` `core` `db` `api` `whatsapp` `ai` `channels` `channel-a` `channel-b`
`payments` `inventory` `orders` `reporting` `scheduler` `notifications` `analytics`
`distributor-mgmt` `security` `tests` `docs` `scripts` `deploy` `fix` `refactor`
`ci` `build` `config`

## Good Commit Examples

```
payments: add abstract PaymentGateway base class with full interface

Define the contract all payment gateway implementations must satisfy.
The base class enforces: generate_payment_link(), verify_webhook_signature(),
process_callback(), and get_payment_status() as abstract methods.

This ensures any future gateway (SafePay, NayaPay, bank, etc.) can be
plugged in without touching any business logic — only the factory needs
updating. All gateways now speak a common interface.

Signed-off-by: Abdullah-Khan-Niazi
```

```
sessions: implement full order context persistence in pending_order_draft

Order context is now fully serialized to JSONB on every state transition.
Includes: items list with catalog snapshots, quantities, unit prices,
discount requests, out-of-stock flags, unlisted item flags, voice
transcription source markers, conversation step tracking, and
ambiguity resolution state.

Process restart no longer loses in-progress orders. Customer continues
from exact state without re-entering any information already provided.

Signed-off-by: Abdullah-Khan-Niazi
```

```
ai: implement multi-provider factory with runtime provider switching

The AI factory now reads ACTIVE_AI_PROVIDER from environment and returns
the correct provider instance without any code changes needed.

Supported providers: gemini (text+audio), openai (gpt+whisper),
anthropic (claude), cohere. Each implements the AIProvider abstract
base class with identical interface signatures.

Provider-specific error codes are normalized to TeletraanAIError
so all callers handle failures identically regardless of provider.

Signed-off-by: Abdullah-Khan-Niazi
```

## Phase Completion Commit Format

```
phase-N: <phase name> complete — <what was verified>

Phase N implementation is complete and verified. All components listed
in the phase plan have been implemented, tested, and committed.

What was built:
- <bullet 1>
- <bullet 2>

Verification:
- <how each component was tested>

Next phase: <brief description>

Signed-off-by: Abdullah-Khan-Niazi
```

## Bad Commits — Never Write These

```bash
git commit -m "fix bug"            # too vague
git commit -m "update code"        # too vague
git commit -m "added payment"      # past tense
git commit -m "payments: add ..."  # MISSING Signed-off-by!
```

## Recovery

**Accidentally committed a secret:**

```bash
# DO NOT push. Rotate the secret immediately. Then:
git reset HEAD~1    # undo last commit, keep changes
# Remove secret from file
git add -p          # stage carefully
git commit          # re-commit without secret
```
