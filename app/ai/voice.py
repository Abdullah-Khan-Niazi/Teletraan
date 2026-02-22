"""Voice pipeline — download, convert, and transcribe WhatsApp voice messages.

Orchestrates the full voice flow:
1. Download .ogg from Meta CDN via ``download_voice_bytes``
2. Convert to .wav via ``convert_ogg_to_wav``
3. Route to the configured STT provider (Gemini native or OpenAI Whisper)
4. Optionally post-process the transcription for medicine name correction

The STT provider is determined by ``effective_stt_provider`` in settings.
"""

from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from app.ai.base import AITranscriptionResponse
from app.ai.factory import get_ai_provider, get_stt_provider
from app.ai.prompts.admin import ADMIN_TRANSCRIPTION_CORRECTION_PROMPT
from app.core.config import get_settings
from app.core.exceptions import AIProviderError, AITranscriptionError
from app.whatsapp.media import convert_ogg_to_wav, download_voice_bytes


async def transcribe_voice_message(
    media_id: str,
    language_hint: str = "ur",
    *,
    post_process: bool = False,
    catalog_products: Optional[list[str]] = None,
) -> AITranscriptionResponse:
    """Full voice pipeline: download → convert → transcribe.

    Args:
        media_id: Meta media ID for the voice message.
        language_hint: ISO 639-1 hint (default ``ur`` for Urdu).
        post_process: If True, run transcription correction for medicine names.
        catalog_products: Product names for post-processing context.

    Returns:
        AITranscriptionResponse with transcribed text.

    Raises:
        AITranscriptionError: If any step in the pipeline fails.
    """
    start = time.monotonic()

    # Step 1 — Download raw audio bytes from Meta
    try:
        audio_bytes, mime_type = await download_voice_bytes(media_id)
        logger.debug(
            "voice.downloaded",
            media_id=media_id,
            size_bytes=len(audio_bytes),
            mime_type=mime_type,
        )
    except Exception as exc:
        logger.error("voice.download_failed", media_id=media_id, error=str(exc))
        raise AITranscriptionError(
            f"Failed to download voice message: {exc}",
            operation="download_voice",
            details={"media_id": media_id},
        ) from exc

    # Step 2 — Convert OGG to WAV (most STT providers prefer WAV)
    settings = get_settings()
    stt_name = settings.effective_stt_provider
    converted_bytes = audio_bytes
    converted_mime = mime_type

    if mime_type in {"audio/ogg", "audio/ogg; codecs=opus"}:
        try:
            converted_bytes = await convert_ogg_to_wav(audio_bytes)
            converted_mime = "audio/wav"
            logger.debug(
                "voice.converted",
                from_type=mime_type,
                to_type="audio/wav",
                original_size=len(audio_bytes),
                converted_size=len(converted_bytes),
            )
        except Exception as exc:
            # Gemini can handle OGG natively — only fail for Whisper
            if stt_name == "whisper":
                logger.error("voice.conversion_failed", error=str(exc))
                raise AITranscriptionError(
                    f"Failed to convert audio for Whisper: {exc}",
                    operation="convert_audio",
                ) from exc
            logger.warning(
                "voice.conversion_failed_using_original",
                error=str(exc),
            )

    # Step 3 — Route to STT provider
    try:
        stt_provider = get_stt_provider()
        result = await stt_provider.transcribe_audio(
            audio_bytes=converted_bytes,
            mime_type=converted_mime,
            language_hint=language_hint,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "voice.transcribed",
            stt_provider=stt_name,
            text_length=len(result.text),
            confidence=result.confidence,
            language=result.language_detected,
            latency_ms=latency_ms,
        )
    except AITranscriptionError:
        raise
    except AIProviderError as exc:
        logger.error("voice.stt_failed", provider=stt_name, error=str(exc))
        raise AITranscriptionError(
            f"STT provider '{stt_name}' failed: {exc}",
            operation="transcribe_audio",
            details={"stt_provider": stt_name},
        ) from exc

    # Step 4 — Optional post-processing for medicine name correction
    if post_process and result.text and catalog_products:
        try:
            corrected = await _post_process_transcription(
                result.text, language_hint, catalog_products
            )
            if corrected:
                logger.debug(
                    "voice.post_processed",
                    original=result.text[:50],
                    corrected=corrected[:50],
                )
                result = AITranscriptionResponse(
                    text=corrected,
                    confidence=result.confidence,
                    language_detected=result.language_detected,
                    duration_seconds=result.duration_seconds,
                    raw_response={
                        **result.raw_response,
                        "original_text": result.text,
                    },
                )
        except Exception as exc:
            # Post-processing failure is non-critical — use original
            logger.warning("voice.post_processing_failed", error=str(exc))

    return result


async def _post_process_transcription(
    raw_text: str,
    language: str,
    catalog_products: list[str],
) -> str | None:
    """Post-process transcription to correct medicine names.

    Uses AI to compare the raw transcription against known catalog
    product names and fix likely STT errors.

    Args:
        raw_text: Raw transcribed text.
        language: Detected language.
        catalog_products: Known product names in catalog.

    Returns:
        Corrected text, or None if correction failed.
    """
    from app.ai.factory import generate_text_with_fallback  # noqa: WPS433

    products_str = ", ".join(catalog_products[:50])  # Limit to avoid token bloat
    prompt = ADMIN_TRANSCRIPTION_CORRECTION_PROMPT.format(
        raw_text=raw_text,
        language=language,
        catalog_products=products_str,
    )

    response = await generate_text_with_fallback(
        system_prompt=prompt,
        messages=[{"role": "user", "content": raw_text}],
        temperature=0.1,
        max_tokens=512,
    )

    if response is None:
        return None

    # Try to extract corrected_text from JSON response
    import json
    import re

    text = response.content
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return data.get("corrected_text")
        except (json.JSONDecodeError, TypeError):
            pass

    return None


async def check_stt_health() -> dict[str, bool]:
    """Check health of both STT providers.

    Returns:
        Dict with provider name → health status.
    """
    results: dict[str, bool] = {}

    settings = get_settings()
    stt_name = settings.effective_stt_provider

    try:
        stt = get_stt_provider()
        results[stt_name] = await stt.health_check()
    except Exception:
        results[stt_name] = False

    return results
