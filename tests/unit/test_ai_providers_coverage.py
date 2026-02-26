"""Tests for AI providers, factory, and response generator.

Covers GeminiProvider, OpenAIProvider, AnthropicProvider,
CohereProvider, OpenRouterProvider, factory functions, and
response_generator module-level functions.

SDKs (google.generativeai, openai, anthropic, cohere) are NOT installed
in the test environment, so they are injected via sys.modules mocks.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
# Settings mock helper
# ═══════════════════════════════════════════════════════════════

def _mock_settings() -> MagicMock:
    """Return a settings mock with all AI keys set."""
    s = MagicMock()
    s.gemini_api_key = "test-gemini-key"
    s.openai_api_key = "test-openai-key"
    s.anthropic_api_key = "test-anthropic-key"
    s.cohere_api_key = "test-cohere-key"
    s.openrouter_api_key = "test-openrouter-key"
    s.openrouter_model = "google/gemini-flash-1.5"
    s.ai_text_model = ""
    s.ai_premium_model = ""
    s.active_ai_provider = "gemini"
    s.ai_fallback_provider = "openai"
    s.effective_stt_provider = "gemini"
    s.meta_api_version = "v19.0"
    s.meta_api_base_url = "https://graph.facebook.com"
    return s


# ═══════════════════════════════════════════════════════════════
# SDK Module Mocks (SDKs are not installed)
# ═══════════════════════════════════════════════════════════════

def _install_mock_genai() -> MagicMock:
    """Install mock google.generativeai into sys.modules."""
    mock_genai = MagicMock()
    mock_google = MagicMock()
    mock_google.generativeai = mock_genai  # Link parent to child
    sys.modules["google"] = mock_google
    sys.modules["google.generativeai"] = mock_genai
    sys.modules["google.generativeai.types"] = mock_genai.types
    return mock_genai


def _install_mock_openai() -> MagicMock:
    """Install mock openai into sys.modules."""
    mock_openai = MagicMock()
    sys.modules["openai"] = mock_openai
    return mock_openai


def _install_mock_anthropic() -> MagicMock:
    """Install mock anthropic into sys.modules."""
    mock_anthropic = MagicMock()
    sys.modules["anthropic"] = mock_anthropic
    return mock_anthropic


def _install_mock_cohere() -> MagicMock:
    """Install mock cohere into sys.modules."""
    mock_cohere = MagicMock()
    sys.modules["cohere"] = mock_cohere
    return mock_cohere


# ═══════════════════════════════════════════════════════════════
# GEMINI PROVIDER
# ═══════════════════════════════════════════════════════════════


class TestGeminiProvider:
    """Test GeminiProvider via mocked google.generativeai SDK."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self) -> None:
        self.mock_genai = _install_mock_genai()
        with patch(
            "app.ai.providers.gemini_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.providers.gemini_provider import GeminiProvider
            self.provider = GeminiProvider()

    def test_get_provider_name(self) -> None:
        assert self.provider.get_provider_name() == "gemini"

    def test_get_model_name_default(self) -> None:
        name = self.provider.get_model_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_get_model_name_premium(self) -> None:
        name = self.provider.get_model_name(premium=True)
        assert isinstance(name, str)

    def test_estimate_cost(self) -> None:
        cost = self.provider.estimate_cost(1000, 500)
        assert isinstance(cost, int)
        assert cost >= 0

    @pytest.mark.asyncio
    async def test_generate_text(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "Hello from Gemini"
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 50
        mock_response.usage_metadata.candidates_token_count = 20
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].finish_reason = MagicMock()
        mock_response.candidates[0].finish_reason.name = "STOP"

        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=mock_response
        )
        self.mock_genai.GenerativeModel.return_value = mock_model

        result = await self.provider.generate_text(
            system_prompt="You are a test bot.",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result.content == "Hello from Gemini"
        assert result.tokens_used_input == 50

    @pytest.mark.asyncio
    async def test_generate_text_error(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            side_effect=Exception("API error")
        )
        self.mock_genai.GenerativeModel.return_value = mock_model

        from app.core.exceptions import AIProviderError
        with pytest.raises(AIProviderError):
            await self.provider.generate_text(
                system_prompt="test",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_transcribe_audio(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "Transcribed text"
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 10

        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=mock_response
        )
        self.mock_genai.GenerativeModel.return_value = mock_model

        result = await self.provider.transcribe_audio(
            audio_bytes=b"fake audio",
            mime_type="audio/ogg",
        )
        assert result.text == "Transcribed text"

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(text="ok")
        )
        self.mock_genai.GenerativeModel.return_value = mock_model
        result = await self.provider.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            side_effect=Exception("down")
        )
        self.mock_genai.GenerativeModel.return_value = mock_model
        result = await self.provider.health_check()
        assert result is False


