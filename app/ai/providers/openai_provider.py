"""OpenAI AI provider — GPT text generation and Whisper STT.

Uses the ``openai`` Python SDK (async client).  GPT-4o-mini is the
default model, GPT-4o is the premium variant.  Audio transcription
is handled by the Whisper-1 endpoint.
"""

from __future__ import annotations

import time

from loguru import logger

from app.ai.base import AIProvider, AITextResponse, AITranscriptionResponse
from app.core.config import get_settings
from app.core.exceptions import AICompletionError, AITranscriptionError


class OpenAIProvider(AIProvider):
    """OpenAI implementation of the TELETRAAN AIProvider contract."""

    DEFAULT_MODEL = "gpt-4o-mini"
    PREMIUM_MODEL = "gpt-4o"
    WHISPER_MODEL = "whisper-1"

    # Cost per 1M tokens in paisas (approx at PKR 280/USD)
    # gpt-4o-mini: $0.15/1M in, $0.60/1M out ≈ 42/168 paisas
    # gpt-4o:      $5.00/1M in, $15.00/1M out ≈ 1400/4200 paisas
    _COST_PER_M_INPUT_MINI = 42
    _COST_PER_M_OUTPUT_MINI = 168
    _COST_PER_M_INPUT_FULL = 1400
    _COST_PER_M_OUTPUT_FULL = 4200

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.openai_api_key or ""
        self._text_model: str = settings.ai_text_model or self.DEFAULT_MODEL
        self._premium_model: str = settings.ai_premium_model or self.PREMIUM_MODEL

    def _get_async_client(self):
        """Return a new AsyncOpenAI client (import deferred)."""
        from openai import AsyncOpenAI  # noqa: WPS433

        return AsyncOpenAI(api_key=self._api_key)

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
        """Generate text using OpenAI chat completions.

        Args:
            system_prompt: System-level instruction.
            messages: Conversation history.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            use_premium_model: Use GPT-4o instead of GPT-4o-mini.

        Returns:
            Normalised AITextResponse.

        Raises:
            AICompletionError: On any OpenAI API failure.
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
                provider="openai",
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
            logger.error("ai.openai.completion_failed", error=str(exc))
            raise AICompletionError(
                f"OpenAI text generation failed: {exc}",
                operation="generate_text",
                details={"provider": "openai"},
            ) from exc

    # ── Whisper STT ─────────────────────────────────────────────────

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str = "ur",
    ) -> AITranscriptionResponse:
        """Transcribe audio using OpenAI Whisper.

        Args:
            audio_bytes: Raw audio data.
            mime_type: MIME type of the audio.
            language_hint: ISO 639-1 language hint.

        Returns:
            Normalised AITranscriptionResponse.

        Raises:
            AITranscriptionError: On any Whisper API failure.
        """
        try:
            import io

            from openai import AsyncOpenAI  # noqa: WPS433

            client = AsyncOpenAI(api_key=self._api_key)

            # Determine file extension from MIME type
            ext_map = {
                "audio/wav": "wav",
                "audio/x-wav": "wav",
                "audio/ogg": "ogg",
                "audio/mpeg": "mp3",
                "audio/mp4": "m4a",
                "audio/webm": "webm",
            }
            ext = ext_map.get(mime_type, "wav")
            filename = f"audio.{ext}"

            # Wrap bytes in a file-like object
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename

            start = time.monotonic()
            response = await client.audio.transcriptions.create(
                model=self.WHISPER_MODEL,
                file=audio_file,
                language=language_hint if len(language_hint) == 2 else None,
                response_format="verbose_json",
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            text = response.text or ""
            duration = getattr(response, "duration", 0.0) or 0.0
            detected_lang = getattr(response, "language", language_hint) or language_hint

            # Confidence heuristic based on duration vs text ratio
            confidence = "high"
            if not text or len(text.strip()) < 3:
                confidence = "low"
            elif duration > 0 and len(text) / duration < 2:
                confidence = "medium"

            logger.info(
                "ai.transcription",
                provider="openai_whisper",
                model=self.WHISPER_MODEL,
                duration_seconds=round(duration, 2),
                latency_ms=latency_ms,
                language_hint=language_hint,
            )

            return AITranscriptionResponse(
                text=text,
                confidence=confidence,
                language_detected=detected_lang,
                duration_seconds=round(duration, 2),
                raw_response={"model": self.WHISPER_MODEL, "latency_ms": latency_ms},
            )

        except (AITranscriptionError,):
            raise
        except Exception as exc:
            logger.error("ai.openai.transcription_failed", error=str(exc))
            raise AITranscriptionError(
                f"OpenAI Whisper transcription failed: {exc}",
                operation="transcribe_audio",
                details={"provider": "openai_whisper"},
            ) from exc

    # ── Cost ────────────────────────────────────────────────────────

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> int:
        """Estimate cost in paisas using GPT-4o-mini pricing.

        Args:
            tokens_in: Input tokens.
            tokens_out: Output tokens.

        Returns:
            Estimated cost in paisas.
        """
        cost_in = (tokens_in * self._COST_PER_M_INPUT_MINI) / 1_000_000
        cost_out = (tokens_out * self._COST_PER_M_OUTPUT_MINI) / 1_000_000
        return max(1, int(cost_in + cost_out))

    # ── Metadata ────────────────────────────────────────────────────

    def get_provider_name(self) -> str:
        """Return ``openai``."""
        return "openai"

    def get_model_name(self, premium: bool = False) -> str:
        """Return the active model name.

        Args:
            premium: If True, return premium model name.
        """
        return self._premium_model if premium else self._text_model

    # ── Health ──────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify OpenAI API is reachable.

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
            )
            return bool(response.choices[0].message.content)
        except Exception as exc:
            logger.warning("ai.openai.health_check_failed", error=str(exc))
            return False
