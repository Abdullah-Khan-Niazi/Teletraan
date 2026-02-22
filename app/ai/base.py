"""Abstract AI provider base class and response models.

All provider implementations (Gemini, OpenAI, Anthropic, Cohere,
OpenRouter) inherit from ``AIProvider`` and implement every abstract
method.  Response models are Pydantic v2 ``BaseModel`` instances so
callers never touch raw provider dicts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════


class AITextResponse(BaseModel):
    """Normalised response from any text-generation call.

    Attributes:
        content: Generated text content.
        tokens_used_input: Prompt/input tokens consumed.
        tokens_used_output: Completion/output tokens consumed.
        finish_reason: Why generation stopped (stop, max_tokens, error).
        raw_response: Full provider response dict for debugging.
        estimated_cost_paisas: Estimated cost in paisas (1 PKR = 100 paisas).
    """

    content: str
    tokens_used_input: int = 0
    tokens_used_output: int = 0
    finish_reason: str = "stop"
    raw_response: dict = Field(default_factory=dict)
    estimated_cost_paisas: int = 0


class AITranscriptionResponse(BaseModel):
    """Normalised response from any speech-to-text call.

    Attributes:
        text: Transcribed text.
        confidence: Confidence bucket — high / medium / low.
        language_detected: ISO 639-1 language code detected.
        duration_seconds: Audio duration in seconds.
        raw_response: Full provider response dict for debugging.
    """

    text: str
    confidence: str = "medium"
    language_detected: str = "ur"
    duration_seconds: float = 0.0
    raw_response: dict = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# ABSTRACT BASE CLASS
# ═══════════════════════════════════════════════════════════════════


class AIProvider(ABC):
    """Contract that every TELETRAAN AI provider must fulfil.

    Providers must:
    * Catch provider-specific exceptions and re-raise as
      ``AIProviderError`` / ``AICompletionError`` / ``AITranscriptionError``.
    * Return normalised response models.
    * Log usage to ``analytics_events`` via the caller (factory/NLU).
    """

    # ── Text Generation ─────────────────────────────────────────────

    @abstractmethod
    async def generate_text(
        self,
        system_prompt: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        *,
        use_premium_model: bool = False,
    ) -> AITextResponse:
        """Generate a text completion.

        Args:
            system_prompt: System-level instruction (English).
            messages: Conversation history ``[{"role": "user"|"assistant", "content": "..."}]``.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens in the completion.
            use_premium_model: Use the premium/expensive model variant.

        Returns:
            Normalised AITextResponse.

        Raises:
            AICompletionError: On any provider failure.
        """

    # ── Speech-to-Text ──────────────────────────────────────────────

    @abstractmethod
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str = "ur",
    ) -> AITranscriptionResponse:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data.
            mime_type: MIME type of the audio (e.g. ``audio/wav``).
            language_hint: ISO 639-1 hint for the expected language.

        Returns:
            Normalised AITranscriptionResponse.

        Raises:
            AITranscriptionError: On any provider failure.
        """

    # ── Cost Estimation ─────────────────────────────────────────────

    @abstractmethod
    def estimate_cost(self, tokens_in: int, tokens_out: int) -> int:
        """Estimate the cost of a call in paisas.

        Args:
            tokens_in: Input/prompt tokens.
            tokens_out: Output/completion tokens.

        Returns:
            Estimated cost in paisas.
        """

    # ── Metadata ────────────────────────────────────────────────────

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the canonical provider identifier (e.g. ``gemini``)."""

    @abstractmethod
    def get_model_name(self, premium: bool = False) -> str:
        """Return the model identifier currently in use.

        Args:
            premium: If True, return the premium model name.
        """

    # ── Health ──────────────────────────────────────────────────────

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is responsive.

        Must not raise — returns False on failure.
        """
