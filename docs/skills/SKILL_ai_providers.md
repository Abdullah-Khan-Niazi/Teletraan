# AI PROVIDER INTEGRATION SKILL
## SKILL: ai-providers | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines how to implement and switch between AI providers in TELETRAAN.
All AI interaction — text generation, intent classification, entity extraction,
voice transcription — goes through the abstract AIProvider interface.

---

## ARCHITECTURE

```
NLU / Response Generator / Voice Pipeline
             ↓
    ai_factory.get_provider()
             ↓
       AIProvider (abstract)
             ↓
[gemini | openai | anthropic | cohere | openrouter]
```

Text and voice (STT) are configured independently:
- ACTIVE_AI_PROVIDER → text generation + NLU
- ACTIVE_STT_PROVIDER → speech-to-text (can be same or different)

---

## ABSTRACT BASE CLASS (app/ai/base.py)

### Methods every provider must implement:

```
generate_text(
    system_prompt: str,
    messages: list[dict],  # [{"role": "user/assistant", "content": "..."}]
    temperature: float = 0.3,
    max_tokens: int = 2048,
    use_premium_model: bool = False,
) → AITextResponse

transcribe_audio(
    audio_bytes: bytes,
    mime_type: str,       # e.g., "audio/ogg", "audio/wav"
    language_hint: str,   # e.g., "ur" (Urdu), "en"
) → AITranscriptionResponse

estimate_cost(
    tokens_in: int,
    tokens_out: int,
) → int  # estimated cost in paisas

get_provider_name() → str
get_model_name(premium: bool = False) → str
health_check() → bool  # Test API reachability with minimal call
```

### Response models:

```
AITextResponse:
    content: str                    # The generated text
    tokens_used_input: int
    tokens_used_output: int
    finish_reason: str              # "stop", "max_tokens", "error"
    raw_response: dict              # Full provider response for debugging
    estimated_cost_paisas: int

AITranscriptionResponse:
    text: str                       # Transcribed text
    confidence: str                 # "high", "medium", "low"
    language_detected: str          # ISO 639-1 code
    duration_seconds: float
    raw_response: dict
```

---

## PROVIDER IMPLEMENTATIONS

### Gemini (app/ai/providers/gemini_provider.py)

**SDK:** `google-generativeai`
**Text model:** `gemini-1.5-flash` (default), `gemini-1.5-pro` (premium)
**Audio:** Native — pass audio bytes directly as Part with mime_type

Text generation:
- Use `genai.GenerativeModel(model_name)`
- Build `Content` objects from messages list
- Set `generation_config` with temperature and max_output_tokens
- System prompt → first `Content(role="user")` with `[SYSTEM]` prefix
  OR use `system_instruction` parameter if available in SDK version

Audio transcription:
- Create `Part` from audio_bytes with mime_type
- Send with transcription prompt: "Transcribe this audio exactly as spoken.
  Language: Urdu/Roman Urdu/English. Return only the transcription text."
- Parse response text as transcription

Token counting: use `model.count_tokens()` before generate for input estimate.
Cost estimate: ~$0.075/1M input tokens, ~$0.30/1M output tokens → convert to paisas.

### OpenAI (app/ai/providers/openai_provider.py)

**SDK:** `openai` official Python SDK v1.x
**Text model:** `gpt-4o-mini` (default), `gpt-4o` (premium)
**STT model:** `whisper-1`

Text generation:
- `client.chat.completions.create(model=..., messages=[...], ...)`
- System message → `{"role": "system", "content": system_prompt}`
- Usage in response: `completion.usage.prompt_tokens`, `completion.usage.completion_tokens`

Audio transcription (Whisper):
- Convert audio_bytes to file-like object: `io.BytesIO(audio_bytes)`
- `client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ur")`
- Returns `.text` attribute

Cost: gpt-4o-mini ~$0.15/1M input, $0.60/1M output. Whisper $0.006/min.
Convert minutes: `duration_seconds / 60 * 0.006 * 100 * 300` (rough PKR paisas)

### Anthropic (app/ai/providers/anthropic_provider.py)

**SDK:** `anthropic` v0.25+
**Text model:** `claude-3-haiku-20240307` (default), `claude-3-5-sonnet-20241022` (premium)
**STT:** Not supported natively — use OpenAI Whisper as STT when Anthropic is text provider