# ═══════════════════════════════════════════════════════════════
# OPENAI PROVIDER
# ═══════════════════════════════════════════════════════════════


class TestOpenAIProvider:
    """Test OpenAIProvider via mocked openai.AsyncOpenAI."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self) -> None:
        self.mock_openai = _install_mock_openai()
        with patch(
            "app.ai.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.providers.openai_provider import OpenAIProvider
            self.provider = OpenAIProvider()

    def test_get_provider_name(self) -> None:
        assert self.provider.get_provider_name() == "openai"

    def test_estimate_cost(self) -> None:
        cost = self.provider.estimate_cost(1000, 500)
        assert isinstance(cost, int)

    @pytest.mark.asyncio
    async def test_generate_text(self) -> None:
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from OpenAI"
        mock_choice.finish_reason = "stop"

        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 50
        mock_completion.usage.completion_tokens = 20
        mock_completion.model_dump.return_value = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_completion
        )
        self.mock_openai.AsyncOpenAI.return_value = mock_client

        result = await self.provider.generate_text(
            system_prompt="Test",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result.content == "Hello from OpenAI"

    @pytest.mark.asyncio
    async def test_generate_text_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        self.mock_openai.AsyncOpenAI.return_value = mock_client

        from app.core.exceptions import AIProviderError
        with pytest.raises(AIProviderError):
            await self.provider.generate_text(
                system_prompt="Test",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_transcribe_audio(self) -> None:
        mock_transcription = MagicMock()
        mock_transcription.text = "Transcribed by Whisper"
        mock_transcription.language = "ur"
        mock_transcription.duration = 5.0

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )
        self.mock_openai.AsyncOpenAI.return_value = mock_client

        result = await self.provider.transcribe_audio(
            audio_bytes=b"fake audio",
            mime_type="audio/ogg",
        )
        assert result.text == "Transcribed by Whisper"

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_choice.finish_reason = "stop"

        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 5
        mock_completion.usage.completion_tokens = 2
        mock_completion.model_dump.return_value = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_completion
        )
        self.mock_openai.AsyncOpenAI.return_value = mock_client

        result = await self.provider.health_check()
        assert result is True


# ═══════════════════════════════════════════════════════════════
# ANTHROPIC PROVIDER
# ═══════════════════════════════════════════════════════════════


class TestAnthropicProvider:
    """Test AnthropicProvider via mocked anthropic.AsyncAnthropic."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self) -> None:
        self.mock_anthropic = _install_mock_anthropic()
        _install_mock_openai()  # for Whisper fallback
        with patch(
            "app.ai.providers.anthropic_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.providers.anthropic_provider import (
                AnthropicProvider,
            )
            self.provider = AnthropicProvider()

    def test_get_provider_name(self) -> None:
        assert self.provider.get_provider_name() == "anthropic"

    def test_estimate_cost(self) -> None:
        cost = self.provider.estimate_cost(1000, 500)
        assert isinstance(cost, int)

    @pytest.mark.asyncio
    async def test_generate_text(self) -> None:
        mock_content = MagicMock()
        mock_content.text = "Hello from Claude"

        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 20
        mock_response.stop_reason = "end_turn"
        mock_response.model_dump.return_value = {}

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=mock_response
        )
        self.mock_anthropic.AsyncAnthropic.return_value = mock_client

        result = await self.provider.generate_text(
            system_prompt="Test",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result.content == "Hello from Claude"

    @pytest.mark.asyncio
    async def test_generate_text_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )
        self.mock_anthropic.AsyncAnthropic.return_value = mock_client

        from app.core.exceptions import AIProviderError
        with pytest.raises(AIProviderError):
            await self.provider.generate_text(
                system_prompt="Test",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_transcribe_audio_delegates_to_openai(self) -> None:
        mock_openai = sys.modules["openai"]
        mock_transcription = MagicMock()
        mock_transcription.text = "Whisper transcription"
        mock_transcription.language = "ur"
        mock_transcription.duration = 3.0

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch(
            "app.ai.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ):
            result = await self.provider.transcribe_audio(
                audio_bytes=b"fake", mime_type="audio/ogg"
            )
            assert result.text == "Whisper transcription"


# ═══════════════════════════════════════════════════════════════
# COHERE PROVIDER
# ═══════════════════════════════════════════════════════════════


class TestCohereProvider:
    """Test CohereProvider via mocked cohere.AsyncClientV2."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self) -> None:
        self.mock_cohere = _install_mock_cohere()
        with patch(
            "app.ai.providers.cohere_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.providers.cohere_provider import CohereProvider
            self.provider = CohereProvider()

    def test_get_provider_name(self) -> None:
        assert self.provider.get_provider_name() == "cohere"

    def test_estimate_cost(self) -> None:
        cost = self.provider.estimate_cost(1000, 500)
        assert isinstance(cost, int)

    @pytest.mark.asyncio
    async def test_generate_text(self) -> None:
        mock_content = MagicMock()
        mock_content.text = "Hello from Cohere"

        mock_usage = MagicMock()
        mock_usage.tokens = MagicMock()
        mock_usage.tokens.input_tokens = 50
        mock_usage.tokens.output_tokens = 20

        mock_response = MagicMock()
        mock_response.message = MagicMock()
        mock_response.message.content = [mock_content]
        mock_response.usage = mock_usage
        mock_response.finish_reason = "COMPLETE"

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)
        self.mock_cohere.AsyncClientV2.return_value = mock_client

        result = await self.provider.generate_text(
            system_prompt="Test",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result.content == "Hello from Cohere"

    @pytest.mark.asyncio
    async def test_generate_text_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(
            side_effect=Exception("API error")
        )
        self.mock_cohere.AsyncClientV2.return_value = mock_client

        from app.core.exceptions import AIProviderError
        with pytest.raises(AIProviderError):
            await self.provider.generate_text(
                system_prompt="Test",
                messages=[{"role": "user", "content": "Hi"}],
            )


# ═══════════════════════════════════════════════════════════════
# OPENROUTER PROVIDER
# ═══════════════════════════════════════════════════════════════


class TestOpenRouterProvider:
    """Test OpenRouterProvider (uses openai.AsyncOpenAI with alt base URL)."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self) -> None:
        self.mock_openai = _install_mock_openai()
        with patch(
            "app.ai.providers.openrouter_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.providers.openrouter_provider import (
                OpenRouterProvider,
            )
            self.provider = OpenRouterProvider()

    def test_get_provider_name(self) -> None:
        assert self.provider.get_provider_name() == "openrouter"

    def test_estimate_cost(self) -> None:
        cost = self.provider.estimate_cost(1000, 500)
        assert isinstance(cost, int)

    @pytest.mark.asyncio
    async def test_generate_text(self) -> None:
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from OpenRouter"
        mock_choice.finish_reason = "stop"

        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 50
        mock_completion.usage.completion_tokens = 20
        mock_completion.model_dump.return_value = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_completion
        )
        self.mock_openai.AsyncOpenAI.return_value = mock_client

        result = await self.provider.generate_text(
            system_prompt="Test",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result.content == "Hello from OpenRouter"

    @pytest.mark.asyncio
    async def test_transcribe_audio_raises(self) -> None:
        from app.core.exceptions import AITranscriptionError
        with pytest.raises(AITranscriptionError):
            await self.provider.transcribe_audio(
                audio_bytes=b"fake", mime_type="audio/ogg"
            )

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_choice.finish_reason = "stop"

        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 5
        mock_completion.usage.completion_tokens = 2
        mock_completion.model_dump.return_value = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_completion
        )
        self.mock_openai.AsyncOpenAI.return_value = mock_client

        result = await self.provider.health_check()
        assert result is True


# ═══════════════════════════════════════════════════════════════
# AI FACTORY
# ═══════════════════════════════════════════════════════════════


class TestAIFactory:
    """Test AI provider factory functions."""

    def test_build_provider_gemini(self) -> None:
        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.providers.gemini_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.factory import _build_provider
            provider = _build_provider("gemini")
            assert provider.get_provider_name() == "gemini"

    def test_build_provider_openai(self) -> None:
        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.factory import _build_provider
            provider = _build_provider("openai")
            assert provider.get_provider_name() == "openai"

    def test_build_provider_unknown_raises(self) -> None:
        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.factory import _build_provider
            from app.core.exceptions import ConfigurationError
            with pytest.raises(ConfigurationError):
                _build_provider("unknown_provider")

    def test_get_ai_provider(self) -> None:
        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.providers.gemini_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.factory import get_ai_provider
            get_ai_provider.cache_clear()
            provider = get_ai_provider()
            assert provider.get_provider_name() == "gemini"
            get_ai_provider.cache_clear()

    def test_get_fallback_provider(self) -> None:
        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.providers.gemini_provider.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.factory import get_ai_provider, get_fallback_provider
            get_ai_provider.cache_clear()
            fb = get_fallback_provider()
            assert fb is not None
            assert fb.get_provider_name() == "openai"
            get_ai_provider.cache_clear()

    def test_get_stt_provider(self) -> None:
        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.providers.gemini_provider.get_settings",
            return_value=_mock_settings(),
        ):
            from app.ai.factory import get_stt_provider
            p = get_stt_provider()
            assert p.get_provider_name() == "gemini"

    @pytest.mark.asyncio
    async def test_generate_text_with_fallback_primary_success(
        self,
    ) -> None:
        from app.ai.base import AITextResponse

        mock_response = AITextResponse(
            content="test",
            tokens_used_input=10,
            tokens_used_output=5,
            finish_reason="stop",
            raw_response={},
            estimated_cost_paisas=1,
        )

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value=mock_response
        )

        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.factory.get_ai_provider",
            return_value=mock_provider,
        ):
            from app.ai.factory import generate_text_with_fallback
            result = await generate_text_with_fallback(
                system_prompt="test",
                messages=[{"role": "user", "content": "Hi"}],
            )
            assert result is not None
            assert result.content == "test"

    @pytest.mark.asyncio
    async def test_generate_text_with_fallback_all_fail(self) -> None:
        from app.core.exceptions import AIProviderError

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            side_effect=AIProviderError("fail")
        )

        with patch(
            "app.ai.factory.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.ai.factory.get_ai_provider",
            return_value=mock_provider,
        ), patch(
            "app.ai.factory.get_fallback_provider",
            return_value=mock_provider,
        ):
            from app.ai.factory import generate_text_with_fallback
            result = await generate_text_with_fallback(
                system_prompt="test",
                messages=[{"role": "user", "content": "Hi"}],
            )
            assert result is None


