# TELETRAAN Final Verification Checklist — 27 Items

Run through every item before the final commit. "It should work" is not evidence.
Each item must be **verified** — check DB state, run tests, review logs, test manually.

---

## Code Quality
- [ ] Zero TODOs, FIXMEs, stubs in any Python file
- [ ] Pre-commit hooks pass on all files (`black`, `isort`, `flake8`)
- [ ] All commits in Linus style, all ending `Signed-off-by: Abdullah-Khan-Niazi`
- [ ] No hardcoded secrets anywhere in codebase
- [ ] `pytest` runs with 80%+ coverage on core modules

## Database
- [ ] All 27 SQL migrations applied and verified in Supabase
- [ ] RLS policies active on all tenant tables
- [ ] All indexes from `026_create_indexes.sql` confirmed present

## AI Providers
- [ ] `ACTIVE_AI_PROVIDER` can be switched to any of 5 providers via env — verified with tests
- [ ] `ACTIVE_STT_PROVIDER` switches correctly between gemini and whisper
- [ ] AI fallback chain works: primary fails → fallback tried → if both fail → rule-based response

## Payment Gateways
- [ ] `ACTIVE_PAYMENT_GATEWAY` can be switched to any of 5 gateways via env — verified with tests
- [ ] All 5 gateways implemented: jazzcash, easypaisa, safepay, nayapay, bank_transfer + dummy
- [ ] SafePay checkout URL generation and HMAC webhook verified
- [ ] NayaPay payment initiation and webhook verified
- [ ] Bank transfer flow: screenshot received, owner notified, manual confirm triggers extension
- [ ] Dummy gateway auto-confirms after delay, fails on 99-paisa amounts, **blocked in production**

## Order Flow
- [ ] Order context fully persists in `sessions.pending_order_draft` — process restart mid-order recovers seamlessly
- [ ] All order context fields per `07_order_context_schema.prompt.md` stored and retrievable
- [ ] All Channel A flows tested: onboarding, order, voice, complaint, profile, language switch, quick reorder, credit check
- [ ] Session survives process restart — conversation resumes from exact state

## Distributor Management
- [ ] Reminder sequence fires at 7d, 3d, 1d, expiry — no duplicates (idempotency keys verified)
- [ ] Channel B: prospect → payment → distributor created → onboarding sequence complete

## Scheduler and Operations
- [ ] All scheduler jobs registered, executing, and error-handling correctly
- [ ] Analytics events being written to `analytics_events` table

## Security
- [ ] Rate limiter blocks at 30 msg/min and sends single warning — no further processing
- [ ] Admin API `X-Admin-Key` protected — unauthorized requests rejected with 401
- [ ] CNIC encrypted before DB write — decrypted correctly on read
- [ ] Phone numbers show last-4-digits-only in all logs — verified in log output

## Deployment
- [ ] All `docs/` files complete and accurate
- [ ] Render deployment live, `/health` check green, all scheduler jobs active in logs
- [ ] Production smoke test passed — all flows verified on live deployment
