# TELETRAAN — Project Identity and Technology Stack

## Project Identity
- **System Name:** TELETRAAN
- **Tagline:** Aapka Distributor, Hamara Kaam
- **Type:** WhatsApp Intelligent Order and Operations Automation System
- **Sector:** Medicine Distribution — Pakistan
- **Deployment Target:** Render (primary) / Railway (secondary)
- **Language:** Python 3.11+
- **Version:** 2.0.0

---

## Core Stack
| Package | Version | Role |
|---|---|---|
| Python | 3.11+ | Primary language |
| FastAPI | 0.111+ | Async web framework and webhook server |
| Uvicorn | 0.29+ | ASGI server (gunicorn in production) |
| Pydantic | 2.x | Data validation, settings management, all model definitions |

---

## AI Providers (all behind abstract base — see 08_ai_provider_abstraction.prompt.md)
Factory reads `ACTIVE_AI_PROVIDER` from env. Text and voice configurable independently.

| ID | Name | SDK | Text Model | Audio |
|---|---|---|---|---|
| `gemini` | Google Gemini | google-generativeai 0.7+ | gemini-1.5-flash | Native audio input |
| `openai` | OpenAI | openai 1.x | gpt-4o-mini / gpt-4o | whisper-1 |
| `anthropic` | Anthropic Claude | anthropic 0.25+ | claude-3-haiku / claude-3-5-sonnet | Route to Whisper |
| `cohere` | Cohere | cohere 5.x | command-r / command-r-plus | Not supported |
| `openrouter` | OpenRouter | httpx (OpenAI-compatible REST) | OPENROUTER_MODEL env var | Not supported |

**AI Env Vars:**
- `ACTIVE_AI_PROVIDER` — ENUM: gemini, openai, anthropic, cohere, openrouter
- `ACTIVE_STT_PROVIDER` — ENUM: gemini, whisper (defaults to ACTIVE_AI_PROVIDER if compatible)
- `AI_TEXT_MODEL` — override default model for chosen provider
- `AI_PREMIUM_MODEL` — premium model for complex reasoning (intent ambiguity, conflict resolution)

---

## Payment Gateways (all behind abstract base — see 09_payment_gateway_abstraction.prompt.md)
Factory reads `ACTIVE_PAYMENT_GATEWAY`. Multiple gateways active simultaneously.

| ID | Name | Type | Auth | Callback Path |
|---|---|---|---|---|
| `jazzcash` | JazzCash | Mobile money — Pakistan | HMAC-SHA256 | `/api/payments/jazzcash/callback` |
| `easypaisa` | EasyPaisa | Mobile money — Pakistan | HMAC per spec | `/api/payments/easypaisa/callback` |
| `safepay` | SafePay | Card + digital | Bearer + HMAC webhook | `/api/payments/safepay/callback` |
| `nayapay` | NayaPay | Digital wallet, QR | API key + signing | `/api/payments/nayapay/callback` |
| `bank_transfer` | Bank Transfer | Manual + screenshot | Manual owner approval | N/A |
| `dummy` | Dummy Gateway | Dev/test only | Internal | `/api/payments/dummy/callback` |

**SafePay Notes:** Visa, Mastercard, UnionPay, mobile wallets. Hosted checkout URL. Best for card payments.  
**NayaPay Notes:** QR code payments. Implement initiation + QR URL + webhook confirmation.  
**Bank Transfer Notes:** Bot sends account details → customer sends screenshot → owner confirms → subscription extended.  
**Dummy Notes:** Auto-confirm after delay; amounts ending in 99 paisas = auto-fail; expires in 15min. BLOCKED in production.

**Payment Env Vars:**
- `ACTIVE_PAYMENT_GATEWAY` — ENUM: jazzcash, easypaisa, safepay, nayapay, bank_transfer, dummy
- `PAYMENT_CALLBACK_BASE_URL` — public HTTPS URL for gateway callbacks
- `PAYMENT_LINK_EXPIRY_MINUTES` — default 60

---

## Database
| Package | Version | Role |
|---|---|---|
| Supabase | — | PostgreSQL DB, RLS, Storage, Realtime |
| supabase-py | 2.x | Primary Python SDK |
| asyncpg | latest | Async PostgreSQL driver for complex queries |

---

## WhatsApp
| Package | Version | Role |
|---|---|---|
| Meta Cloud API | v19.0 | WhatsApp Business API — all message types |
| httpx | 0.27+ | Async HTTP client for all outbound calls |

---

## Audio Processing
| Package | Role |
|---|---|
| pydub | Audio format conversion (.ogg → .wav/.mp3) |
| ffmpeg | Audio codec backend — must be installed on server |

---

## Document Generation
| Package | Version | Role |
|---|---|---|
| openpyxl | 3.x | Excel (.xlsx) order log generation |
| reportlab | latest | PDF catalog and order receipt generation |
| Pillow | latest | Image processing for catalog image generation |

---

## Utilities
| Package | Role |
|---|---|
| rapidfuzz 3.x | Fuzzy medicine name matching |
| APScheduler 3.x | Background job scheduling |
| loguru | Structured logging with rotation |
| python-dotenv | Environment variable management |
| pytest 8.x | Test framework |
| pytest-asyncio | Async test support |
| pytest-cov | Coverage reporting |
| tenacity | Retry logic for all external API calls |
| cachetools | In-memory TTL cache for catalog and distributor lookups |
| pytz | Pakistan Standard Time handling |
| cryptography | Fernet symmetric encryption for sensitive fields |
| phonenumbers | Pakistan phone number validation and E.164 normalization |
| pre-commit | Git hooks: black, isort, flake8 |
| black | Code formatter |
| isort | Import sorter |
| flake8 | Linter |

---

## Hosting
| Platform | Role |
|---|---|
| Render | Primary — always-on Python web service |
| Railway | Secondary/backup hosting |
| Supabase Storage | Files: Excel, PDFs, voice recordings, screenshots |
