"""Anthropic Claude AI provider — text generation with Whisper STT fallback.

Uses the ``anthropic`` Python SDK (async client).  Claude 3 Haiku is
the default model, Claude 3.5 Sonnet is the premium variant.  Anthropic
does not have a native STT endpoint, so ``transcribe_audio`` routes to
OpenAI Whisper via the OpenAI provider.
"""

from __future__ import annotations

import time

from loguru import logger

from app.ai.base import AIProvider, AITextResponse, AITranscriptionResponse
from app.core.config import get_settings
from app.core.exceptions import AICompletionError, AITranscriptionError


class AnthropicProvider(AIProvider):
    """Anthropic Claude implementation of the TELETRAAN AIProvider contract."""

    DEFAULT_MODEL = "claude-3-haiku-20240307"
    PREMIUM_MODEL = "claude-3-5-sonnet-20241022"

    # Cost per 1M tokens in paisas (approx at PKR 280/USD)
    # Haiku:  $0.25/1M in, $1.25/1M out  ≈ 70/350 paisas
    # Sonnet: $3.00/1M in, $15.00/1M out ≈ 840/4200 paisas
    _COST_PER_M_INPUT_HAIKU = 70
    _COST_PER_M_OUTPUT_HAIKU = 350
    _COST_PER_M_INPUT_SONNET = 840
    _COST_PER_M_OUTPUT_SONNET = 4200

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.anthropic_api_key or ""
        self._openai_key: str = settings.openai_api_key or ""
        self._text_model: str = settings.ai_text_model or self.DEFAULT_MODEL
        self._premium_model: str = settings.ai_premium_model or self.PREMIUM_MODEL

    def _get_async_client(self):
        """Return a new AsyncAnthropic client (import deferred)."""
        from anthropic import AsyncAnthropic  # noqa: WPS433

        return AsyncAnthropic(api_key=self._api_key)

    # ── Text Generation ─────────────────────────────────────────────

    async def generate_text(
        self,
        system_prompt: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        *,
        use_premium_model: bool = False,
    ) -> AITextResponse:
        """Generate text using Anthropic Claude messages API.

        Args:
            system_prompt: System-level instruction.
            messages: Conversation history.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            use_premium_model: Use Sonnet instead of Haiku.

        Returns:
            Normalised AITextResponse.

        Raises:
            AICompletionError: On any Anthropic API failure.
        """
        try:
            client = self._get_async_client()
            model_name = self._premium_model if use_premium_model else self._text_model

            # Anthropic expects messages without system role — it goes separately
            api_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                if role == "system":
                    continue  # system prompt passed separately
                api_messages.append({
                    "role": role,
                    "content": msg["content"],
                })

            # Ensure at least one user message
            if not api_messages:
                api_messages.append({"role": "user", "content": "Hello"})

            start = time.monotonic()
            response = await client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=api_messages,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            tokens_in = getattr(response.usage, "input_tokens", 0) or 0
            tokens_out = getattr(response.usage, "output_tokens", 0) or 0
            finish = getattr(response, "stop_reason", "end_turn") or "stop"

            cost = self.estimate_cost(tokens_in, tokens_out)

            logger.info(
                "ai.text_generation",
                provider="anthropic",
                model=model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_paisas=cost,
                latency_ms=latency_ms,
            )

            return AITextResponse(
                content=text,
                tokens_used_input=tokens_in,
                tokens_used_output=tokens_out,
                finish_reason=finish,
                raw_response={"model": model_name, "latency_ms": latency_ms},
                estimated_cost_paisas=cost,
            )

        except (AICompletionError,):
            raise
        except Exception as exc:
            logger.error("ai.anthropic.completion_failed", error=str(exc))
            raise AICompletionError(
                f"Anthropic text generation failed: {exc}",
                operation="generate_text",
                details={"provider": "anthropic"},
            ) from exc

    # ── STT via Whisper Fallback ────────────────────────────────────

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str = "ur",
    ) -> AITranscriptionResponse:
        """Transcribe audio by routing to OpenAI Whisper.

        Anthropic has no native STT.  Falls back to OpenAI Whisper-1
        if OPENAI_API_KEY is available.

        Args:
            audio_bytes: Raw audio data.
            mime_type: MIME type of the audio.
            language_hint: ISO 639-1 language hint.

        Returns:
            Normalised AITranscriptionResponse.

        Raises:
            AITranscriptionError: If Whisper call fails or no key set.
        """
        if not self._openai_key:
            raise AITranscriptionError(
                "Anthropic has no native STT and OPENAI_API_KEY is not set "
                "for Whisper fallback.",
                operation="transcribe_audio",
                details={"provider": "anthropic"},
            )

        from app.ai.providers.openai_provider import OpenAIProvider  # noqa: WPS433

        whisper = OpenAIProvider()
        return await whisper.transcribe_audio(audio_bytes, mime_type, language_hint)

    # ── Cost ────────────────────────────────────────────────────────

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> int:
        """Estimate cost in paisas using Haiku pricing.

        Args:
            tokens_in: Input tokens.
            tokens_out: Output tokens.

        Returns:
            Estimated cost in paisas.
        """
        cost_in = (tokens_in * self._COST_PER_M_INPUT_HAIKU) / 1_000_000
        cost_out = (tokens_out * self._COST_PER_M_OUTPUT_HAIKU) / 1_000_000
        return max(1, int(cost_in + cost_out))

    # ── Metadata ────────────────────────────────────────────────────

    def get_provider_name(self) -> str:
        """Return ``anthropic``."""
        return "anthropic"

    def get_model_name(self, premium: bool = False) -> str:
        """Return the active model name.

        Args:
            premium: If True, return premium model.
        """
        return self._premium_model if premium else self._text_model

    # ── Health ──────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify Anthropic API is reachable.

        Returns:
            True if responsive, False otherwise.
        """
        try:
            client = self._get_async_client()
            response = await client.messages.create(
                model=self._text_model,
                max_tokens=5,
                temperature=0.0,
                messages=[{"role": "user", "content": "Reply OK"}],
            )
            return bool(response.content)
        except Exception as exc:
            logger.warning("ai.anthropic.health_check_failed", error=str(exc))
            return False
