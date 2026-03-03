"""Google Gemini AI provider — text generation and native audio transcription.

Uses the ``google-generativeai`` SDK.  Gemini 1.5 Flash is the default
(cheap, fast, good Urdu/Roman-Urdu).  Gemini 1.5 Pro is the premium
variant.  Gemini supports native audio input, so ``transcribe_audio``
sends raw bytes directly without routing to Whisper.
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

from app.ai.base import AIProvider, AITextResponse, AITranscriptionResponse
from app.core.config import get_settings
from app.core.exceptions import AICompletionError, AITranscriptionError


class GeminiProvider(AIProvider):
    """Google Gemini implementation of the TELETRAAN AIProvider contract."""

    DEFAULT_MODEL = "gemini-1.5-flash"
    PREMIUM_MODEL = "gemini-1.5-pro"

    # ── Rough cost per 1M tokens in paisas (PKR 0.01 = 1 paisa) ──
    # Flash: ~$0.075/1M input, ~$0.30/1M output  ≈ 21/84 paisas/1M
    # Pro:   ~$3.50/1M input, ~$10.50/1M output   ≈ 980/2940 paisas/1M
    _COST_PER_M_INPUT_FLASH = 21
    _COST_PER_M_OUTPUT_FLASH = 84
    _COST_PER_M_INPUT_PRO = 980
    _COST_PER_M_OUTPUT_PRO = 2940

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.gemini_api_key or ""
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
        """Generate text using Gemini generative model.

        Args:
            system_prompt: System-level instruction.
            messages: Conversation history.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            use_premium_model: Use Gemini 1.5 Pro instead of Flash.

        Returns:
            Normalised AITextResponse.

        Raises:
            AICompletionError: On any Gemini API failure.
        """
        try:
            import google.generativeai as genai  # noqa: WPS433

            genai.configure(api_key=self._api_key)

            model_name = self._premium_model if use_premium_model else self._text_model
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt,
            )

            # Build Gemini contents from messages
            contents: list[dict] = []
            for msg in messages:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [msg["content"]]})

            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            start = time.monotonic()
            response = await asyncio.to_thread(
                model.generate_content,
                contents=contents,
                generation_config=generation_config,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            # Extract usage metadata
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            text = response.text or ""
            finish = "stop"
            if response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                if finish_reason:
                    finish = str(finish_reason).lower().replace("finishreason.", "")

            cost = self.estimate_cost(tokens_in, tokens_out)

            logger.info(
                "ai.text_generation",
                provider="gemini",
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

        except (AICompletionError, AITranscriptionError):
            raise
        except Exception as exc:
            logger.error("ai.gemini.completion_failed", error=str(exc))
            raise AICompletionError(
                f"Gemini text generation failed: {exc}",
                operation="generate_text",
                details={"provider": "gemini"},
            ) from exc

    # ── Native Audio Transcription ──────────────────────────────────

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str = "ur",
    ) -> AITranscriptionResponse:
        """Transcribe audio using Gemini's native audio support.

        Gemini can accept audio bytes directly as multimodal input
        and return a text transcription.

        Args:
            audio_bytes: Raw audio data.
            mime_type: MIME type (e.g. ``audio/wav``, ``audio/ogg``).
            language_hint: ISO 639-1 language hint.

        Returns:
            Normalised AITranscriptionResponse.

        Raises:
            AITranscriptionError: On any Gemini API failure.
        """
        try:
            import google.generativeai as genai  # noqa: WPS433

            genai.configure(api_key=self._api_key)

            model = genai.GenerativeModel(model_name=self._text_model)

            # Build audio part for multimodal input
            prompt = (
                f"Transcribe the following audio exactly as spoken. "
                f"The language is likely {language_hint}. "
                f"Return ONLY the transcribed text, nothing else."
            )
            audio_part = {"mime_type": mime_type, "data": audio_bytes}

            start = time.monotonic()
            response = await asyncio.to_thread(
                model.generate_content,
                contents=[prompt, audio_part],
                generation_config=genai.types.GenerationConfig(temperature=0.1),
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            text = (response.text or "").strip()
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            # Rough duration estimate: 16kHz mono 16-bit ≈ 32000 bytes/sec
            estimated_duration = len(audio_bytes) / 32000.0

            logger.info(
                "ai.transcription",
                provider="gemini",
                model=self._text_model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                language_hint=language_hint,
            )

            return AITranscriptionResponse(
                text=text,
                confidence="high" if len(text) > 5 else "low",
                language_detected=language_hint,
                duration_seconds=round(estimated_duration, 2),
                raw_response={"model": self._text_model, "latency_ms": latency_ms},
            )

        except (AITranscriptionError,):
            raise
        except Exception as exc:
            logger.error("ai.gemini.transcription_failed", error=str(exc))
            raise AITranscriptionError(
                f"Gemini audio transcription failed: {exc}",
                operation="transcribe_audio",
                details={"provider": "gemini"},
            ) from exc

    # ── Cost ────────────────────────────────────────────────────────

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> int:
        """Estimate cost in paisas based on Flash pricing.

        Args:
            tokens_in: Input tokens.
            tokens_out: Output tokens.

        Returns:
            Estimated cost in paisas.
        """
        cost_in = (tokens_in * self._COST_PER_M_INPUT_FLASH) / 1_000_000
        cost_out = (tokens_out * self._COST_PER_M_OUTPUT_FLASH) / 1_000_000
        return max(1, int(cost_in + cost_out))

    # ── Metadata ────────────────────────────────────────────────────

    def get_provider_name(self) -> str:
        """Return ``gemini``."""
        return "gemini"

    def get_model_name(self, premium: bool = False) -> str:
        """Return the active model name.

        Args:
            premium: If True, return premium model name.
        """
        return self._premium_model if premium else self._text_model

    # ── Health ──────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify Gemini API is reachable with a minimal call.

        Returns:
            True if responsive, False otherwise.
        """
        try:
            import google.generativeai as genai  # noqa: WPS433

            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(model_name=self._text_model)
            response = await asyncio.to_thread(
                model.generate_content,
                contents="Reply with OK",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=5,
                ),
            )
            return bool(response.text)
        except Exception as exc:
            logger.warning("ai.gemini.health_check_failed", error=str(exc))
            return False
