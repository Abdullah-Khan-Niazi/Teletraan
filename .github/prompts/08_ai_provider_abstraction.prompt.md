# TELETRAAN AI Provider Abstraction — Implementation Spec

## Abstract Base Class (`app/ai/base.py`)

`AIProvider` abstract base class — all 5 provider implementations must inherit this.

### Required Abstract Methods
```python
async def generate_text(
    system_prompt: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> AITextResponse: ...

async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str,
    language_hint: str,
) -> AITranscriptionResponse: ...

def estimate_cost(tokens_in: int, tokens_out: int) -> int: ...  # returns paisas

def get_provider_name(self) -> str: ...
def get_model_name(self) -> str: ...
async def health_check(self) -> bool: ...
```

### Response Types

**AITextResponse** must contain:
- `content: str`
- `tokens_used_input: int`
- `tokens_used_output: int`
- `finish_reason: str`
- `raw_response: dict`
- `estimated_cost_paisas: int`

**AITranscriptionResponse** must contain:
- `text: str`
- `confidence: str`
- `language_detected: str`
- `duration_seconds: float`
- `raw_response: dict`

---

## Provider Implementations (`app/ai/providers/`)

| File | Provider | Text Model | Audio |
|---|---|---|---|
| `gemini_provider.py` | Google Gemini | gemini-1.5-flash | Native audio input |
| `openai_provider.py` | OpenAI | gpt-4o-mini / gpt-4o | whisper-1 |
| `anthropic_provider.py` | Anthropic Claude | claude-3-haiku / claude-3-5-sonnet | Route to Whisper |
| `cohere_provider.py` | Cohere | command-r / command-r-plus | Not supported — route to whisper |
| `openrouter_provider.py` | OpenRouter | OPENROUTER_MODEL env var | Not supported |

---

## Factory (`app/ai/factory.py`)
```python
# Reads ACTIVE_AI_PROVIDER from environment
# Returns correct provider instance
# If provider fails and AI_FALLBACK_PROVIDER is set: tries fallback once
# If fallback also fails: use rule-based response templates — bot continues
```

---

## Error Normalization
Every provider must catch provider-specific exceptions and re-raise as `TeletraanAIError`:
```python
class TeletraanAIError(TeletraanBaseError):
    provider: str
    original_message: str
    is_retryable: bool
    is_quota_exceeded: bool
    is_content_filtered: bool
```
All callers handle `TeletraanAIError` only — never provider-specific exceptions.

---

## Fallback Chain
1. Try `ACTIVE_AI_PROVIDER`
2. If fails and `AI_FALLBACK_PROVIDER` is set → try fallback once
3. Log both attempts to `analytics_events` with `ai_provider` field
4. If fallback also fails → use rule-based response templates (bot continues, no crash)

---

## Analytics Tracking
Every AI call must log to `analytics_events`:
- `ai_provider` — which provider handled the request
- `ai_tokens_used` — total tokens
- `ai_cost_paisas` — estimated cost
- `event_type` — `ai.text_generation` or `ai.transcription`

---

## STT Routing
- Voice pipeline reads `ACTIVE_STT_PROVIDER`
- If `gemini`: send audio bytes directly to Gemini (native audio input)
- If `whisper`: send to OpenAI Whisper endpoint
- Both paths produce `AITranscriptionResponse` with same fields
- Audio conversion (pydub/ffmpeg) happens before sending to any STT provider
- STT health checked separately from text AI health
