# SECURITY SKILL
## SKILL: security | Version: 1.0 | Priority: CRITICAL

---

## PURPOSE

This skill defines all security implementation requirements for TELETRAAN.
Security is not optional and not deferred. Every item in this document
must be implemented from the start.

---

## SECRET MANAGEMENT

### Rule: Zero secrets in code — ever
- All secrets in `.env` only
- `.env` in `.gitignore` — verified before first commit
- `.env.example` has all variable names with descriptions but NO real values
- If a secret accidentally appears in a commit: rotate it immediately, then fix

### Encryption key setup
```python
# Generate Fernet key (run once, store result in ENCRYPTION_KEY env var):
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### Startup validation
`app/core/config.py` Pydantic Settings must validate all required secrets at startup.
If any required variable is missing: raise `ValueError` with clear message.
Application must REFUSE to start with missing critical config.

```python
@model_validator(mode='after')
def validate_encryption_key(self) -> 'Settings':
    try:
        Fernet(self.ENCRYPTION_KEY.encode())
    except Exception:
        raise ValueError("ENCRYPTION_KEY is not a valid Fernet key. Generate with Fernet.generate_key()")
    return self
```

---

## WHATSAPP WEBHOOK VERIFICATION

Every POST to `/api/webhook` must be verified before any processing.

```python
import hmac
import hashlib

def verify_meta_signature(
    payload_bytes: bytes,
    x_hub_signature_256: str,
    app_secret: str,
) -> bool:
    """Verify Meta's HMAC-SHA256 webhook signature.

    Meta sends: X-Hub-Signature-256: sha256=<hex_digest>
    We verify by computing HMAC-SHA256(payload, APP_SECRET).
    """
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    # Use compare_digest to prevent timing attacks
    return hmac.compare_digest(expected, x_hub_signature_256)
```

Webhook handler must:
1. Read raw body bytes BEFORE parsing JSON
2. Call `verify_meta_signature()` with raw bytes and `X-Hub-Signature-256` header
3. If False: log warning, return HTTP 400 (not 401 — avoid auth info leakage)
4. Only if True: parse JSON and process

DO NOT use the parsed JSON for signature verification — use raw bytes.

---

## SENSITIVE FIELD ENCRYPTION

CNIC and any other sensitive fields must be encrypted before DB write
and decrypted on read. Never store plaintext sensitive data.

```python
# In app/core/security.py:
from cryptography.fernet import Fernet
from app.core.config import get_settings

def encrypt_sensitive(value: str) -> str:
    """Encrypt sensitive string value using Fernet symmetric encryption."""
    fernet = Fernet(get_settings().ENCRYPTION_KEY.encode())
    return fernet.encrypt(value.encode()).decode()

def decrypt_sensitive(encrypted_value: str) -> str:
    """Decrypt Fernet-encrypted sensitive string value."""
    fernet = Fernet(get_settings().ENCRYPTION_KEY.encode())
    return fernet.decrypt(encrypted_value.encode()).decode()
```

Usage in repositories:
- `distributor_repo.create()`: encrypt CNIC before insert
- `distributor_repo.get_by_id()`: decrypt CNIC after fetch
- CNIC never appears as plaintext in logs or API responses

---

## PII MASKING IN LOGS

Loguru filter must mask phone numbers in all log output:

```python
import re

def pii_masking_filter(record: dict) -> bool:
    """Mask phone numbers in log messages and extra fields."""
    # Mask phone numbers: keep only last 4 digits
    phone_pattern = re.compile(r'\+?\d{10,15}')

    def mask_number(match):
        num = match.group()
        return f"****{num[-4:]}"

    record["message"] = phone_pattern.sub(mask_number, record["message"])

    # Also mask in extra dict values
    for key, value in record["extra"].items():
        if isinstance(value, str):
            record["extra"][key] = phone_pattern.sub(mask_number, value)

    return True  # Always allow record through after masking
```

Install with: `logger.add(sys.stderr, filter=pii_masking_filter)`

---

## INPUT VALIDATION AND SANITIZATION

### Length limits (enforced in webhook handler before any processing):
- WhatsApp message text: max 4096 chars (WhatsApp limit, enforce at 2000 for safety)
- Customer name: max 255 chars
- Shop name: max 255 chars
- Address: max 500 chars
- Any free-text field: max 2000 chars

```python
def validate_message_length(text: str, max_length: int = 2000) -> str:
    """Truncate and flag oversized messages."""
    if len(text) > max_length:
        logger.warning("message.truncated", original_length=len(text))
        return text[:max_length]
    return text
