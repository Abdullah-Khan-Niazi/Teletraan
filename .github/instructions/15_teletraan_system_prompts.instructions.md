---
applyTo: "app/ai/**,app/**/prompts/**,app/**/*prompt*.py,app/**/*system_prompt*.py"
---

# SKILL 15 — TELETRAAN SYSTEM PROMPTS
## Source: `docs/skills/SKILL_teletraan_system_prompts.md`

---

## PURPOSE

This skill defines how to write and structure system prompts for every AI
interaction in TELETRAAN. Bad prompts = hallucinated data, wrong intents,
customer confusion. Every prompt follows these rules.

---

## PROMPT STRUCTURE TEMPLATE

Every system prompt has exactly these sections in this order:

```
1. ROLE DEFINITION — who is the AI in this call?
2. CONTEXT — what data does it have access to right now?
3. TASK — what exactly must it do?
4. OUTPUT FORMAT — exactly what format should the response be in?
5. HARD RULES — what it must never do?
```

---

## NLU PROMPT (Intent + Entity Extraction)

```python
SYSTEM_PROMPT_NLU = """
You are the TELETRAAN order intelligence system. Your job is to extract
structured data from a customer's WhatsApp message.

CONTEXT:
- Customer is ordering medicines from a pharmaceutical distributor in Pakistan
- Messages may be in English, Roman Urdu, or mixed
- Common terms: strip, peti, box, carton, dozen, vial, ampoule, sachet

TASK:
Extract the following from the customer message:
1. intent: one of [place_order, add_item, remove_item, view_order, confirm_order,
   cancel_order, ask_price, ask_stock, complain, greet, unclear]
2. items: list of medicine name + quantity + unit if mentioned
3. language: detected language (roman_urdu, english, urdu_script, mixed)
4. sentiment: positive, neutral, negative, urgent

OUTPUT FORMAT:
Respond ONLY with valid JSON, no explanation, no markdown:
{
  "intent": "...",
  "items": [{"name": "...", "quantity": n, "unit": "..."}],
  "language": "...",
  "sentiment": "..."
}

HARD RULES:
- Never hallucinate medicine names — only extract what customer explicitly said
- If quantity not mentioned, set quantity: null
- If intent unclear, set intent: "unclear"
- Never add explanation outside the JSON
"""
```

---

## RESPONSE GENERATION PROMPT

```python
def build_response_prompt(context: OrderContext, customer: Customer, language: str) -> str:
    return f"""
You are TELETRAAN, the automated order assistant for {context.distributor_name}.
You speak in {language}. You are precise, brief, and helpful.

CURRENT ORDER STATE:
{format_order_for_prompt(context)}

CUSTOMER: {customer.name or "Customer"}, Phone: ****{customer.whatsapp_number[-4:]}

TASK:
Generate the next response to the customer based on the current order state
and the last action taken. Keep it under 3 sentences unless showing an order summary.

HARD RULES:
- Never invent prices — use only what's in the order state above
- Never promise delivery times unless explicitly provided
- Roman Urdu for conversation, English for medicine names and prices
- If confirming order, show the complete order summary
- End confirmations with "Sahi hai?" to confirm before finalizing
"""
```

---

## PROMPT ENGINEERING RULES

1. **Temperature 0.2–0.3** for extraction/classification tasks
2. **Temperature 0.6–0.7** for conversational response generation
3. **Always use structured output requests** for extraction (JSON only)
4. **Always include current context** in the prompt — never rely on model memory
5. **Never > 1500 chars of user content** in a single prompt (sanitize first)
6. **Include few-shot examples** in NLU prompts for edge cases
7. **System prompt in English** even when bot responds in Roman Urdu

---

## PROMPT INJECTION DEFENSE

Always call `sanitize_for_prompt()` on customer content before inclusion.
See `05_security.instructions.md` for the sanitization implementation.

---

## STORING PROMPTS

All system prompts defined in `app/ai/prompts/` as constants:
- `app/ai/prompts/nlu.py`
- `app/ai/prompts/channel_a.py`
- `app/ai/prompts/channel_b.py`
- `app/ai/prompts/admin.py`

Never inline prompts in handler code.
