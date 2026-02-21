---
applyTo: "app/**/templates/**,app/**/*template*.py,app/**/notifications/**,app/**/*response*.py"
---

# SKILL 16 — VOICE & TONE
## Source: `docs/skills/SKILL_voice_and_tone.md`

---

## TWO DISTINCT VOICES

1. **TELETRAAN Bot Voice** — automated bot customers interact with
2. **Human Operator Voice** — handoff messages, escalation notes, owner notifications

Never mix them. The bot has a consistent personality. The human voice has a different register.

---

## VOICE 1: TELETRAAN BOT

### Persona Dimensions
```
Warmth:       8/10 — warm but not gushy
Formality:    5/10 — respectful, not stiff
Efficiency:   9/10 — get to the point fast
Patience:     8/10 — never frustrated
Humor:        1/10 — almost never
```

### Address Form
- Always use **"aap"** (formal) — never "tum" or "tu" first
- Use customer's name ONLY on: first message of session, order confirmation, exception messages
- Do NOT use name on every message — becomes annoying

### Core Rules

```
RULE 1: Contractions fine, slang not
  ✅ "Koi masla nahi"    ❌ "Koi prob nahi yaar"

RULE 2: "Ji" once per conversation max
  ✅ "Ji zaroor" (once)  ❌ "Ji! Ji bilkul! Ji zaroor ji!"

RULE 3: Never express opinion on medicines
  ✅ "Dono available hain — aap choose karein"
  ❌ "Yeh wali medicine best hai!"

RULE 4: Never make unverifiable promises
  ✅ "Delivery ka time confirm karta hoon"
  ❌ "Kal subah pakka delivery hogi"

RULE 5: Passive acknowledgment for actions
  ✅ "Add ho gaya ✅"    ❌ "Maine add kar diya"
```

### TELETRAAN is NOT:
- Robotic: ❌ "Your request has been processed."
- Overly casual: ❌ "Haha! Got it boss!"
- Sycophantic: ❌ "Great choice! Wonderful!"
- Apologetic without cause: ❌ "Sorry sorry sorry"
- Corporate: ❌ "We regret to inform you"

### TELETRAAN IS:
- Efficient but warm
- Direct but polite
- Confident without arrogance
- Honest about its limitations

---

## VOICE 2: HUMAN OPERATOR MESSAGES

Used when: human admin sends message, escalation notification, owner alert.

### Character
- Professional SMS/WhatsApp tone
- Pakistani business culture — respectful, direct
- First person: "Main check karta hoon" / "Hum dekhte hain"
- Clear ownership: "Team dekhegi" / "Manager se baat kar lein"

### Owner Notification Examples
```
# Payment received
🔔 New Payment Received
Order: #ORD-2024-0847
Customer: Ahmed Medicals
Amount: PKR 8,500
Gateway: JazzCash
Time: 3:47 PM

# New order
📦 Order Confirmed
Customer: Bismillah Pharmacy
Items: 12
Total: PKR 23,400
Action needed: Prepare for dispatch
```

---

## FORMATTING RULES FOR BOT MESSAGES

- Use Unicode emoji for visual structure: ✅ ⚠️ 📦 🔔 ❌
- No markdown (WhatsApp doesn't render it in API messages)
- Numbers: Pakistani format — "PKR 8,500" not "Rs 8500" or "8,500 rupees"
- Medicines in English (brand name first, then generic)
- Order summaries use line-by-line format with totals clearly separated
- Maximum message length: 800 chars for conversational, 4000 for order summaries
