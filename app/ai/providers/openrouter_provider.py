"""OpenRouter AI provider — proxy to any model via OpenAI-compatible API.

OpenRouter exposes the OpenAI-compatible ``/chat/completions`` endpoint,
so we use the ``openai`` SDK pointed at ``https://openrouter.ai/api/v1``.
No STT support — ``transcribe_audio`` is not available.
"""

from __future__ import annotations

import time

from loguru import logger

from app.ai.base import AIProvider, AITextResponse, AITranscriptionResponse
from app.core.config import get_settings
from app.core.exceptions import AICompletionError, AITranscriptionError


class OpenRouterProvider(AIProvider):
    """OpenRouter implementation of the TELETRAAN AIProvider contract."""

    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "google/gemini-flash-1.5"

    # Cost varies by model — use a reasonable default in paisas/1M
    _COST_PER_M_INPUT = 42
    _COST_PER_M_OUTPUT = 168

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.openrouter_api_key or ""
        self._text_model: str = (
            settings.openrouter_model
            or settings.ai_text_model
            or self.DEFAULT_MODEL
        )
        self._premium_model: str = settings.ai_premium_model or self._text_model

    def _get_async_client(self):
        """Return an AsyncOpenAI client pointed at OpenRouter."""
        from openai import AsyncOpenAI  # noqa: WPS433

        return AsyncOpenAI(
            api_key=self._api_key,
            base_url=self.BASE_URL,
        )

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
        """Generate text via OpenRouter's OpenAI-compatible endpoint.

        Args:
            system_prompt: System-level instruction.
            messages: Conversation history.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            use_premium_model: Use the premium model if configured.

        Returns:
            Normalised AITextResponse.

        Raises:
            AICompletionError: On any OpenRouter API failure.
        """
        try:
            client = self._get_async_client()
            model_name = self._premium_model if use_premium_model else self._text_model

            api_messages = [{"role": "system", "content": system_prompt}]
            for msg in messages:
                api_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg["content"],
                })

            start = time.monotonic()
            response = await client.chat.completions.create(
                model=model_name,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_headers={
                    "HTTP-Referer": "https://teletraan.pk",
                    "X-Title": "TELETRAAN",
                },
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            choice = response.choices[0]
            text = choice.message.content or ""
            finish = choice.finish_reason or "stop"
            tokens_in = getattr(response.usage, "prompt_tokens", 0) or 0
            tokens_out = getattr(response.usage, "completion_tokens", 0) or 0

            cost = self.estimate_cost(tokens_in, tokens_out)

            logger.info(
                "ai.text_generation",
                provider="openrouter",
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
            logger.error("ai.openrouter.completion_failed", error=str(exc))
            raise AICompletionError(
                f"OpenRouter text generation failed: {exc}",
                operation="generate_text",
                details={"provider": "openrouter"},
            ) from exc

    # ── STT Not Supported ───────────────────────────────────────────

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str = "ur",
    ) -> AITranscriptionResponse:
        """OpenRouter does not support audio transcription.

        Raises:
            AITranscriptionError: Always — STT not available.
        """
        raise AITranscriptionError(
            "OpenRouter does not support audio transcription. "
            "Configure ACTIVE_STT_PROVIDER to 'gemini' or 'whisper'.",
            operation="transcribe_audio",
            details={"provider": "openrouter"},
        )

    # ── Cost ────────────────────────────────────────────────────────

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> int:
        """Estimate cost in paisas using generic pricing.

        Actual cost varies by the model chosen via OPENROUTER_MODEL.

        Args:
            tokens_in: Input tokens.
            tokens_out: Output tokens.

        Returns:
            Estimated cost in paisas.
        """
        cost_in = (tokens_in * self._COST_PER_M_INPUT) / 1_000_000
        cost_out = (tokens_out * self._COST_PER_M_OUTPUT) / 1_000_000
        return max(1, int(cost_in + cost_out))

    # ── Metadata ────────────────────────────────────────────────────

    def get_provider_name(self) -> str:
        """Return ``openrouter``."""
        return "openrouter"

    def get_model_name(self, premium: bool = False) -> str:
        """Return the active model name.

        Args:
            premium: If True, return premium model name.
        """
        return self._premium_model if premium else self._text_model

    # ── Health ──────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify OpenRouter API is reachable.

        Returns:
            True if responsive, False otherwise.
        """
        try:
            client = self._get_async_client()
            response = await client.chat.completions.create(
                model=self._text_model,
                messages=[{"role": "user", "content": "Reply OK"}],
                max_tokens=5,
                temperature=0.0,
                extra_headers={
                    "HTTP-Referer": "https://teletraan.pk",
                    "X-Title": "TELETRAAN",
                },
            )
            return bool(response.choices[0].message.content)
        except Exception as exc:
            logger.warning("ai.openrouter.health_check_failed", error=str(exc))
            return False
