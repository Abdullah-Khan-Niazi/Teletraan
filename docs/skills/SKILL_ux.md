# UX & CONVERSATION DESIGN SKILL
## SKILL: ux | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines the user experience design standards for TELETRAAN —
how conversations flow, how information is structured for WhatsApp,
how errors feel to the customer, and what makes the bot feel trustworthy
versus frustrating.

UX in a WhatsApp bot is not a visual design problem. It is a conversation
design problem. The quality of UX is measured by: how many messages does
a customer need to complete their order, and how many times do they feel
confused.

---

## CORE UX PRINCIPLES

### PRINCIPLE 1 — ONE MESSAGE, ONE PURPOSE
Every bot message does one thing. Either it asks one question, OR it
confirms one action, OR it shows one piece of information. Never combine
an ask, a confirm, and a summary in one message.

```
WRONG (three things in one message):
"Aapka paracetamol add ho gaya! Koi aur cheez? Agar confirm karna ho to
CONFIRM likhein. Aur delivery address bhi bata dain."

CORRECT (one thing):
"Paracetamol 500mg × 10 strips add ho gaya ✅
Koi aur medicine chahiye?"
```

### PRINCIPLE 2 — NEVER MAKE THE CUSTOMER GUESS
The next action must always be explicit. The customer should never be
wondering "ab kya karna hai?" After every bot message, the path forward
is obvious.

```
CORRECT endings:
"Koi aur cheez chahiye? Ya bill dekhna hai?"
"Confirm karna ho to *CONFIRM* likhein 👆"
"Haan ya nahi?"
"1 likhein JazzCash ke liye, 2 likhein EasyPaisa ke liye"
```

### PRINCIPLE 3 — CONFIRM BEFORE WRITING
TELETRAAN never writes data (order items, confirmed orders) without
explicit customer confirmation. The confirmation flow is:
1. Bot shows what it understood
2. Customer confirms or corrects
3. Bot writes to DB only after confirmation

```
After entity extraction:
"*Brufen 400mg* — 10 strips?
Haan/Nahi?"

After customer says haan:
→ Now add to order
```

### PRINCIPLE 4 — FORGIVE TYPOS ALWAYS
A customer typing in Roman Urdu on a mobile keyboard will make typos.
The bot handles "paresitamol", "bruffen", "amoxicillin" without complaint.
Fuzzy matching happens silently. If the bot is not sure, it shows options —
it does NOT say "medicine nahi mili."

```
WRONG:
"Yeh medicine hamare catalog mein nahi hai."

CORRECT (when fuzzy match finds candidates):
"Kya aap yeh mein se koi chahte hain?
1. Paracetamol 500mg
2. Paracetamol 125mg syrup
3. Koi aur"
```

### PRINCIPLE 5 — SHORT MESSAGES WIN
WhatsApp is a mobile-first, notification-driven medium. Long messages get
partially read or ignored. Every bot message should be readable in under
5 seconds. Target: under 5 lines per message, under 100 words.

```
Exception: Bill summary (max 20 lines, structured)
Exception: Welcome/onboarding message (one time, max 10 lines)
```

### PRINCIPLE 6 — FAIL GRACEFULLY, NEVER SILENTLY
If something goes wrong (AI failure, DB timeout, payment error), the
customer must receive a message. The customer must NEVER be left waiting
with no response. The error message must not contain technical terms.

```
WRONG:
"Internal Server Error 500"
"Database connection failed"

CORRECT:
"Maazrat chahte hain, ek technical masla aa gaya.
Aapka order mehfooz hai. Thori dair mein dobara try karein."

CORRECT (payment failure):
"Payment link mein masla aa gaya. Kripaya dobara try karein
ya apne JazzCash account se directly send karein: 0300-XXXXXXX"
```

---

## WHATSAPP MESSAGE FORMATTING RULES

### TEXT FORMATTING
- `*bold*` for emphasis: medicine names, totals, commands
- `_italic_` sparingly: for gentle tone (e.g., "aapka order _tayyar_ hai")
- `` `code` `` never (looks bad on mobile)
- `~strikethrough~` for crossed-out original prices
- Headers via emoji + bold: `*📦 Order Summary*`

