# Phase 3 — AI Engine (Multi-Provider)

**Prerequisites:** Phase 2 complete and verified.
**Verify before P4:** NLU tested with 20+ samples in all languages, voice pipeline tested with both STT providers.

## Steps (execute in order, commit after each)

1. Implement `app/ai/base.py` — abstract `AIProvider` base class with full interface contract  
   See `08_ai_provider_abstraction.prompt.md` for all required methods and response types  
   → Commit: `"ai: define abstract AIProvider base class with full interface contract"`

2. Implement `app/ai/providers/gemini_provider.py` — Gemini text + native audio transcription  
   → Commit: `"ai: implement Gemini provider for text and native audio transcription"`

3. Implement `app/ai/providers/openai_provider.py` — GPT text + Whisper STT  
   → Commit: `"ai: implement OpenAI provider with GPT text and Whisper STT"`

4. Implement `app/ai/providers/anthropic_provider.py` — Claude text + Whisper STT fallback  
   → Commit: `"ai: implement Anthropic Claude provider with Whisper STT fallback"`

5. Implement `app/ai/providers/cohere_provider.py` — Cohere text + Whisper STT fallback  
   → Commit: `"ai: implement Cohere provider with Whisper STT fallback"`

6. Implement `app/ai/providers/openrouter_provider.py` — OpenRouter via OpenAI-compatible REST API  
   → Commit: `"ai: implement OpenRouter proxy provider via OpenAI-compatible API"`

7. Implement `app/ai/factory.py` — provider factory with env-driven selection, fallback chain  
   See `08_ai_provider_abstraction.prompt.md` for fallback behavior  
   → Commit: `"ai: implement provider factory with env-driven selection and fallback chain"`

8. Implement all prompts in `app/ai/prompts/` — `order_bot_prompts.py`, `sales_bot_prompts.py`, `system_prompts.py`  
   See `14_teletraan_persona.instructions.md` and `15_teletraan_system_prompts.instructions.md`  
   → Commit: `"ai: add all system prompts for Channel A, Channel B, and shared utilities"`

9. Implement `app/ai/nlu.py` — intent classification, entity extraction, Roman Urdu normalization  
   → Commit: `"ai: implement NLU with intent classification, entity extraction, and Roman Urdu normalization"`

10. Implement `app/ai/voice.py` — voice pipeline: `.ogg` download → pydub conversion → route to STT provider  
    → Commit: `"ai: implement voice pipeline with ogg download, conversion, and multi-provider STT"`

11. Implement `app/ai/response_generator.py` — multi-language response generation using provider factory  
    → Commit: `"ai: implement multi-language response generation with provider abstraction"`

12. Test NLU with 20+ sample messages across Urdu, English, Roman Urdu  
    → Commit: `"tests: add unit tests for NLU with mocked AI provider responses"`

13. Test voice pipeline end-to-end with Gemini and OpenAI Whisper  
    → Commit: `"tests: verify voice pipeline works with both STT providers"`

14. **PHASE 3 COMPLETE** Commit: `"phase-3: AI engine complete with 5 providers, NLU, voice pipeline tested"`
