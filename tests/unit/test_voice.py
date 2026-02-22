"""Unit tests for the voice pipeline.

Tests use mocked providers/media functions to verify the pipeline
orchestration, error handling, and post-processing logic without
making real API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.base import AITranscriptionResponse
from app.ai.voice import (
    _post_process_transcription,
    check_stt_health,
    transcribe_voice_message,
)
from app.core.exceptions import AITranscriptionError


# ═══════════════════════════════════════════════════════════════════
# FULL PIPELINE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestTranscribeVoiceMessage:
    """Test the full voice pipeline with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_successful_transcription_gemini(self):
        """Test successful pipeline with Gemini STT."""
        mock_transcription = AITranscriptionResponse(
            text="5 strip paracetamol chahiye",
            confidence="high",
            language_detected="ur",
            duration_seconds=3.5,
            raw_response={},
        )

        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "gemini"

        with (
            patch(
                "app.ai.voice.download_voice_bytes",
                new_callable=AsyncMock,
                return_value=(b"fake_ogg_data", "audio/ogg"),
            ),
            patch(
                "app.ai.voice.convert_ogg_to_wav",
                new_callable=AsyncMock,
                return_value=b"fake_wav_data",
            ),
            patch("app.ai.voice.get_settings", return_value=mock_settings),
            patch("app.ai.voice.get_stt_provider") as mock_get_stt,
        ):
            mock_provider = AsyncMock()
            mock_provider.transcribe_audio = AsyncMock(return_value=mock_transcription)
            mock_get_stt.return_value = mock_provider

            result = await transcribe_voice_message("media123", language_hint="ur")

            assert result.text == "5 strip paracetamol chahiye"
            assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_successful_transcription_whisper(self):
        """Test successful pipeline with Whisper STT."""
        mock_transcription = AITranscriptionResponse(
            text="mujhe augmentin chahiye",
            confidence="high",
            language_detected="ur",
            duration_seconds=2.0,
            raw_response={},
        )

        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "whisper"

        with (
            patch(
                "app.ai.voice.download_voice_bytes",
                new_callable=AsyncMock,
                return_value=(b"fake_ogg_data", "audio/ogg"),
            ),
            patch(
                "app.ai.voice.convert_ogg_to_wav",
                new_callable=AsyncMock,
                return_value=b"fake_wav_data",
            ),
            patch("app.ai.voice.get_settings", return_value=mock_settings),
            patch("app.ai.voice.get_stt_provider") as mock_get_stt,
        ):
            mock_provider = AsyncMock()
            mock_provider.transcribe_audio = AsyncMock(return_value=mock_transcription)
            mock_get_stt.return_value = mock_provider

            result = await transcribe_voice_message("media456", language_hint="ur")

            assert result.text == "mujhe augmentin chahiye"

    @pytest.mark.asyncio
    async def test_download_failure_raises(self):
        """Test that download failure raises AITranscriptionError."""
        with patch(
            "app.ai.voice.download_voice_bytes",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            with pytest.raises(AITranscriptionError, match="download"):
                await transcribe_voice_message("media_bad")

    @pytest.mark.asyncio
    async def test_whisper_conversion_failure_raises(self):
        """Test that conversion failure raises for Whisper (not for Gemini)."""
        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "whisper"

        with (
            patch(
                "app.ai.voice.download_voice_bytes",
                new_callable=AsyncMock,
                return_value=(b"fake_ogg", "audio/ogg"),
            ),
            patch(
                "app.ai.voice.convert_ogg_to_wav",
                new_callable=AsyncMock,
                side_effect=Exception("pydub error"),
            ),
            patch("app.ai.voice.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(AITranscriptionError, match="convert"):
                await transcribe_voice_message("media_ogg_bad")

    @pytest.mark.asyncio
    async def test_gemini_conversion_failure_uses_original(self):
        """Test that Gemini uses original OGG when conversion fails."""
        mock_transcription = AITranscriptionResponse(
            text="test text",
            confidence="medium",
            language_detected="ur",
            duration_seconds=1.0,
            raw_response={},
        )

        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "gemini"

        with (
            patch(
                "app.ai.voice.download_voice_bytes",
                new_callable=AsyncMock,
                return_value=(b"fake_ogg", "audio/ogg"),
            ),
            patch(
                "app.ai.voice.convert_ogg_to_wav",
                new_callable=AsyncMock,
                side_effect=Exception("pydub error"),
            ),
            patch("app.ai.voice.get_settings", return_value=mock_settings),
            patch("app.ai.voice.get_stt_provider") as mock_get_stt,
        ):
            mock_provider = AsyncMock()
            mock_provider.transcribe_audio = AsyncMock(return_value=mock_transcription)
            mock_get_stt.return_value = mock_provider

            result = await transcribe_voice_message("media_gemini")
            assert result.text == "test text"

    @pytest.mark.asyncio
    async def test_non_ogg_skips_conversion(self):
        """Test that non-OGG audio skips conversion step."""
        mock_transcription = AITranscriptionResponse(
            text="hello",
            confidence="high",
            language_detected="en",
            duration_seconds=1.0,
            raw_response={},
        )

        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "whisper"

        with (
            patch(
                "app.ai.voice.download_voice_bytes",
                new_callable=AsyncMock,
                return_value=(b"fake_wav", "audio/wav"),
            ),
            patch("app.ai.voice.get_settings", return_value=mock_settings),
            patch("app.ai.voice.get_stt_provider") as mock_get_stt,
        ):
            mock_provider = AsyncMock()
            mock_provider.transcribe_audio = AsyncMock(return_value=mock_transcription)
            mock_get_stt.return_value = mock_provider

            result = await transcribe_voice_message("media_wav")
            assert result.text == "hello"


# ═══════════════════════════════════════════════════════════════════
# POST-PROCESSING TESTS
# ═══════════════════════════════════════════════════════════════════


class TestPostProcessTranscription:
    @pytest.mark.asyncio
    async def test_successful_correction(self):
        """Test successful medicine name correction."""
        mock_response = AsyncMock()
        mock_response.content = '{"corrected_text": "5 strip Paracetamol 500mg", "corrections_made": []}'

        with patch(
            "app.ai.factory.generate_text_with_fallback",
            return_value=mock_response,
        ):
            result = await _post_process_transcription(
                "5 strip parasitamol",
                "ur",
                ["Paracetamol 500mg", "Amoxicillin 250mg"],
            )
            assert result == "5 strip Paracetamol 500mg"

    @pytest.mark.asyncio
    async def test_ai_failure_returns_none(self):
        """Test that AI failure returns None (non-critical)."""
        with patch(
            "app.ai.factory.generate_text_with_fallback",
            return_value=None,
        ):
            result = await _post_process_transcription(
                "test text", "ur", ["Product A"]
            )
            assert result is None


# ═══════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════


class TestCheckSttHealth:
    @pytest.mark.asyncio
    async def test_healthy_provider(self):
        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "gemini"

        mock_provider = AsyncMock()
        mock_provider.health_check = AsyncMock(return_value=True)

        with (
            patch("app.ai.voice.get_settings", return_value=mock_settings),
            patch("app.ai.voice.get_stt_provider", return_value=mock_provider),
        ):
            result = await check_stt_health()
            assert result == {"gemini": True}

    @pytest.mark.asyncio
    async def test_unhealthy_provider(self):
        mock_settings = MagicMock()
        mock_settings.effective_stt_provider = "whisper"

        with (
            patch("app.ai.voice.get_settings", return_value=mock_settings),
            patch("app.ai.voice.get_stt_provider", side_effect=Exception("fail")),
        ):
            result = await check_stt_health()
            assert result == {"whisper": False}