# ═══════════════════════════════════════════════════════════════
# RESPONSE GENERATOR
# ═══════════════════════════════════════════════════════════════


class TestResponseGenerator:
    """Test response generator functions."""

    def test_format_order_summary(self) -> None:
        from app.ai.response_generator import format_order_summary

        result = format_order_summary(
            order_number="ORD-20250226-ABCD",
            customer_name="Test Shop",
            items=[{"name": "Panadol 500mg", "qty": 10, "unit": "strip", "price_paisas": 5000}],
            subtotal=50000,
            total=50000,
        )
        assert "ORD-20250226-ABCD" in result
        assert "500" in result

    @pytest.mark.asyncio
    async def test_generate_greeting(self) -> None:
        from app.ai.base import AITextResponse
        from app.ai.response_generator import generate_greeting

        mock_response = AITextResponse(
            content="Salam! Welcome back.",
            tokens_used_input=10,
            tokens_used_output=5,
            finish_reason="stop",
            raw_response={},
            estimated_cost_paisas=1,
        )

        with patch(
            "app.ai.response_generator.generate_text_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await generate_greeting(
                distributor_name="Test Pharma",
                customer_name="Ali",
            )
            assert "Salam" in result or "Welcome" in result

    @pytest.mark.asyncio
    async def test_generate_greeting_ai_failure_fallback(self) -> None:
        from app.ai.response_generator import generate_greeting

        with patch(
            "app.ai.response_generator.generate_text_with_fallback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await generate_greeting(
                distributor_name="Test Pharma",
                customer_name="Ali",
            )
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_order_response(self) -> None:
        from app.ai.base import AITextResponse
        from app.ai.response_generator import generate_order_response

        mock_response = AITextResponse(
            content="Order noted: Panadol 10 packs.",
            tokens_used_input=20,
            tokens_used_output=10,
            finish_reason="stop",
            raw_response={},
            estimated_cost_paisas=2,
        )

        with patch(
            "app.ai.response_generator.generate_text_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.ai.response_generator.sanitize_for_prompt",
            side_effect=lambda x, **kw: x,
        ):
            result = await generate_order_response(
                distributor_name="Test Pharma",
                order_context="Panadol 10 packs",
                customer_name="Ali",
                phone_last4="1234",
                customer_message="Panadol chahiye",
            )
            assert "Panadol" in result

    @pytest.mark.asyncio
    async def test_generate_sales_response(self) -> None:
        from app.ai.base import AITextResponse
        from app.ai.response_generator import generate_sales_response

        mock_response = AITextResponse(
            content="Thank you for your interest!",
            tokens_used_input=20,
            tokens_used_output=10,
            finish_reason="stop",
            raw_response={},
            estimated_cost_paisas=2,
        )

        with patch(
            "app.ai.response_generator.generate_text_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.ai.response_generator.sanitize_for_prompt",
            side_effect=lambda x, **kw: x,
        ):
            result = await generate_sales_response(
                prospect_name="Kamran",
                prospect_message="Tell me about pricing",
            )
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_complaint_response(self) -> None:
        from app.ai.base import AITextResponse
        from app.ai.response_generator import generate_complaint_response

        mock_response = AITextResponse(
            content="We apologize for the issue.",
            tokens_used_input=20,
            tokens_used_output=10,
            finish_reason="stop",
            raw_response={},
            estimated_cost_paisas=2,
        )

        with patch(
            "app.ai.response_generator.generate_text_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.ai.response_generator.sanitize_for_prompt",
            side_effect=lambda x, **kw: x,
        ):
            result = await generate_complaint_response(
                distributor_name="Test Pharma",
                complaint_category="billing",
                customer_message="Wrong amount charged",
            )
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_price_stock_response(self) -> None:
        from app.ai.base import AITextResponse
        from app.ai.response_generator import generate_price_stock_response

        mock_response = AITextResponse(
            content="Panadol is Rs 50 per strip.",
            tokens_used_input=20,
            tokens_used_output=10,
            finish_reason="stop",
            raw_response={},
            estimated_cost_paisas=2,
        )

        with patch(
            "app.ai.response_generator.generate_text_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.ai.response_generator.sanitize_for_prompt",
            side_effect=lambda x, **kw: x,
        ):
            result = await generate_price_stock_response(
                distributor_name="Test Pharma",
                query_type="price",
                product_name="Panadol",
                catalog_data="Panadol 500mg - Rs 50/strip - In stock",
            )
            assert isinstance(result, str)

    def test_build_messages(self) -> None:
        from app.ai.response_generator import _build_messages

        history = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
        ]
        with patch(
            "app.ai.response_generator.sanitize_for_prompt",
            side_effect=lambda x, **kw: x,
        ):
            result = _build_messages(history, "new message", max_turns=5)
            assert isinstance(result, list)
            assert result[-1]["content"] == "new message"
