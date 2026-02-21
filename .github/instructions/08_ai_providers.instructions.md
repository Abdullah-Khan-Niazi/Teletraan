---
applyTo: "app/ai/**,app/**/ai/**,app/**/*provider*.py,app/**/*nlu*.py"
---

# SKILL 08 — AI PROVIDERS
## Source: `docs/skills/SKILL_ai_providers.md`

---

## ARCHITECTURE

```
NLU / Response Generator / Voice Pipeline
             ↓
    ai_factory.get_provider()
             ↓
       AIProvider (abstract base)
             ↓
[gemini | openai | anthropic | cohere | openrouter]
```

Text and voice configured independently:
- `ACTIVE_AI_PROVIDER` → text generation + NLU
- `ACTIVE_STT_PROVIDER` → speech-to-text (can differ)

---

## ABSTRACT BASE CLASS (app/ai/base.py)

Every provider must implement:

```python
class AIProvider(ABC):
    @abstractmethod
    async def generate_text(
        self,
        system_prompt: str,
        messages: list[dict],  # [{"role": "user/assistant", "content": "..."}]
        temperature: float = 0.3,
        max_tokens: int = 2048,
        use_premium_model: bool = False,
    ) -> AITextResponse: ...

    @abstractmethod
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,       # e.g., "audio/ogg"
        language_hint: str,   # e.g., "ur"
    ) -> AITranscriptionResponse: ...

    @abstractmethod
    async def estimate_cost(self, tokens_in: int, tokens_out: int) -> int: ...
    # Returns estimated cost in paisas

    @abstractmethod
    def get_provider_name(self) -> str: ...

    @abstractmethod
    def get_model_name(self, premium: bool = False) -> str: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

---

## RESPONSE MODELS

```python
class AITextResponse(BaseModel):
    content: str
    tokens_used_input: int
    tokens_used_output: int
    finish_reason: str            # "stop", "max_tokens", "error"
    raw_response: dict            # Full provider response for debugging
    estimated_cost_paisas: int

class AITranscriptionResponse(BaseModel):
    text: str
    confidence: str               # "high", "medium", "low"
    language_detected: str        # ISO 639-1 code
    duration_seconds: float
    raw_response: dict
```

---

## FACTORY (app/ai/factory.py)

```python
def get_ai_provider() -> AIProvider:
    """Return the configured AI provider singleton."""
    settings = get_settings()
    match settings.active_ai_provider:
        case "gemini":
            return GeminiProvider()
        case "openai":
            return OpenAIProvider()
        case _:
            raise ConfigurationError(f"Unknown AI provider: {settings.active_ai_provider}")
```

Default provider: Gemini 1.5 Flash — cheapest, handles Urdu/Roman Urdu well.

---

## USAGE TRACKING

Every AI call must be logged to `ai_usage_log` table:
- `distributor_id`, `provider`, `model`, `tokens_in`, `tokens_out`
- `cost_paisas`, `operation_type` (nlu/response/transcription), `latency_ms`

---

## PROMPT INJECTION GUARD

Before every AI call, user content must pass through `sanitize_for_prompt()`.
See `05_security.instructions.md` for implementation.

---

## COST MANAGEMENT

- Default to flash/mini models (temperature 0.3 for extraction, 0.7 for conversation)
- Use premium model (`use_premium_model=True`) only when explicitly triggered
- Log cost estimate on every AI call
- Per-distributor monthly spend limit: configurable in distributor settings