### EMOJI USAGE
Emoji makes messages feel warm and scannable. Use deliberately:
```
✅ — confirmed, completed action
❌ — cancelled, unavailable
📦 — order, delivery
💊 — medicine item
💰 — payment, pricing
⚠️  — warning, important note
🔄 — processing, loading
❓ — question, needs clarification
📋 — bill, summary
```

Rules:
- Max 2 emoji per message
- Never use emoji in error messages (tone mismatch)
- Never use emoji as list bullets (use numbers instead)
- Never use emoji mid-sentence

### INTERACTIVE MESSAGES
Use WhatsApp interactive buttons when the choice is binary or max 3 options.
Use WhatsApp list messages when the choice is 4-10 options.
Use plain text when asking for free-form input (quantity, address).

```python
# Binary choice → buttons
{
  "type": "interactive",
  "interactive": {
    "type": "button",
    "body": {"text": "Brufen 400mg — 10 strips?\nPKR 450"},
    "action": {
      "buttons": [
        {"type": "reply", "reply": {"id": "confirm_item", "title": "Haan ✅"}},
        {"type": "reply", "reply": {"id": "reject_item", "title": "Nahi ❌"}}
      ]
    }
  }
}

# Multiple medicine matches → list
{
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": {"text": "Kaunsa Brufen chahiye?"},
    "action": {
      "button": "Dekhein",
      "sections": [{
        "title": "Catalog Matches",
        "rows": [
          {"id": "cat_001", "title": "Brufen 400mg", "description": "100 strips/box — PKR 450"},
          {"id": "cat_002", "title": "Brufen 600mg", "description": "100 strips/box — PKR 580"},
          {"id": "cat_003", "title": "Brufen Syrup", "description": "120ml bottle — PKR 120"},
        ]
      }]
    }
  }
}
```

---

## CONVERSATION FLOWS

### FLOW 1 — RETURNING CUSTOMER, SINGLE ITEM ORDER

```
Customer: "Assalam o alaikum"
Bot:      "Walaikum assalam! 😊
           Ahmed Pharma ke liye kya chahiye?"

Customer: "10 strip paracetamol"
Bot:      [search catalog → found: Paracetamol 500mg GSK]
           "💊 *Paracetamol 500mg* (GSK) — 10 strips
           PKR 650
           Sahi hai?"

           [Interactive: Haan ✅ | Nahi ❌]

Customer: [taps Haan]
Bot:      "Add ho gaya ✅
           Koi aur cheez?"

Customer: "Nahi bas yahi"
Bot:      "📋 *Bill Summary*

           Paracetamol 500mg × 10 strips — PKR 650
           Delivery: PKR 100
           *Total: PKR 750*

           Confirm karna ho to *CONFIRM* likhein"

Customer: "CONFIRM"
Bot:      "Order confirm ho gaya! ✅
           Order #ORD-2025-0847

           Kal subah 10 baje tak delivery hogi.
           Payment ka link thori dair mein aayega."
```

### FLOW 2 — VOICE NOTE ORDER

```
Customer: [sends voice note]
Bot:      [transcribe audio]
           "🎤 Yeh samjha:
           '5 daba augmentin 625mg chahiye'

           Sahi hai?"

           [Interactive: Haan ✅ | Nahi ❌]

Customer: [taps Haan]
Bot:      "💊 *Augmentin 625mg* — 5 boxes
           PKR 2,750
           Add karo?"

           [Interactive: Haan ✅ | Nahi ❌]
```

### FLOW 3 — FUZZY MATCH REQUIRED

```
Customer: "amoksal 500"
Bot:      [fuzzy match: candidates found]
           "Yeh mein se kaunsa chahiye?"

           [List: Amoxil 500mg | Amoxicillin 500mg (generic) | Amoksiklav 625mg]

Customer: [selects Amoxil 500mg]
Bot:      "💊 *Amoxil 500mg* — Kitni chahiye?"

Customer: "3 daba"
Bot:      "*Amoxil 500mg* — 3 boxes
           PKR 1,800
           Sahi hai?"
```

### FLOW 4 — OUT OF STOCK

```
Bot:      "⚠️  *Brufen 400mg* abhi available nahi.
           Kya brufen 600mg chalega? Ya koi aur alternative?"
```

### FLOW 5 — DISCOUNT REQUEST

