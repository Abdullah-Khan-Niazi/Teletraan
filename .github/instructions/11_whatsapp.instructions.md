---
applyTo: "app/whatsapp/**,app/**/*whatsapp*.py,app/**/*webhook*.py,app/**/*parser*.py"
---

# SKILL 11 — WHATSAPP API
## Source: `docs/skills/SKILL_whatsapp.md`

---

## META CLOUD API ESSENTIALS

- API Version: `v19.0` (pinned via `META_API_VERSION` env var)
- Send endpoint: `https://graph.facebook.com/v19.0/{phone_number_id}/messages`
- Auth: Bearer token using page access token from `META_APP_SECRET`
- Webhook: HTTPS endpoint registered in Meta App Dashboard

---

## WEBHOOK HANDLER RULES

1. **Verify HMAC-SHA256 signature FIRST** — see `05_security.instructions.md`
2. **Return 200 within 5 seconds** — process asynchronously (spawn background task)
3. **Deduplicate by message ID** — store processed message IDs, ignore replays
4. **Handle status updates** (`sent`, `delivered`, `read`, `failed`) separately from messages
5. **Always return 200** — even on internal errors (non-200 causes Meta to retry → duplicates)

### Webhook GET (verification)
```python
@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> Response:
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403)
```

---

## INCOMING MESSAGE TYPES (app/whatsapp/parser.py)

| type | Action |
|---|---|
| `text` | Extract `body` string |
| `audio` | Extract `id` → download media → transcribe |
| `image` | Extract `id` → download media |
| `interactive.button_reply` | Extract `button_reply.id` |
| `interactive.list_reply` | Extract `list_reply.id` |
| `sticker`, `location`, `contacts` | Send guidance message |
| `reaction` | Ignore silently |
| `unsupported` | Send "I couldn't understand that" |

---

## OUTBOUND MESSAGE BUILDERS (app/whatsapp/message_types.py)

### Text message
```python
def build_text_message(to: str, body: str) -> dict:
    """Max 4096 chars. No markdown — use Unicode (✅ ⚠️ 📦) for structure."""
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
```

### Interactive buttons (up to 3)
```python
def build_button_message(to: str, body: str, buttons: list[tuple[str, str]]) -> dict:
    """buttons = [(id, title), ...]. title max 20 chars. id max 256 chars."""
    return {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "button", "body": {"text": body},
            "action": {"buttons": [{"type": "reply", "reply": {"id": bid, "title": btitle}} for bid, btitle in buttons]},
        },
    }
```

### Interactive list (up to 10 rows per section)
```python
def build_list_message(to: str, body: str, button_label: str, sections: list[dict]) -> dict: ...
```

### Template message (for business-initiated messages)
```python
def build_template_message(to: str, template_name: str, lang_code: str, parameters: list[dict]) -> dict: ...
```

---

## WHATSAPP API CLIENT (app/whatsapp/client.py)

```python
class WhatsAppClient:
    async def send_message(self, payload: dict) -> str:
        """Send message, return message_id. Raises WhatsAppAPIError on failure."""
        # POST to send endpoint, handle 429 with retry, log result

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Download media bytes and return (bytes, mime_type)."""
        # GET media URL first, then download bytes

    async def mark_as_read(self, message_id: str) -> None:
        """Send read receipt for message_id."""
```

---

## NUMBER FORMATTING

All phone numbers stored and sent in E.164 format: `+923001234567`
Validate on incoming webhook — normalize before any processing.
Never pass unnormalized numbers to any downstream service.

---

## ANTI-SPAM POLICY

- **Never use WhatsApp broadcast** — use API-triggered individual messages only
- Warm up new numbers gradually (start low volume, increase over 30 days)
- Respect rate limits: 1000 conversations/day/number (free tier)
- Business-initiated messages require approved templates — use them
