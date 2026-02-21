---
applyTo: "**"
---

# SKILL 05 — SECURITY
## Source: `docs/skills/SKILL_security.md`

---

## SECRET MANAGEMENT — ZERO TOLERANCE

- All secrets in `.env` only — NEVER in source code
- `.env` is in `.gitignore` — verify before first commit
- `.env.example` has all variable names with descriptions but NO real values
- If a secret accidentally appears in a commit: **rotate it immediately**, then fix

---

## WEBHOOK SIGNATURE VERIFICATION

Every POST to `/api/webhook` must be verified before any processing:

```python
import hmac
import hashlib

def verify_meta_signature(
    payload_bytes: bytes,
    x_hub_signature_256: str,
    app_secret: str,
) -> bool:
    """Verify Meta's HMAC-SHA256 webhook signature."""
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, x_hub_signature_256)
```

Rules:
1. Read raw body bytes BEFORE parsing JSON
2. Verify with raw bytes (NOT parsed JSON)
3. If False: log warning, return HTTP 400
4. Only process if True

---

## SENSITIVE FIELD ENCRYPTION

CNIC and sensitive fields must be encrypted before DB write:

```python
from cryptography.fernet import Fernet
from app.core.config import get_settings

def encrypt_sensitive(value: str) -> str:
    """Encrypt using Fernet symmetric encryption."""
    return Fernet(get_settings().ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()

def decrypt_sensitive(encrypted_value: str) -> str:
    """Decrypt Fernet-encrypted value."""
    return Fernet(get_settings().ENCRYPTION_KEY.encode()).decrypt(encrypted_value.encode()).decode()
```

Generate key: `Fernet.generate_key().decode()` → store in `ENCRYPTION_KEY` env var.

---

## PII MASKING IN LOGS — MANDATORY

Phone numbers must NEVER appear as plaintext in any log:

```python
import re

def mask_pii(record: dict) -> bool:
    """Mask phone numbers in log messages — show only last 4 digits."""
    phone_pattern = re.compile(r'\+?\d{10,15}')
    def mask(match):
        num = match.group()
        return f"****{num[-4:]}"
    record["message"] = phone_pattern.sub(mask, record["message"])
    for key, value in record["extra"].items():
        if isinstance(value, str):
            record["extra"][key] = phone_pattern.sub(mask, value)
    return True
```

Install: `logger.add(sys.stderr, filter=mask_pii)`

---

## INPUT VALIDATION AND SANITIZATION

Length limits enforced at webhook handler, before any processing:
- WhatsApp message text: 2000 chars max
- Customer name, shop name: 255 chars max
- Address: 500 chars max
- Any free-text field: 2000 chars max

### Prompt injection sanitization

```python
INJECTION_PATTERNS = [
    "ignore previous instructions", "ignore all previous", "you are now",
    "new instructions:", "system:", "[system]", "{{", "}}", "```", "<|", "|>",
]

def sanitize_for_prompt(text: str, max_length: int = 1500) -> str:
    """Sanitize user input before AI prompt inclusion."""
    for pattern in INJECTION_PATTERNS:
        if pattern in text.lower():
            logger.warning("security.prompt_injection_attempt_detected", pattern=pattern)
            text = text.replace(pattern, "[filtered]")
    return text[:max_length]
```

---

## RATE LIMITING

Per-WhatsApp-number rate limiting to prevent abuse:
- Max 30 messages per minute per number
- If exceeded: log warning, send throttle message, drop excess requests
- Use in-memory counter (Redis if available, else LRU dict)

---

## STARTUP VALIDATION

`app/core/config.py` must validate ALL required secrets at startup.
Application must REFUSE to start if any required variable is missing.

```python
@model_validator(mode='after')
def validate_encryption_key(self) -> 'Settings':
    try:
        Fernet(self.ENCRYPTION_KEY.encode())
    except Exception:
        raise ValueError("ENCRYPTION_KEY is not a valid Fernet key.")
    return self
```
