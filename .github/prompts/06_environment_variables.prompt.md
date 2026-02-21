# TELETRAAN Environment Variables — Complete Reference

All variables belong in `.env` only. Never in source code.
`.env` is gitignored. `.env.example` has all names with descriptions but NO real values.

---

## Application
| Variable | Values / Default | Description |
|---|---|---|
| `APP_ENV` | development, staging, production | |
| `APP_HOST` | `0.0.0.0` | |
| `APP_PORT` | `8000` | |
| `APP_SECRET_KEY` | — | 64-char random string for internal signing |
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR | |
| `ENCRYPTION_KEY` | — | Fernet key for CNIC/sensitive fields — generate with `Fernet.generate_key()` |
| `ADMIN_API_KEY` | — | X-Admin-Key header value for admin endpoints |

---

## Meta WhatsApp API
| Variable | Description |
|---|---|
| `META_APP_ID` | |
| `META_APP_SECRET` | |
| `META_VERIFY_TOKEN` | You define this — used for webhook verification |
| `META_API_VERSION` | default: `v19.0` |
| `META_API_BASE_URL` | default: `https://graph.facebook.com` |
| `OWNER_PHONE_NUMBER_ID` | Meta Phone Number ID for Channel B owner SIM |
| `OWNER_WHATSAPP_NUMBER` | E.164 format owner number |

---

## AI Providers
| Variable | Values / Default | Description |
|---|---|---|
| `ACTIVE_AI_PROVIDER` | gemini, openai, anthropic, cohere, openrouter | |
| `ACTIVE_STT_PROVIDER` | gemini, whisper | Defaults to ACTIVE_AI_PROVIDER if compatible |
| `AI_TEXT_MODEL` | — | Override default model for chosen provider |
| `AI_PREMIUM_MODEL` | — | Premium model for complex reasoning tasks |
| `AI_MAX_TOKENS` | `2048` | |
| `AI_TEMPERATURE` | `0.30` | |
| `AI_FALLBACK_PROVIDER` | — | Fallback if primary provider fails |
| `GEMINI_API_KEY` | — | |
| `OPENAI_API_KEY` | — | |
| `ANTHROPIC_API_KEY` | — | |
| `COHERE_API_KEY` | — | |
| `OPENROUTER_API_KEY` | — | |
| `OPENROUTER_MODEL` | — | e.g., `meta-llama/llama-3.1-8b-instruct` |

---

## Supabase
| Variable | Description |
|---|---|
| `SUPABASE_URL` | |
| `SUPABASE_SERVICE_KEY` | Service role — full access — NEVER expose client-side |
| `SUPABASE_ANON_KEY` | |

---

## Payment Gateways
| Variable | Values / Default | Description |
|---|---|---|
| `ACTIVE_PAYMENT_GATEWAY` | jazzcash, easypaisa, safepay, nayapay, bank_transfer, dummy | |
| `PAYMENT_CALLBACK_BASE_URL` | — | Public HTTPS URL for gateway callbacks |
| `PAYMENT_LINK_EXPIRY_MINUTES` | `60` | |
| `JAZZCASH_MERCHANT_ID` | — | |
| `JAZZCASH_PASSWORD` | — | |
| `JAZZCASH_INTEGRITY_SALT` | — | |
| `JAZZCASH_API_URL` | — | |
| `EASYPAISA_STORE_ID` | — | |
| `EASYPAISA_HASH_KEY` | — | |
| `EASYPAISA_API_URL` | — | |
| `SAFEPAY_API_KEY` | — | |
| `SAFEPAY_SECRET_KEY` | — | |
| `SAFEPAY_API_URL` | `https://api.getsafepay.com` | |
| `SAFEPAY_WEBHOOK_SECRET` | — | |
| `NAYAPAY_MERCHANT_ID` | — | |
| `NAYAPAY_API_KEY` | — | |
| `NAYAPAY_SECRET` | — | |
| `NAYAPAY_API_URL` | — | |
| `BANK_ACCOUNT_NAME` | — | |
| `BANK_ACCOUNT_NUMBER` | — | |
| `BANK_IBAN` | — | |
| `BANK_NAME` | — | |
| `BANK_BRANCH` | — | |
| `DUMMY_GATEWAY_AUTO_CONFIRM` | true, false | Dev only — blocked in production |
| `DUMMY_GATEWAY_CONFIRM_DELAY_SECONDS` | `10` | |

---

## Scheduler
| Variable | Default | Description |
|---|---|---|
| `SCHEDULER_TIMEZONE` | `Asia/Karachi` | |
| `INVENTORY_SYNC_INTERVAL_MINUTES` | `120` | |
| `SESSION_CLEANUP_INTERVAL_HOURS` | `6` | |
| `REMINDER_CHECK_INTERVAL_HOURS` | `12` | |

---

## Feature Flags
| Variable | Default | Description |
|---|---|---|
| `ENABLE_VOICE_PROCESSING` | `true` | |
| `ENABLE_INVENTORY_SYNC` | `true` | |
| `ENABLE_EXCEL_REPORTS` | `true` | |
| `ENABLE_PDF_CATALOG` | `true` | |
| `ENABLE_CHANNEL_B` | `true` | |
| `ENABLE_ANALYTICS` | `true` | |
| `ENABLE_CREDIT_ACCOUNTS` | `false` | |

---

## Email
| Variable | Default | Description |
|---|---|---|
| `RESEND_API_KEY` | — | Resend.com for Excel report delivery |
| `EMAIL_FROM_ADDRESS` | `noreply@teletraan.pk` | |
