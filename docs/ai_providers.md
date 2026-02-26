# TELETRAAN — AI Providers Guide

## Overview

TELETRAAN uses a pluggable AI provider system. All providers implement the
`AIProvider` base class with three capabilities:

1. **Text generation** — Natural language understanding and response
2. **Speech-to-text** (STT) — Voice message transcription
3. **Structured extraction** — Parse orders from natural language

The active provider is set via `ACTIVE_AI_PROVIDER`. A fallback provider
can be configured via `AI_FALLBACK_PROVIDER`.

---

## Provider Selection

```env
ACTIVE_AI_PROVIDER=gemini        # Options: gemini, openai, anthropic, cohere, openrouter
AI_FALLBACK_PROVIDER=openai      # Optional fallback
ACTIVE_STT_PROVIDER=openai       # Optional separate STT provider (defaults to main)
```

---

## Available Providers

### Gemini (Default)

Google's Gemini 1.5 Flash — fast, cost-effective, good for production.

```env
GEMINI_API_KEY=AIzaSy...
AI_TEXT_MODEL=gemini-1.5-flash     # Optional override
```

**SDK:** `google.generativeai`
**Default Model:** `gemini-1.5-flash`
**STT:** Not natively supported — falls back to OpenAI Whisper

### OpenAI

GPT-4o-mini for text, Whisper for STT.

```env
OPENAI_API_KEY=sk-...
AI_TEXT_MODEL=gpt-4o-mini          # Optional override
```

**SDK:** `openai` (AsyncOpenAI)
**Default Model:** `gpt-4o-mini`
**STT Model:** `whisper-1`

### Anthropic

Claude for high-quality reasoning tasks.

```env
ANTHROPIC_API_KEY=sk-ant-...
AI_TEXT_MODEL=claude-3-haiku-20240307  # Optional override
```

**SDK:** `anthropic` (AsyncAnthropic)
**Default Model:** `claude-3-haiku-20240307`
**STT:** Not supported — falls back to configured STT provider

### Cohere

Cohere's Command model for multilingual text processing.

```env
COHERE_API_KEY=...
AI_TEXT_MODEL=command-r            # Optional override
```

**SDK:** `cohere`
**Default Model:** `command-r`
**STT:** Falls back to OpenAI Whisper

### OpenRouter

Meta-provider routing to 100+ models via a single API.

```env
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct  # Required
```

**SDK:** `openai` (AsyncOpenAI with custom base URL)
**STT:** Falls back to OpenAI Whisper

---

## Configuration

### Common Settings

```env
AI_MAX_TOKENS=2048       # Max response tokens
AI_TEMPERATURE=0.30      # Response creativity (0.0 = deterministic, 1.0 = creative)
```

### Feature Flags

```env
ENABLE_VOICE_PROCESSING=true   # Enable/disable voice message handling
```

---

## How It Works

### Text Generation

```python
# The AI factory creates the active provider
provider = AIProviderFactory.create()

# Generate a response
response = await provider.generate(
    prompt="Customer wants to order Panadol",
    system_prompt="You are TELETRAAN, a medicine order assistant...",
    conversation_history=[...],
)
```

### Speech-to-Text

```python
# Transcribe a voice message
transcript = await provider.transcribe(
    audio_bytes=b"...",
    language="ur",  # Urdu
)
```

### Structured Extraction

The NLU module uses AI to extract structured data from natural language:

```python
from app.ai.nlu import NLUProcessor

nlu = NLUProcessor(provider)
result = await nlu.extract_order_items("Panadol 5 strip aur Augmentin 2 strip")
# Returns: [{"medicine": "Panadol", "quantity": 5, "unit": "strip"}, ...]
```

---

## Fallback Behaviour

If the primary provider fails:

1. Error logged with provider name and error details
2. If `AI_FALLBACK_PROVIDER` is set, retry with fallback
3. If fallback also fails, return a graceful error message to user
4. No exception propagates to the user

---

## Provider Health Check

```bash
curl https://your-app.com/api/admin/health/ai \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

Returns:
```json
{
  "provider": "gemini",
  "status": "healthy",
  "model": "gemini-1.5-flash"
}
```

---

## Switching Providers

1. Set the new provider's API key in environment variables
2. Change `ACTIVE_AI_PROVIDER` to the new provider name
3. Restart the application
4. Verify via `/api/admin/health/ai`

No code changes required — the factory pattern handles provider instantiation.

---

## Adding a New Provider

1. Create `app/ai/providers/new_provider.py`
2. Extend `AIProvider` base class
3. Implement: `generate()`, `transcribe()`, `extract_structured()`
4. Register in `app/ai/factory.py`
5. Add API key to `app/core/config.py` Settings
6. Update `.env.example`

---

## Cost Optimisation

| Provider | Approximate Cost (per 1M tokens) | Best For |
|---|---|---|
| Gemini Flash | ~$0.075 | Production (default) |
| GPT-4o-mini | ~$0.15 | Good quality + STT |
| Claude Haiku | ~$0.25 | Complex reasoning |
| Cohere Command-R | ~$0.50 | Multilingual |
| OpenRouter | Varies by model | Model experimentation |

**Recommendation:** Use Gemini Flash for production, OpenAI for STT,
keep GPT-4o-mini as fallback.
