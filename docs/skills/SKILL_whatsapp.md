# SKILL: WhatsApp API Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before implementing any WhatsApp integration code.

---

## IDENTITY

This skill defines all rules for interacting with the Meta WhatsApp Cloud API.
WhatsApp is the primary interface for all end-users. Getting this layer wrong
means silent failures, banned numbers, and broken conversations. Every rule here
exists because of a documented Meta policy or a known production failure mode.

---

## META CLOUD API — KEY FACTS

- API Version: v19.0 (pinned via `META_API_VERSION` env var)
- Base URL: `https://graph.facebook.com/{version}`
- Send endpoint: `/v19.0/{phone_number_id}/messages`
- Media endpoint: `/v19.0/{media_id}`
- Auth: Bearer token using `META_APP_SECRET` (page access token)
- Webhook: Your public HTTPS endpoint, registered in Meta App Dashboard

---

## WEBHOOK SETUP

### Verification (GET)
Meta sends `GET /webhook?hub.mode=subscribe&hub.challenge=XXXX&hub.verify_token=YOUR_TOKEN`
Your endpoint must:
1. Check `hub.verify_token` matches `META_VERIFY_TOKEN` env var
2. Return `hub.challenge` as plain text response with 200

### Receiving messages (POST)
Meta sends `POST /webhook` with JSON payload.
Your endpoint must:
1. **Immediately** verify HMAC-SHA256 signature (see SECURITY_PROTOCOL.md)
2. Return 200 within 5 seconds — or Meta will retry
3. Process message asynchronously (spawn task, don't block)
4. Deduplicate by message ID (ignore replayed webhooks)
5. Handle status updates (read receipts) separately from message events

### CRITICAL: Always return 200 to payment/webhook callbacks
Even if processing fails — log the error, return 200. Returning non-200 causes
Meta (and payment gateways) to retry indefinitely, creating duplicate processing.
Handle idempotency on your side.

---

## MESSAGE TYPES — INCOMING

Parser must handle all of these in `app/whatsapp/parser.py`:

| type field | When received | Action |
|---|---|---|
| `text` | Standard text message | Extract `body` string |
| `audio` | Voice message (.ogg) | Extract `id` for media download |
| `image` | Photo (e.g., complaint photo) | Extract `id` for media download |
| `interactive` with `type: button_reply` | Button tapped | Extract `button_reply.id` |
| `interactive` with `type: list_reply` | List item selected | Extract `list_reply.id` |
| `sticker` | Sticker sent | Send polite "I only understand text/voice" message |
| `location` | Location pin | Not used — send guidance |
| `contacts` | Contact card | Not used — send guidance |
| `reaction` | Emoji reaction | Ignore silently |
| `unsupported` | Unknown type | Send "I couldn't understand that" message |

Status updates in `statuses[]` array:
- `sent`, `delivered`, `read` → update `notifications_log.delivery_status`
- `failed` → log error, flag for retry

---

## MESSAGE TYPES — OUTBOUND

All builders in `app/whatsapp/message_types.py`.

### Text message
Plain text only. No markdown — WhatsApp does not render `**bold**` or `_italic_`
in API-sent messages. Use Unicode characters (✅ ⚠️ 📦) for visual structure.
Max length: 4096 characters.

### Interactive — Buttons (up to 3 buttons)
```json
{
  "type": "interactive",
  "interactive": {
    "type": "button",
    "body": {"text": "Main message text"},
    "action": {
      "buttons": [
        {"type": "reply", "reply": {"id": "confirm_order", "title": "✅ Confirm"}},
        {"type": "reply", "reply": {"id": "edit_order", "title": "✏️ Edit"}}
      ]
    }
  }
}
```
Button `id` max 256 chars. Button `title` max 20 chars.
Use stable, descriptive IDs (not sequential numbers) — they arrive in webhook.

### Interactive — List (up to 10 items, grouped in sections)
```json
{
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": {"text": "Choose a medicine:"},
    "action": {
      "button": "Dekho Options",
      "sections": [
        {
          "title": "Best Matches",
          "rows": [
            {"id": "catalog_uuid_1", "title": "Paracetamol 500mg", "description": "Strip — PKR 35"}
          ]
        }
      ]
    }
  }
}
```
List button text max 20 chars. Row title max 24 chars. Row description max 72 chars.
Section title max 24 chars. Max 10 rows across all sections.

### Document (PDF send)
```json
{
  "type": "document",
  "document": {
    "link": "https://signed-url-to-pdf",
    "filename": "Al-Shifa-Catalog-Feb-2025.pdf"
  }
}
```
Use Supabase Storage signed URL (1 hour validity). File must be publicly accessible.

### Template message
Required for business-initiated conversations outside the 24-hour window.
Templates must be pre-approved by Meta. Use for payment reminders, subscription notices.
Never send bulk templates without checking Meta's rate limits and policy.

---

## BUSINESS-INITIATED CONVERSATIONS — POLICY

Meta allows free messages within a 24-hour window after the customer last messaged.
After 24 hours — you must use an approved template message.

### For distributor subscription reminders (business-initiated):
Must use approved template. Register templates in Meta Business Manager.
`TELETRAAN_payment_reminder_7d`, `TELETRAAN_payment_reminder_1d`, etc.

### Individual vs Broadcast:
NEVER use WhatsApp Broadcast API for sending to customers or distributors.
Always send individual messages via the `/messages` endpoint per recipient.
Broadcast violates Meta policy and will result in number suspension.

---

## PHONE NUMBER MANAGEMENT

### Multi-number architecture
One Meta App → multiple phone numbers registered.
Each distributor's SIM is registered as a separate phone number under the same app.
`phone_number_id` (not the actual phone number) identifies which SIM a message came from.

### Routing by phone_number_id
Incoming webhook includes `metadata.phone_number_id`.
Look up distributor in DB by `whatsapp_phone_number_id` column.
Route to Channel A.
If phone_number_id matches `OWNER_PHONE_NUMBER_ID` — route to Channel B.

### Number warm-up
New numbers should not send hundreds of messages on day one.
Gradually increase: 10/day → 50/day → 200/day → scale up over 2-3 weeks.
Rapid sudden volume = suspicious = potential number quality downgrade or ban.

---

## RATE LIMITS AND ERROR HANDLING

### Meta API rate limits
- 80 messages per second per phone number (normal limit)
- 1,000 free service conversations per month per number (after: pay per conversation)

### Rate limit response
Meta returns HTTP 429 with `error.code = 130429` (too many requests).
On 429: wait `Retry-After` header seconds, then retry with tenacity.

### Common error codes to handle
| Code | Meaning | Action |
|---|---|---|
| 130429 | Rate limit hit | Retry after backoff |
| 131026 | Message undeliverable (number not on WhatsApp) | Log, mark customer as invalid |
| 131047 | 24hr window expired, need template | Switch to template message |
| 131051 | Unsupported message type | Log and skip |
| 100 | Invalid parameter | Log error with full payload for debugging |

### Retry logic with tenacity
Max 3 retries. Exponential backoff: 1s, 2s, 4s.
Only retry on 429 (rate limit) and 5xx (server errors).
Never retry on 4xx client errors (invalid parameter, auth failure).

---

## MEDIA HANDLING

### Download media
1. Receive media message with `media_id`
2. `GET /v19.0/{media_id}` with Authorization header → returns `{url, mime_type, sha256, ...}`
3. `GET {url}` with Authorization header → returns media bytes
4. Upload bytes to Supabase Storage immediately
5. Return Supabase Storage path/URL for further processing

### Audio specifically (.ogg Opus codec)
WhatsApp voice messages arrive as `audio/ogg; codecs=opus`.
Convert to WAV with pydub + ffmpeg before sending to AI provider.
Never save audio files permanently — process in memory, discard after transcription.
Max voice message length: 60 seconds. Reject longer messages gracefully.

### Images for complaints
Download image, upload to Supabase Storage under:
`{distributor_id}/complaints/{complaint_id}/{filename}`
Store Supabase URL in `complaints.media_urls` array.
Never store raw image bytes in database.

---

## DEDUPLICATION

Meta may deliver the same webhook multiple times (at-least-once delivery).
Deduplicate using `message.id` (WhatsApp message ID).
On receiving a message:
1. Check if `message.id` already in recent processing cache (TTLCache, 1 hour)
2. If present → return 200 immediately, do not process
3. If not present → add to cache, process normally

Cache implementation: in-memory `cachetools.TTLCache(maxsize=10000, ttl=3600)`.
This survives short restarts. For multi-process deployments: move to Redis/Supabase.

---

## READ RECEIPTS

Send read receipt after processing every customer message:
```json
{
  "messaging_product": "whatsapp",
  "status": "read",
  "message_id": "{message_id}"
}
```
Send this to `/{phone_number_id}/messages` after successful processing.
This shows the customer their message was received. Improves UX significantly.
