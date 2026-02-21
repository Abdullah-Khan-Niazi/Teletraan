"""TELETRAAN security utilities.

Provides:
- Meta webhook HMAC-SHA256 signature verification.
- Fernet symmetric encryption for CNIC and other sensitive fields.
- Input sanitisation for AI prompt injection prevention.
- Secure token/reference generation.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from app.core.config import get_settings
from app.core.constants import MAX_FREE_TEXT_LENGTH, MAX_MESSAGE_LENGTH

# ── Prompt injection patterns ───────────────────────────────────────

_INJECTION_PATTERNS: list[str] = [
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
]


# ═══════════════════════════════════════════════════════════════════
# WEBHOOK SIGNATURE VERIFICATION
# ═══════════════════════════════════════════════════════════════════


def verify_meta_signature(
    payload_bytes: bytes,
    x_hub_signature_256: str | None,
    app_secret: str,
) -> bool:
    """Verify Meta's HMAC-SHA256 webhook signature.

    This MUST be called with the **raw request body bytes** before
    parsing JSON.  If verification fails the request must be rejected.

    Args:
        payload_bytes: Raw body bytes as received from Meta.
        x_hub_signature_256: Value of the ``X-Hub-Signature-256`` header.
        app_secret: Meta App Secret from environment.

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.
    """
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, x_hub_signature_256)


# ═══════════════════════════════════════════════════════════════════
# FERNET ENCRYPTION / DECRYPTION
# ═══════════════════════════════════════════════════════════════════


def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured ENCRYPTION_KEY."""
    return Fernet(get_settings().encryption_key.encode())


def encrypt_sensitive(value: str) -> str:
    """Encrypt a sensitive string (e.g. CNIC) using Fernet.

    Args:
        value: Plaintext string to encrypt.

    Returns:
        Base64-encoded ciphertext string safe for DB storage.
    """
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_sensitive(encrypted_value: str) -> str:
    """Decrypt a Fernet-encrypted string.

    Args:
        encrypted_value: Ciphertext produced by ``encrypt_sensitive``.

    Returns:
        Original plaintext string.

    Raises:
        app.core.exceptions.ValidationError: If decryption fails
            (corrupted data or wrong key).
    """
    try:
        return _get_fernet().decrypt(encrypted_value.encode()).decode()
    except InvalidToken as exc:
        # Import here to avoid circular import at module load
        from app.core.exceptions import ValidationError

        raise ValidationError(
            "Failed to decrypt sensitive field — data may be corrupted "
            "or ENCRYPTION_KEY was rotated.",
            operation="decrypt_sensitive",
        ) from exc


# ═══════════════════════════════════════════════════════════════════
# INPUT SANITISATION
# ═══════════════════════════════════════════════════════════════════


def sanitize_for_prompt(text: str, max_length: int = 1500) -> str:
    """Sanitise user input before inclusion in an AI prompt.

    Strips known prompt-injection patterns and truncates to
    ``max_length`` characters.

    Args:
        text: Raw user input string.
        max_length: Maximum character count for the sanitised output.

    Returns:
        Sanitised string safe for prompt inclusion.
    """
    sanitised = text
    lower = sanitised.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in lower:
            logger.warning(
                "security.prompt_injection_attempt_detected",
                pattern=pattern,
            )
            sanitised = sanitised.replace(pattern, "[filtered]")
            # Case-insensitive replacement
            sanitised = re.sub(
                re.escape(pattern), "[filtered]", sanitised, flags=re.IGNORECASE
            )
    return sanitised[:max_length]


def enforce_length_limit(
    text: str,
    max_length: int = MAX_MESSAGE_LENGTH,
    field_name: str = "input",
) -> str:
    """Enforce a character-length limit on free-text input.

    Args:
        text: The input string.
        max_length: Maximum allowed characters.
        field_name: Name of the field (for error context).

    Returns:
        The input string truncated to ``max_length``.

    Raises:
        app.core.exceptions.ValidationError: If truncation is not
            acceptable (caller decides).
    """
    if len(text) > max_length:
        logger.warning(
            "security.input_truncated",
            field=field_name,
            original_length=len(text),
            max_length=max_length,
        )
    return text[:max_length]


# ═══════════════════════════════════════════════════════════════════
# TOKEN / REFERENCE GENERATION
# ═══════════════════════════════════════════════════════════════════


def generate_order_number() -> str:
    """Generate a unique, human-readable order number.

    Format: ``TLN-YYMMDD-XXXXX`` where X is a random 5-digit alphanumeric.

    Returns:
        Order number string guaranteed unique by random suffix.
    """
    date_part = datetime.now(tz=timezone.utc).strftime("%y%m%d")
    random_part = secrets.token_hex(3).upper()[:5]
    return f"TLN-{date_part}-{random_part}"


def generate_ticket_number(prefix: str = "TKT") -> str:
    """Generate a unique support/complaint ticket number.

    Args:
        prefix: Ticket prefix (``TKT`` for complaints, ``SUP``
            for support tickets).

    Returns:
        Ticket number string, e.g. ``TKT-26022-A3F1B``.
    """
    date_part = datetime.now(tz=timezone.utc).strftime("%y%m%d")
    random_part = secrets.token_hex(3).upper()[:5]
    return f"{prefix}-{date_part}-{random_part}"


def generate_transaction_reference() -> str:
    """Generate a unique payment transaction reference.

    Returns:
        Reference string, e.g. ``PAY-260222-1A2B3C4D``.
    """
    date_part = datetime.now(tz=timezone.utc).strftime("%y%m%d")
    random_part = secrets.token_hex(4).upper()
    return f"PAY-{date_part}-{random_part}"


def generate_idempotency_key(*parts: str) -> str:
    """Generate a deterministic idempotency key from parts.

    Args:
        parts: String components that together identify a unique
            operation (e.g. distributor_id, recipient, message_type,
            date).

    Returns:
        SHA-256 hex digest of the concatenated parts.
    """
    combined = ":".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def mask_phone(number: str) -> str:
    """Return a PII-safe representation of a phone number.

    Only the last 4 digits are preserved; everything else is masked.

    Args:
        number: Full phone number string (any format).

    Returns:
        Masked string, e.g. ``****7890``.
    """
    digits_only = re.sub(r"\D", "", number)
    if len(digits_only) < 4:
        return "****"
    return f"****{digits_only[-4:]}"
