"""Pydantic Settings for TELETRAAN — all environment variables typed and validated.

Application refuses to start if any required variable is missing or has
an invalid value.  Access settings anywhere via ``get_settings()``.
"""

from __future__ import annotations

import functools
from typing import Optional

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated, and documented application settings.

    Reads from environment variables and ``.env`` file.  Every required
    secret must be present at startup — there is no lazy resolution.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────────────
    app_env: str = Field(
        default="development",
        pattern=r"^(development|staging|production)$",
        description="Runtime environment.",
    )
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_secret_key: str = Field(
        ...,
        min_length=32,
        description="64-char random string for internal signing.",
    )
    log_level: str = Field(
        default="DEBUG",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    encryption_key: str = Field(
        ...,
        description="Fernet key for CNIC/sensitive field encryption.",
    )
    admin_api_key: str = Field(
        ...,
        min_length=16,
        description="X-Admin-Key header value for admin endpoints.",
    )

    # ── Meta WhatsApp API ───────────────────────────────────────────
    meta_app_id: str = Field(..., description="Meta App ID.")
    meta_app_secret: str = Field(..., description="Meta App Secret.")
    meta_verify_token: str = Field(
        ..., description="Webhook verification token (you define this)."
    )
    meta_access_token: str = Field(
        ..., description="Meta permanent access token for WhatsApp Cloud API."
    )
    meta_api_version: str = Field(default="v19.0")
    meta_api_base_url: str = Field(default="https://graph.facebook.com")
    owner_phone_number_id: str = Field(
        ..., description="Meta Phone Number ID for Channel B owner SIM."
    )
    owner_whatsapp_number: str = Field(
        ..., description="E.164 owner number."
    )

    # ── AI Providers ────────────────────────────────────────────────
    active_ai_provider: str = Field(
        default="gemini",
        pattern=r"^(gemini|openai|anthropic|cohere|openrouter)$",
    )
    active_stt_provider: Optional[str] = Field(
        default=None,
        pattern=r"^(gemini|whisper)$",
        description="Defaults to active_ai_provider if compatible.",
    )
    ai_text_model: Optional[str] = Field(
        default=None, description="Override default model for chosen provider."
    )
    ai_premium_model: Optional[str] = Field(
        default=None, description="Premium model for complex reasoning."
    )
    ai_max_tokens: int = Field(default=2048, ge=256, le=32768)
    ai_temperature: float = Field(default=0.30, ge=0.0, le=2.0)
    ai_fallback_provider: Optional[str] = Field(
        default=None,
        pattern=r"^(gemini|openai|anthropic|cohere|openrouter)$",
    )
    gemini_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    cohere_api_key: Optional[str] = Field(default=None)
    openrouter_api_key: Optional[str] = Field(default=None)
    openrouter_model: Optional[str] = Field(default=None)

    # ── Supabase ────────────────────────────────────────────────────
    supabase_url: str = Field(..., description="Supabase project URL.")
    supabase_service_key: str = Field(
        ..., description="Service role key — full access."
    )
    supabase_anon_key: Optional[str] = Field(default=None)

    # ── Payment Gateways ────────────────────────────────────────────
    active_payment_gateway: str = Field(
        default="dummy",
        pattern=r"^(jazzcash|easypaisa|safepay|nayapay|bank_transfer|dummy)$",
    )
    payment_callback_base_url: Optional[str] = Field(
        default=None, description="Public HTTPS URL for gateway callbacks."
    )
    payment_link_expiry_minutes: int = Field(default=60, ge=5, le=1440)

    # JazzCash
    jazzcash_merchant_id: Optional[str] = Field(default=None)
    jazzcash_password: Optional[str] = Field(default=None)
    jazzcash_integrity_salt: Optional[str] = Field(default=None)
    jazzcash_api_url: Optional[str] = Field(default=None)

    # EasyPaisa
    easypaisa_store_id: Optional[str] = Field(default=None)
    easypaisa_hash_key: Optional[str] = Field(default=None)
    easypaisa_api_url: Optional[str] = Field(default=None)

    # SafePay
    safepay_api_key: Optional[str] = Field(default=None)
    safepay_secret_key: Optional[str] = Field(default=None)
    safepay_api_url: str = Field(default="https://api.getsafepay.com")
    safepay_webhook_secret: Optional[str] = Field(default=None)

    # NayaPay
    nayapay_merchant_id: Optional[str] = Field(default=None)
    nayapay_api_key: Optional[str] = Field(default=None)
    nayapay_secret: Optional[str] = Field(default=None)
    nayapay_api_url: Optional[str] = Field(default=None)

    # Bank Transfer
    bank_account_name: Optional[str] = Field(default=None)
    bank_account_number: Optional[str] = Field(default=None)
    bank_iban: Optional[str] = Field(default=None)
    bank_name: Optional[str] = Field(default=None)
    bank_branch: Optional[str] = Field(default=None)

    # Dummy Gateway (dev only)
    dummy_gateway_auto_confirm: bool = Field(default=True)
    dummy_gateway_confirm_delay_seconds: int = Field(default=10, ge=0, le=300)

    # ── Scheduler ───────────────────────────────────────────────────
    scheduler_timezone: str = Field(default="Asia/Karachi")
    inventory_sync_interval_minutes: int = Field(default=120, ge=5)
    session_cleanup_interval_hours: int = Field(default=6, ge=1)
    reminder_check_interval_hours: int = Field(default=12, ge=1)

    # ── Feature Flags ───────────────────────────────────────────────
    enable_voice_processing: bool = Field(default=True)
    enable_inventory_sync: bool = Field(default=True)
    enable_excel_reports: bool = Field(default=True)
    enable_pdf_catalog: bool = Field(default=True)
    enable_channel_b: bool = Field(default=True)
    enable_analytics: bool = Field(default=True)
    enable_credit_accounts: bool = Field(default=False)

    # ── Email ───────────────────────────────────────────────────────
    resend_api_key: Optional[str] = Field(default=None)
    email_from_address: str = Field(default="noreply@teletraan.pk")

    # ── Validators ──────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_encryption_key(self) -> Settings:
        """Ensure ENCRYPTION_KEY is a valid Fernet key."""
        try:
            Fernet(self.encryption_key.encode())
        except Exception as exc:
            raise ValueError(
                "ENCRYPTION_KEY is not a valid Fernet key. "
                "Generate one with: python -c "
                "\"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from exc
        return self

    @model_validator(mode="after")
    def validate_active_provider_key(self) -> Settings:
        """Ensure the API key for the active AI provider is set."""
        provider_key_map: dict[str, str] = {
            "gemini": "gemini_api_key",
            "openai": "openai_api_key",
            "anthropic": "anthropic_api_key",
            "cohere": "cohere_api_key",
            "openrouter": "openrouter_api_key",
        }
        key_field = provider_key_map.get(self.active_ai_provider)
        if key_field and not getattr(self, key_field):
            raise ValueError(
                f"ACTIVE_AI_PROVIDER is '{self.active_ai_provider}' but "
                f"{key_field.upper()} is not set."
            )
        return self

    @model_validator(mode="after")
    def validate_dummy_gateway_blocked_in_production(self) -> Settings:
        """Block dummy gateway in production."""
        if (
            self.app_env == "production"
            and self.active_payment_gateway == "dummy"
        ):
            raise ValueError(
                "Dummy payment gateway is not allowed in production. "
                "Set ACTIVE_PAYMENT_GATEWAY to a real gateway."
            )
        return self

    @property
    def is_production(self) -> bool:
        """Return True if running in production."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Return True if running in development."""
        return self.app_env == "development"

    @property
    def effective_stt_provider(self) -> str:
        """Resolve the effective STT provider.

        Falls back to ACTIVE_AI_PROVIDER if it supports audio natively.
        """
        if self.active_stt_provider:
            return self.active_stt_provider
        if self.active_ai_provider == "gemini":
            return "gemini"
        return "whisper"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton.

    Returns:
        Validated Settings instance.

    Raises:
        pydantic.ValidationError: If required env vars are missing
            or have invalid values — application refuses to start.
    """
    return Settings()  # type: ignore[call-arg]
