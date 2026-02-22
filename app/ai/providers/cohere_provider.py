"""Cohere AI provider — text generation with Whisper STT fallback.

Uses the ``cohere`` Python SDK (async client).  Command-R is the
default model, Command-R+ is premium.  Cohere has no STT capability
so ``transcribe_audio`` routes to OpenAI Whisper.
"""

from __future__ import annotations

import time

from loguru import logger

from app.ai.base import AIProvider, AITextResponse, AITranscriptionResponse
from app.core.config import get_settings
from app.core.exceptions import AICompletionError, AITranscriptionError


class CohereProvider(AIProvider):
    """Cohere implementation of the TELETRAAN AIProvider contract."""

    DEFAULT_MODEL = "command-r"
    PREMIUM_MODEL = "command-r-plus"

    # Cost per 1M tokens in paisas (approx at PKR 280/USD)
    # Command-R:  $0.15/1M in, $0.60/1M out  ≈ 42/168 paisas
    # Command-R+: $2.50/1M in, $10.00/1M out ≈ 700/2800 paisas
    _COST_PER_M_INPUT_R = 42
    _COST_PER_M_OUTPUT_R = 168
    _COST_PER_M_INPUT_R_PLUS = 700
    _COST_PER_M_OUTPUT_R_PLUS = 2800

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.cohere_api_key or ""
        self._openai_key: str = settings.openai_api_key or ""
        self._text_model: str = settings.ai_text_model or self.DEFAULT_MODEL
        self._premium_model: str = settings.ai_premium_model or self.PREMIUM_MODEL

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
        """Generate text using Cohere chat endpoint.

        Args:
            system_prompt: System-level instruction (preamble).
            messages: Conversation history.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            use_premium_model: Use Command-R+ instead of Command-R.

        Returns:
            Normalised AITextResponse.

        Raises:
            AICompletionError: On any Cohere API failure.
        """
        try:
            import cohere  # noqa: WPS433

            client = cohere.AsyncClientV2(api_key=self._api_key)
            model_name = self._premium_model if use_premium_model else self._text_model

            # Build Cohere-style messages
            api_messages: list[dict] = [
                {"role": "system", "content": system_prompt},
            ]
            for msg in messages:
                role = msg.get("role", "user")
                api_messages.append({
                    "role": role,
                    "content": msg["content"],
                })

            start = time.monotonic()
            response = await client.chat(
                model=model_name,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            text = ""
            if response.message and response.message.content:
                for block in response.message.content:
                    if hasattr(block, "text"):
                        text += block.text

            tokens_in = 0
            tokens_out = 0
            if response.usage and response.usage.tokens:
                tokens_in = getattr(response.usage.tokens, "input_tokens", 0) or 0
                tokens_out = getattr(response.usage.tokens, "output_tokens", 0) or 0

            finish = getattr(response, "finish_reason", "COMPLETE") or "stop"

            cost = self.estimate_cost(tokens_in, tokens_out)

            logger.info(
                "ai.text_generation",
                provider="cohere",
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
                finish_reason=str(finish).lower(),
                raw_response={"model": model_name, "latency_ms": latency_ms},
                estimated_cost_paisas=cost,
            )

        except (AICompletionError,):
            raise
        except Exception as exc:
            logger.error("ai.cohere.completion_failed", error=str(exc))
            raise AICompletionError(
                f"Cohere text generation failed: {exc}",
                operation="generate_text",
                details={"provider": "cohere"},
            ) from exc

    # ── STT via Whisper Fallback ────────────────────────────────────

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str = "ur",
    ) -> AITranscriptionResponse:
        """Transcribe audio by routing to OpenAI Whisper.

        Cohere has no STT capability.

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
                "Cohere has no native STT and OPENAI_API_KEY is not set "
                "for Whisper fallback.",
                operation="transcribe_audio",
                details={"provider": "cohere"},
            )

        from app.ai.providers.openai_provider import OpenAIProvider  # noqa: WPS433

        whisper = OpenAIProvider()
        return await whisper.transcribe_audio(audio_bytes, mime_type, language_hint)

    # ── Cost ────────────────────────────────────────────────────────

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> int:
        """Estimate cost in paisas using Command-R pricing.

        Args:
            tokens_in: Input tokens.
            tokens_out: Output tokens.

        Returns:
            Estimated cost in paisas.
        """
        cost_in = (tokens_in * self._COST_PER_M_INPUT_R) / 1_000_000
        cost_out = (tokens_out * self._COST_PER_M_OUTPUT_R) / 1_000_000
        return max(1, int(cost_in + cost_out))

    # ── Metadata ────────────────────────────────────────────────────

    def get_provider_name(self) -> str:
        """Return ``cohere``."""
        return "cohere"

    def get_model_name(self, premium: bool = False) -> str:
        """Return the active model name.

        Args:
            premium: If True, return premium model.
        """
        return self._premium_model if premium else self._text_model

    # ── Health ──────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify Cohere API is reachable.

        Returns:
            True if responsive, False otherwise.
        """
        try:
            import cohere  # noqa: WPS433

            client = cohere.AsyncClientV2(api_key=self._api_key)
            response = await client.chat(
                model=self._text_model,
                messages=[
                    {"role": "system", "content": "You reply with OK only."},
                    {"role": "user", "content": "Reply OK"},
                ],
                max_tokens=5,
                temperature=0.0,
            )
            return bool(response.message and response.message.content)
        except Exception as exc:
            logger.warning("ai.cohere.health_check_failed", error=str(exc))
            return False
