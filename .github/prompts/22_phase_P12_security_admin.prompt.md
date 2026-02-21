# Phase 12 — Security, Rate Limiting, Admin API

**Prerequisites:** Phase 11 complete and verified.
**Verify before P13:** All security tests passing; admin API authenticated correctly; rate limiting blocks at threshold.

## Steps (execute in order, commit after each)

1. Integrate per-number rate limiting into `app/channels/router.py`  
   Limit: 30 messages/minute per number. If exceeded: log warning, send single throttle message, drop excess.  
   Use `rate_limits` table for persistence (Redis if available, else in-memory LRU + DB sync)  
   → Commit: `"security: integrate per-number rate limiting in message router"`

2. Implement `app/api/admin.py` — protected admin API (X-Admin-Key header)  
   Endpoints: distributor management (create, suspend, unsuspend, extend), system status,  
   gateway health, AI provider health, force inventory sync, send announcement  
   → Commit: `"api: implement protected admin API with full distributor and system management endpoints"`

3. Verify Fernet encryption on all CNIC writes — audit every distributor model write path  
   Check `distributor_repo.py` → all writes go through `security.encrypt_sensitive()`  
   Check `distributor_repo.py` → all reads go through `security.decrypt_sensitive()`  
   → Commit: `"security: verify Fernet encryption applied on all CNIC writes and reads"`

4. Full security audit pass:  
   - All endpoints: verify authentication/authorization  
   - All inputs: verify length limits and sanitization  
   - All logs: verify no PII leaks (phone numbers show last 4 digits only)  
   - All webhook handlers: verify HMAC before any processing  
   - Prompt injection patterns stripped from all user text before AI prompts  
   → Commit: `"security: complete security audit pass, all PII masked, all inputs validated"`

5. Write security unit tests:  
   - HMAC rejection (invalid signature returns 400, valid processes)  
   - Rate limiting (31st message blocked, warning sent, 32nd dropped silently)  
   - Input validation (2001-char message rejected, prompt injection patterns filtered)  
   - CNIC encrypt/decrypt round-trip  
   - Admin endpoint rejects without X-Admin-Key  
   → Commit: `"tests: add security tests for HMAC rejection, rate limiting, input validation"`

6. **PHASE 12 COMPLETE** Commit: `"phase-12: security hardening, rate limiting, and admin API complete"`
