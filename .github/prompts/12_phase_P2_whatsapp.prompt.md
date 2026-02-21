# Phase 2 — WhatsApp API Integration

**Prerequisites:** Phase 1 complete and verified.
**Verify before P3:** Webhook verification passing in Meta console, real message received and reply sent successfully.

## Steps (execute in order, commit after each)

1. Implement `app/whatsapp/message_types.py` — payload builders for all Meta API message types  
   (text, interactive buttons, list, template, media, reaction, location)  
   → Commit: `"whatsapp: add message payload builders for all Meta API message types"`

2. Implement `app/whatsapp/client.py` — async Meta Cloud API client, retry with tenacity, rate limit tracking  
   → Commit: `"whatsapp: implement async Meta Cloud API client with retry and rate limit tracking"`

3. Implement `app/whatsapp/parser.py` — webhook payload parser for all incoming message types  
   (text, voice, image, button reply, list reply, template reply, location, contact)  
   → Commit: `"whatsapp: add webhook payload parser for all incoming message types"`

4. Implement `app/whatsapp/media.py` — media download from Meta CDN, Supabase Storage upload  
   → Commit: `"whatsapp: add media download and Supabase Storage upload handlers"`

5. Implement `app/api/webhook.py` — Meta webhook GET verify + POST receive, HMAC verification before any processing  
   → Commit: `"api: add Meta webhook handler with HMAC verification and message routing"`

6. Implement `app/channels/router.py` — message routing by `phone_number_id`, distributor resolution, channel dispatch  
   → Commit: `"channels: implement message router with distributor resolution and channel dispatch"`

7. Implement `app/notifications/templates/` — all three language template files (urdu, english, roman_urdu)  
   → Commit: `"notifications: add all three language template files (urdu, english, roman_urdu)"`

8. Implement `app/notifications/whatsapp_notifier.py` — send wrapper with notification logging, retry, delivery tracking  
   → Commit: `"notifications: implement send wrapper with logging, retry, and delivery tracking"`

9. Test webhook verification with Meta console — test real message receive and reply  
   → Commit: `"test: verify end-to-end webhook receive and text reply working"`

10. Write unit tests for `parser.py` and `message_types.py`  
    → Commit: `"tests: add unit tests for webhook parser and message type builders"`

11. **PHASE 2 COMPLETE** Commit: `"phase-2: WhatsApp API integration complete, verified end-to-end"`