Text generation:
- `client.messages.create(model=..., max_tokens=..., system=system_prompt, messages=[...])`
- Claude format: messages must alternate user/assistant, start with user
- Response: `message.content[0].text` for text blocks
- Usage: `message.usage.input_tokens`, `message.usage.output_tokens`

For STT when Anthropic is ACTIVE_AI_PROVIDER and ACTIVE_STT_PROVIDER=whisper:
- Instantiate OpenAI client with OPENAI_API_KEY for Whisper calls only
- Text generation uses Anthropic

### Cohere (app/ai/providers/cohere_provider.py)

**SDK:** `cohere` v5.x
**Text model:** `command-r` (default), `command-r-plus` (premium)
**STT:** Not supported — use Whisper as STT fallback

Text generation:
- `client.chat(model=..., message=last_user_message, chat_history=[...], preamble=system_prompt)`
- Cohere uses `chat_history` for turns and `preamble` for system prompt
- Convert OpenAI-format messages to Cohere's format before calling
- Response: `response.text`

### OpenRouter (app/ai/providers/openrouter_provider.py)

**API:** OpenAI-compatible REST API
**Base URL:** `https://openrouter.ai/api/v1`
**Auth:** `Authorization: Bearer OPENROUTER_API_KEY`
**Model:** Set by OPENROUTER_MODEL env var
**STT:** Not supported — use Whisper

Implementation: identical to OpenAI provider but with different base_url.
Use `openai` SDK with `base_url="https://openrouter.ai/api/v1"` override.
Add required headers: `HTTP-Referer: https://teletraan.pk`, `X-Title: TELETRAAN`.

---

## MESSAGES FORMAT NORMALIZATION

Internal messages format (always use this in your code — never provider-specific):
```python
[
    {"role": "user", "content": "Customer message here"},
    {"role": "assistant", "content": "Bot response here"},
    {"role": "user", "content": "Next customer message"},
]
```

Each provider's implementation converts this to provider-specific format internally.
The NLU and response generator NEVER know which provider they're talking to.

---

## ERROR NORMALIZATION

Every provider must catch its own SDK exceptions and re-raise as `TeletraanAIError`:

```python
class TeletraanAIError(TeletraanBaseException):
    def __init__(
        self,
        message: str,
        provider: str,
        is_retryable: bool = True,
        is_quota_exceeded: bool = False,
        is_content_filtered: bool = False,
    ): ...
```

Provider error mapping examples:
- Gemini `ResourceExhausted` → `is_quota_exceeded=True, is_retryable=False`
- OpenAI `RateLimitError` → `is_retryable=True`
- Anthropic `OverloadedError` → `is_retryable=True`
- Any `ConnectionError` → `is_retryable=True`
- Content filter/safety block → `is_content_filtered=True, is_retryable=False`

---

## RETRY LOGIC

Wrap all provider calls in tenacity retry:
- Max attempts: 3
- Wait: exponential backoff (2^n seconds, max 30 seconds)
- Retry on: `is_retryable=True` TeletraanAIError only
- Do NOT retry: quota exceeded, content filtered, auth failures

---

## FALLBACK CHAIN

In `app/ai/factory.py`:

```python
async def generate_with_fallback(system_prompt, messages, ...):
    primary = get_provider(settings.ACTIVE_AI_PROVIDER)
    try:
        return await primary.generate_text(system_prompt, messages, ...)
    except TeletraanAIError as e:
        if not settings.AI_FALLBACK_PROVIDER or e.is_content_filtered:
            raise
        logger.warning("ai.primary_failed_trying_fallback", provider=primary.get_provider_name())
        fallback = get_provider(settings.AI_FALLBACK_PROVIDER)
        return await fallback.generate_text(system_prompt, messages, ...)
```

If both fail: do NOT raise. Return a `TeletraanAIError` flag to caller.
Caller uses rule-based template instead. Bot continues functioning.

---

## VOICE PIPELINE (app/ai/voice.py)

Complete pipeline from WhatsApp voice message to confirmed transcription:

