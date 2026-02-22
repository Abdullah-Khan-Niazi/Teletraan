"""AI provider factory — env-driven selection with fallback chain.

Reads ``ACTIVE_AI_PROVIDER`` from environment and returns the correct
provider singleton.  If the primary provider fails,
``get_ai_provider_with_fallback`` will try ``AI_FALLBACK_PROVIDER``
once.  If that also fails, callers use rule-based templates so the
bot stays alive.
"""

from __future__ import annotations

import functools

from loguru import logger

from app.ai.base import AIProvider, AITextResponse
from app.core.config import get_settings
from app.core.exceptions import AICompletionError, AIProviderError, ConfigurationError


# ═══════════════════════════════════════════════════════════════════
# PROVIDER FACTORY
# ═══════════════════════════════════════════════════════════════════


def _build_provider(name: str) -> AIProvider:
    """Instantiate a provider by canonical name.

    Args:
        name: One of gemini, openai, anthropic, cohere, openrouter.

    Returns:
        An AIProvider instance.

    Raises:
        ConfigurationError: If the name is unknown.
    """
    from app.ai.providers import (  # noqa: WPS433
        AnthropicProvider,
        CohereProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
    )

    providers: dict[str, type[AIProvider]] = {
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "cohere": CohereProvider,
        "openrouter": OpenRouterProvider,
    }

    cls = providers.get(name)
    if cls is None:
        raise ConfigurationError(
            f"Unknown AI provider: '{name}'. "
            f"Valid options: {', '.join(providers.keys())}",
            operation="get_ai_provider",
        )

    return cls()


@functools.lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider:
    """Return the configured primary AI provider singleton.

    Reads ``ACTIVE_AI_PROVIDER`` from settings and returns a cached
    instance.

    Returns:
        The primary AIProvider.

    Raises:
        ConfigurationError: If the provider name is unknown.
    """
    settings = get_settings()
    provider = _build_provider(settings.active_ai_provider)
    logger.info(
        "ai.provider_loaded",
        provider=provider.get_provider_name(),
        model=provider.get_model_name(),
    )
    return provider


def get_fallback_provider() -> AIProvider | None:
    """Return the fallback AI provider, or None if not configured.

    Returns:
        An AIProvider instance, or None.
    """
    settings = get_settings()
    if not settings.ai_fallback_provider:
        return None
    if settings.ai_fallback_provider == settings.active_ai_provider:
        return None
    try:
        provider = _build_provider(settings.ai_fallback_provider)
        logger.debug(
            "ai.fallback_provider_loaded",
            provider=provider.get_provider_name(),
        )
        return provider
    except ConfigurationError:
        logger.warning(
            "ai.fallback_provider_invalid",
            name=settings.ai_fallback_provider,
        )
        return None


def get_stt_provider() -> AIProvider:
    """Return the provider to use for speech-to-text.

    Reads ``effective_stt_provider`` from settings.  If ``gemini``,
    returns GeminiProvider.  If ``whisper``, returns OpenAIProvider
    (which has Whisper support).

    Returns:
        AIProvider with STT capability.

    Raises:
        ConfigurationError: If the STT config is invalid.
    """
    settings = get_settings()
    stt = settings.effective_stt_provider
    if stt == "gemini":
        return _build_provider("gemini")
    if stt == "whisper":
        return _build_provider("openai")
    raise ConfigurationError(
        f"Unknown STT provider: '{stt}'. Valid: gemini, whisper.",
        operation="get_stt_provider",
    )


# ═══════════════════════════════════════════════════════════════════
# FALLBACK-AWARE GENERATION
# ═══════════════════════════════════════════════════════════════════


async def generate_text_with_fallback(
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
    *,
    use_premium_model: bool = False,
) -> AITextResponse | None:
    """Try primary provider, then fallback, then return None.

    Callers receiving None should use rule-based response templates
    so the bot continues operating without AI.

    Args:
        system_prompt: System instruction.
        messages: Conversation history.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        use_premium_model: Use premium model variant.

    Returns:
        AITextResponse on success, None if all providers fail.
    """
    primary = get_ai_provider()
    try:
        return await primary.generate_text(
            system_prompt=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            use_premium_model=use_premium_model,
        )
    except AIProviderError as exc:
        logger.warning(
            "ai.primary_provider_failed",
            provider=primary.get_provider_name(),
            error=str(exc),
        )

    fallback = get_fallback_provider()
    if fallback is None:
        logger.error("ai.no_fallback_configured")
        return None

    try:
        logger.info(
            "ai.trying_fallback",
            fallback_provider=fallback.get_provider_name(),
        )
        return await fallback.generate_text(
            system_prompt=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            use_premium_model=use_premium_model,
        )
    except AIProviderError as exc:
        logger.error(
            "ai.fallback_provider_also_failed",
            provider=fallback.get_provider_name(),
            error=str(exc),
        )
        return None