```
Customer: "thora discount dain"
Bot:      "Aapki request owner ke paas bhej di gayi hai ✅
           Agar approve hua to bill update ho jayega.
           Baaki order continue karein?"
```

### FLOW 6 — NEW CUSTOMER ONBOARDING

```
Bot:      "Assalam o alaikum! 🌟 *[Distributor Name]* mein khush aamdeed!

           Main TELETRAAN hoon — aapka automated order assistant.
           Mujhse direct medicine order kar sakte hain.

           Shuru karne ke liye apna *naam* aur *dukaan ka naam* bata dain."

Customer: "Ali Khan — Ali Medical Store"
Bot:      "Shukriya Ali bhai! ✅
           Aapka account ban gaya.

           Ab bas medicine ka naam aur quantity bataiye —
           main order ready kar dunga."
```

---

## ERROR MESSAGE TEMPLATES

Define all customer-visible error messages in:
`app/notifications/errors.py`

```python
ERROR_MESSAGES = {
    "out_of_stock": "⚠️ {medicine_name} abhi available nahi. Koi alternative chahiye?",
    "credit_limit_exceeded": "⚠️ Aapki credit limit ({limit}) exceed ho rahi hai.\nKripaya pehle outstanding balance {balance} clear karein.",
    "payment_link_failed": "Payment link mein masla. Dobara try karein ya {owner_number} par call karein.",
    "order_empty": "Order mein koi item nahi. Pehle medicine add karein.",
    "technical_error": "Ek masla aa gaya. Thori dair mein dobara try karein. 🙏",
    "session_expired": "Aapka session expire ho gaya. Dobara shuru karein — aapka account mehfooz hai.",
    "voice_low_confidence": "🎤 Aawaaz clearly nahi suni. Kripaya type kar ke bataiye ya dobara voice note bhejein.",
    "catalog_not_found": "Yeh medicine catalog mein nahi mili.\nNaam dobara check karein ya owner se confirm karein.",
    "order_minimum_not_met": "Minimum order PKR {minimum} hai. Abhi PKR {current} ka order hai.",
    "delivery_zone_unknown": "Delivery zone confirm karna hai. Aapka pura address bata dain.",
}
```

---

## UX ANTI-PATTERNS (NEVER DO THESE)

| Anti-Pattern | Why Bad | Correct Approach |
|---|---|---|
| Saying "I don't understand" | Blames user, creates dead end | Ask clarifying question |
| Showing stack traces | Confusing, scary, unprofessional | Use error templates |
| Asking multiple questions at once | User doesn't know which to answer | One question per message |
| Silent failures | Customer thinks order was placed | Always acknowledge |
| Using all-caps aggressively | Feels like shouting | Only use for commands: CONFIRM, CANCEL |
| Response longer than 20 lines | Gets scrolled past | Split into multiple messages |
| Repeating full order list after every item | Clutters chat | Only show on bill request or final confirm |
| Making customer type exact command syntax | Feels robotic | Accept natural language variations |

---

## RESPONSE TIMING

Customers on WhatsApp expect near-instant responses.
TELETRAAN must respond within 3 seconds for text messages.
For voice notes, response within 5 seconds is acceptable.

```python
# Ensure processing pipeline meets these targets:
# Text webhook → handler → AI → response: < 3s
# Voice webhook → download → transcribe → handler → AI → response: < 5s

# Use typing indicators for operations > 1.5 seconds
async def send_typing_indicator(phone: str, client: WhatsAppClient):
    await client.post(f"/messages", {"messaging_product": "whatsapp",
                                     "to": phone, "type": "reaction"})
```

---

## CHANNEL A vs CHANNEL B UX DIFFERENCES

| Aspect | Channel A (Customers) | Channel B (Sales Reps) |
|---|---|---|
| Tone | Warm, simple, patient | Efficient, data-forward |
| Language | Roman Urdu primary | Roman Urdu or English |
| Message length | Very short (≤5 lines) | Medium (up to 10 lines) |
| Data shown | Order status, bill, delivery | Targets, commissions, customer list |
| Error handling | Soft, reassuring | Direct, actionable |
| Confirmation steps | Always required | Fewer confirmations (professional) |
| Voice support | Full | Partial (commands only) |

---

*End of SKILL: ux v1.0*