```
1. Receive media_id from WhatsApp webhook
2. Call WhatsApp API to get temporary media URL
3. Download audio bytes with auth header
4. Convert .ogg (Opus) → .wav using pydub:
   AudioSegment.from_ogg(io.BytesIO(ogg_bytes)).export(output, format="wav")
5. Get STT provider: factory.get_stt_provider()
6. Call provider.transcribe_audio(wav_bytes, "audio/wav", language_hint="ur")
7. Return AITranscriptionResponse
8. Caller shows transcription to customer for confirmation
```

Language hint logic:
- Default: "ur" (Urdu)
- If customer language_preference = "english": hint "en"
- If customer language_preference = "roman_urdu": hint "ur" (best for Roman Urdu audio)

Confidence mapping:
- If transcription.text is empty or less than 3 words: set confidence="low"
- If provider returns confidence score: map to high/medium/low thresholds
- If provider doesn't return confidence: set "medium" as default

---

## PROMPT ENGINEERING STANDARDS

All prompts live in `app/ai/prompts/`. They are Python string constants — not files.

System prompt structure for Channel A:
```
[ROLE]
You are TELETRAAN, the WhatsApp order assistant for {distributor_name}
operating in {distributor_city}, Pakistan.

[LANGUAGE]
Respond in: {language}. For Roman Urdu, use natural conversational Pakistani style.

[DISTRIBUTOR CONTEXT]
Business: {business_name}
Current catalog: {catalog_summary}  ← 2-3 sentence summary, not full catalog
Custom instructions: {custom_suffix}

[BEHAVIOR RULES]
- You process medicine orders for retailers and chemists
- Extract medicine names, quantities, and units from customer messages
- Never invent medicines not in the catalog summary
- When unsure about a medicine name, ask for clarification
- Keep responses concise — this is WhatsApp, not email
- Never use markdown formatting (no **, no #, no -)

[OUTPUT FORMAT]
Return structured JSON for entity extraction. Return plain text for customer messages.
```

ANTI-PROMPT-INJECTION: Before including any user content in a prompt:
```python
def sanitize_for_prompt(text: str) -> str:
    # Remove common injection patterns
    dangerous_patterns = [
        "ignore previous instructions",
        "ignore all previous",
        "you are now",
        "new instructions:",
        "system:",
        "[system]",
        "{{",
        "}}",
    ]
    cleaned = text
    for pattern in dangerous_patterns:
        cleaned = cleaned.replace(pattern, "[removed]")
    # Limit length
    return cleaned[:1500]
```

---

## CONTEXT WINDOW MANAGEMENT

Conversation history is stored in `sessions.conversation_history` as JSONB.
Keep last 15 turns (30 messages: 15 user + 15 assistant).

For orders with many items (8+ items), generate `ai_context_summary`:
```python
# Ask AI to summarize the order so far in 2 sentences
# Store in pending_order_draft.ai_context_summary
# Inject this summary instead of full history to save tokens on long orders
```

Token budget awareness:
- Estimate input tokens before calling (use character count / 4 as rough estimate)
- If estimated input > 80% of model's context limit: trim oldest conversation turns
- Always preserve last 3 turns regardless of length

---

## ANALYTICS TRACKING

Every AI call must log to analytics_events:
```python
await analytics_repo.log_event(
    distributor_id=distributor_id,
    event_type="ai.text_generation",
    properties={
        "provider": provider.get_provider_name(),
        "model": provider.get_model_name(),
        "intent": detected_intent,
        "tokens_in": response.tokens_used_input,
        "tokens_out": response.tokens_used_output,
    },
    ai_provider=provider.get_provider_name(),
    ai_tokens_used=response.tokens_used_input + response.tokens_used_output,
    ai_cost_paisas=response.estimated_cost_paisas,
    duration_ms=elapsed_ms,
)
```

---

## ADDING A NEW PROVIDER IN THE FUTURE

1. Create `app/ai/providers/new_provider.py`
2. Implement all AIProvider abstract methods
3. Add to factory.py PROVIDER_MAP
4. Add API key env var to config.py as Optional
5. Add to .env.example
6. Write unit tests with mocked SDK responses
7. Update docs/ai_providers.md
8. Commit with scope `ai:`

Zero changes to NLU, response generator, or voice pipeline.
