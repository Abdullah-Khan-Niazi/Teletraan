"""TELETRAAN custom exception hierarchy.

Every exception raised in the application must descend from
``TeletraanBaseException`` so that the global FastAPI handler and
logging infrastructure can handle it uniformly.

Hierarchy::

    TeletraanBaseException
    ├── DatabaseError
    ├── WhatsAppAPIError
    │   └── WhatsAppRateLimitError
    ├── AIProviderError
    │   ├── AITranscriptionError
    │   └── AICompletionError
    ├── PaymentGatewayError
    │   └── PaymentSignatureError
    ├── RateLimitError
    ├── ValidationError
    ├── SessionError
    │   └── StateTransitionError
    ├── OrderContextError
    │   └── OrderContextConflictError
    ├── ConfigurationError
    └── NotFoundError
"""

from __future__ import annotations


# ── Base ────────────────────────────────────────────────────────────


class TeletraanBaseException(Exception):
    """Root exception for all TELETRAAN application errors.

    Args:
        message: Human-readable error description.
        operation: The operation that triggered the failure (optional).
        details: Arbitrary extra context for structured logging.
    """

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        *,
        operation: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.operation = operation
        self.details = details or {}
        super().__init__(self.message)


# ── Database ────────────────────────────────────────────────────────


class DatabaseError(TeletraanBaseException):
    """Raised on any Supabase / PostgreSQL failure after retries."""


class NotFoundError(TeletraanBaseException):
    """Raised when a requested entity does not exist in the database."""


# ── WhatsApp ────────────────────────────────────────────────────────


class WhatsAppAPIError(TeletraanBaseException):
    """Raised when the Meta Cloud API call fails."""


class WhatsAppRateLimitError(WhatsAppAPIError):
    """Raised when Meta returns HTTP 429 — rate limit exceeded."""


# ── AI Providers ────────────────────────────────────────────────────


class AIProviderError(TeletraanBaseException):
    """Raised when the active AI provider returns an error."""


class AITranscriptionError(AIProviderError):
    """Raised when speech-to-text transcription fails."""


class AICompletionError(AIProviderError):
    """Raised when text/chat completion fails."""


# ── Payments ────────────────────────────────────────────────────────


class PaymentGatewayError(TeletraanBaseException):
    """Raised when a payment gateway operation fails."""


class PaymentSignatureError(PaymentGatewayError):
    """Raised when a payment webhook signature verification fails."""


# ── Rate Limiting ───────────────────────────────────────────────────


class RateLimitError(TeletraanBaseException):
    """Raised when a per-number or per-distributor rate limit is hit."""


# ── Validation ──────────────────────────────────────────────────────


class ValidationError(TeletraanBaseException):
    """Raised when application-level input validation fails.

    Distinct from Pydantic's ``ValidationError`` — this is for
    business-rule validation that occurs after schema validation.
    """


# ── Sessions ────────────────────────────────────────────────────────


class SessionError(TeletraanBaseException):
    """Raised on session management failures."""


class StateTransitionError(SessionError):
    """Raised when an FSM state transition is illegal."""


# ── Order Context ───────────────────────────────────────────────────


class OrderContextError(TeletraanBaseException):
    """Raised when order context read/write/validate fails."""


class OrderContextConflictError(OrderContextError):
    """Raised on a conflicting concurrent modification of order context."""


# ── Configuration ───────────────────────────────────────────────────


class ConfigurationError(TeletraanBaseException):
    """Raised when a required configuration value is missing or invalid."""