```

### Prompt injection sanitization
Before any user content is included in AI prompts:

```python
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "new instructions:",
    "system:",
    "[system]",
    "{{",
    "}}",
    "```",
    "<|",
    "|>",
    "assistant:",
    "human:",
]

def sanitize_for_prompt(text: str, max_length: int = 1500) -> str:
    """Sanitize user input before AI prompt inclusion."""
    cleaned = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in cleaned:
            logger.warning(
                "security.prompt_injection_attempt_detected",
                pattern=pattern,
            )
            text = text.replace(pattern, "[filtered]")
            text = text.replace(pattern.title(), "[filtered]")
            text = text.replace(pattern.upper(), "[filtered]")
    return text[:max_length]
```

---

## RATE LIMITING

### Limits per WhatsApp number per distributor (per configurable window):
- Messages: 10 per 60-second window
- Voice messages: 5 per 10-minute window
- AI calls: 30 per 60-minute window

### Implementation (app/core/security.py):
```
check_rate_limit(
    distributor_id: str,
    whatsapp_number: str,
    limit_type: str,  # "message", "voice", "ai_call"
    rate_limit_repo: RateLimitRepository,
) → bool  # True = allowed, False = throttled
```

Logic:
1. Get current window record from rate_limits table
2. If no record: create one with count=1, return True
3. If count >= limit for this type: set is_throttled=True, return False
4. Else: increment count, return True

Window boundaries:
- message: 60-second window (window_start = truncate(now, second=0))
- voice: 10-minute window
- ai_call: 60-minute window

### Response when throttled:
- Send single polite throttle message (in customer's language)
- After that: silently ignore until window resets
- Log throttle event to analytics_events

---

## ADMIN API PROTECTION

All endpoints under `/api/admin/` require:
```python
async def verify_admin_key(x_admin_key: str = Header(...)) -> bool:
    """FastAPI dependency for admin endpoint protection."""
    if not hmac.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True
```

Use `Depends(verify_admin_key)` on all admin routes.
Do NOT use HTTP Basic Auth — API key header is sufficient here.
Log all admin API calls to audit_log.

---

## PAYMENT SIGNATURE VERIFICATION

Every payment gateway callback endpoint must:
1. Read raw body bytes before any parsing
2. Call `gateway.verify_webhook_signature(body_bytes, headers)`
3. If False: log with full context, return HTTP 400
4. Track failure count: 3 failures in 10 minutes from same IP = alert owner

```python
# Failure tracking in rate_limits or a separate payment_security table
async def track_signature_failure(gateway: str, ip: str) -> None:
    """Track signature verification failures for suspicious activity detection."""
    # Increment counter in DB
    # If count >= 3 in 10 minutes: notify owner via WhatsApp
```

---

## AUDIT LOG POLICY

The `audit_log` table is APPEND-ONLY. No updates, no deletes.
RLS policy in Supabase: INSERT allowed, SELECT allowed, UPDATE denied, DELETE denied.

Every state-changing operation must log:
- Order created, modified, cancelled, confirmed
- Customer created, blocked, unblocked
- Distributor subscription changed
- Payment confirmed, failed
- Support ticket created, resolved
- Admin API call executed

Audit log entries must include:
- Who did it (actor_type + actor_id or whatsapp_masked)
- What changed (action string + entity_type + entity_id)
- Before state and after state (as JSONB)
- When (created_at — server-side, not client-provided)

---

## HTTPS AND TRANSPORT SECURITY

Enforced by Render/Railway — HTTPS is automatically handled by the platform.
Your app listens on HTTP internally (port 8000). Platform terminates TLS.
Never disable HTTPS on the platform.

In FastAPI, add these security headers via middleware:
```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
```

---

## DEPENDENCY SECURITY

Pin ALL dependencies in requirements.txt with exact versions.
Run `pip-audit` periodically to check for known vulnerabilities.
Never use `latest` in requirements — always specify version.

---

## SECURITY CHECKLIST (verify before deployment)

- [ ] .env not in git history (check with `git log --all -- .env`)
- [ ] All API keys from environment (grep codebase for hardcoded key patterns)
- [ ] Meta webhook HMAC verified on every POST
- [ ] Payment gateway signatures verified on every callback
- [ ] CNIC encrypted before DB write (check distributor_repo.create)
- [ ] Phone numbers last-4-only in all log lines (tail the logs)
- [ ] Rate limiting active (test by sending 11 messages in 60 seconds)
- [ ] Admin API returns 403 without correct key
- [ ] Prompt injection sanitization active (test with "ignore previous instructions")
- [ ] All inputs length-capped
- [ ] Dummy gateway blocked in production (set APP_ENV=production, try to use dummy)
- [ ] audit_log has no UPDATE or DELETE permissions (verify in Supabase RLS)
