# TELETRAAN SYSTEM PROMPT ENGINEERING SKILL
## SKILL: teletraan-system-prompts | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines how the TELETRAAN Build Agent writes, structures, versions,
and maintains ALL system prompts used by the TELETRAAN bot at runtime.

System prompts are production code. They are versioned, tested, and committed
with the same discipline as Python files. A poorly written system prompt causes
wrong intent classification, hallucinated medicine names, missed order items,
and lost revenue.

---

## DIRECTORY STRUCTURE

```
app/
  ai/
    prompts/
      __init__.py
      base.py                  ← PromptTemplate base class
      channel_a_order.py       ← Customer order flow (Channel A)
      channel_b_sales.py       ← Sales rep B2B flow (Channel B)
      intent_classifier.py     ← Intent classification
      entity_extractor.py      ← Medicine name / quantity extraction
      fuzzy_disambiguator.py   ← Fuzzy match candidate selection
      bill_summarizer.py       ← Billing confirmation message generator
      voice_fallback.py        ← Low-confidence audio fallback
      onboarding.py            ← New customer onboarding guidance
      admin_nlp.py             ← Owner admin command interpretation
      language_detector.py     ← Urdu/Roman Urdu/English detection
```

---

## PROMPT TEMPLATE BASE CLASS

```python
# app/ai/prompts/base.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PromptTemplate:
    """
    Base class for all TELETRAAN system prompts.

    Every prompt is versioned, named, and documents its expected
    input variables and output schema.
    """
    name: str
    version: str
    description: str
    input_variables: list[str]            # variables injected at render time
    output_format: str                    # "json" | "text" | "structured_text"
    temperature: float = 0.2             # default: low for determinism
    max_tokens: int = 1024
    _template: str = field(default="", repr=False)

    def render(self, **kwargs) -> str:
        """Render the system prompt with injected variables."""
        missing = [v for v in self.input_variables if v not in kwargs]
        if missing:
            raise ValueError(f"[{self.name}] Missing prompt variables: {missing}")
        return self._template.format(**kwargs)

    def metadata_comment(self) -> str:
        return (
            f"[PROMPT: {self.name} v{self.version}] "
            f"[OUTPUT: {self.output_format}] "
            f"[TEMP: {self.temperature}]"
        )
```

---

## PROMPT ENGINEERING RULES

### RULE 1 — STATE THE ROLE FIRST
Every prompt opens with a single-sentence role declaration. TELETRAAN is not
a general assistant. State exactly what it is and what it does in Prompt Line 1.

```
CORRECT:
"You are TELETRAAN, an automated WhatsApp order assistant for {distributor_name},
a pharmaceutical distributor in Pakistan."

WRONG:
"You are a helpful assistant that can help with orders."
```

### RULE 2 — SPECIFY THE LANGUAGE CONTRACT EXPLICITLY
TELETRAAN operates in Roman Urdu (primary), Urdu script, and English.
Every prompt must tell the model which language to respond in and under
what conditions to switch.

```
Language Rules (include in every customer-facing prompt):
- Default response language: Roman Urdu
- If customer writes in English only: respond in English
- If customer writes in Urdu script: respond in Urdu script
- Never mix Urdu script and Roman Urdu in the same sentence
- Technical terms (medicine names, amounts in PKR): always use their common name
- Formal address: use "aap" not "tum" unless customer uses "tum" first
```

### RULE 3 — OUTPUT FORMAT IS LAW
If the prompt expects JSON output, the model MUST output JSON and nothing else.
Enforce this with explicit forbidden phrases.

```
You MUST respond with valid JSON only.
Do NOT include any explanation, preamble, markdown fences, or commentary.
Do NOT say "Here is the JSON:" or "Sure, here you go:"
Your entire response must be parseable by json.loads() with no preprocessing.
```

### RULE 4 — DEFINE EVERY EDGE CASE IN THE PROMPT
Do not rely on the model's "common sense." If a customer asks for a medicine
that does not exist, specify exactly what to do. If the quantity is missing,
specify exactly what to ask. Every known failure mode must have an explicit
instruction.

```
Edge case instructions to include in order flow prompts:
- Medicine name not found → ask for clarification, suggest similar names if available
- Quantity missing → ask "Kitni chahiye?"
- Price question before confirming item → state price, then confirm quantity
- Customer says "sab" (all) without specifying → ask which items
- Customer cancels mid-order → acknowledge, ask if they want a new order
- Customer sends a voice note → transcription is provided, treat as text input
- Customer sends an image → if product image, acknowledge; cannot process visually
- Unrelated message (e.g., "Hello", "Kaisa ho?") → respond briefly, redirect to ordering
```

### RULE 5 — INJECT BUSINESS CONTEXT DYNAMICALLY
Prompts must receive runtime context about the distributor, customer, and
current order state. Never hardcode business rules into the static prompt string.
Business rules come from the database and are injected at call time.

```python
# CORRECT — context injected at runtime
prompt.render(
    distributor_name=distributor.business_name,
    credit_limit_paisas=customer.credit_limit,
    outstanding_balance_paisas=customer.outstanding_balance,
    discount_policy=distributor.discount_policy_description,
    delivery_zones=", ".join(distributor.active_delivery_zones),
    current_order_summary=order_context.billing_summary_text(),
)

# WRONG — hardcoded business rule in static prompt
"The credit limit is PKR 50,000."
```

### RULE 6 — NEVER INSTRUCT THE MODEL TO HALLUCINATE
Do not include instructions like "If you don't know the medicine, make up a similar
name." The model must always express uncertainty to the orchestrator, not to the
customer.

```
CORRECT (in entity extractor prompt):
"If you cannot confidently extract a medicine name, set 'confidence' to 'low'
and 'medicine_name_raw' to the customer's exact words verbatim."

WRONG:
"Try to guess the closest medicine name if you are unsure."
```

### RULE 7 — KEEP PROMPTS FOCUSED (ONE JOB PER PROMPT)
An intent classifier prompt only classifies intent. It does not also extract
entities or generate a response. Separation of concerns applies to prompts.

---

## PROMPT CATALOG

### 1. INTENT CLASSIFIER PROMPT

**File:** `app/ai/prompts/intent_classifier.py`
**Purpose:** Classify incoming customer message into one of N intents.
**Output:** JSON

```
Input variables:
- customer_message: str
- conversation_history: str   ← last 5 turns, formatted
- current_order_state: str    ← e.g., "building" | "awaiting_confirmation"
- channel: str                ← "A" (customer) | "B" (sales)

Output JSON schema:
{
  "intent": "<intent_name>",
  "confidence": "high" | "medium" | "low",
  "requires_clarification": true | false,
  "clarification_prompt": "<question to ask if needed>"
}

Intent names (Channel A):
- add_item           ← "mujhe paracetamol chahiye"
- remove_item        ← "yeh wala hata do"
- modify_quantity    ← "teen ki jagah paanch"
- confirm_order      ← "theek hai", "confirm", "haan"
- cancel_order       ← "rehne do", "cancel"
- view_bill          ← "bill dikhao", "total kitna hai"
- request_discount   ← "thora discount dain"
- check_stock        ← "yeh available hai?"
- ask_price          ← "price kya hai"
- voice_note         ← (when message is a transcription)
- reorder            ← "pehle wala order dena"
- greeting           ← "assalam o alaikum", "hello"
- unrelated          ← anything not related to ordering
- unclear            ← cannot determine intent

Intent names (Channel B):
- submit_order       ← sales rep sending customer order
- check_targets      ← "mera target kya hai"
- view_commission    ← "commission dikhao"
- add_prospect       ← "naya client add karo"
- update_visit       ← "visit log karo"
- unclear
```

### 2. ENTITY EXTRACTOR PROMPT

**File:** `app/ai/prompts/entity_extractor.py`
**Purpose:** Extract medicine names, quantities, and units from raw customer text.
**Output:** JSON

```
Input variables:
- customer_message: str
- catalog_sample: str    ← comma-separated list of top-50 medicines in catalog
- language: str          ← "roman_urdu" | "urdu" | "english"

Output JSON schema:
{
  "items": [
    {
      "medicine_name_raw": "<exact words from customer>",
      "quantity_raw": "<exact quantity text>",
      "quantity_numeric": <number or null>,
      "unit": "strip" | "box" | "bottle" | "piece" | "pack" | null,
      "confidence": "high" | "medium" | "low"
    }
  ],
  "language_detected": "roman_urdu" | "urdu" | "english" | "mixed",
  "has_ambiguity": true | false,
  "ambiguity_note": "<description of ambiguity if any>"
}

Rules to include in prompt:
- Extract ALL items mentioned in one message, even if a long list
- "ek daba" = 1 box, "do pattay" = 2 strips, "teen seesaw" = 3 syrup bottles
- Roman Urdu quantity words: ek=1, do=2, teen=3, chaar=4, paanch=5, das=10
- Medicine names may be brand names, generic names, or abbreviations
- Never correct or normalize medicine names — preserve the customer's exact words
- If quantity not stated, set quantity_numeric to null
- If unit not stated, set unit to null
```

### 3. FUZZY DISAMBIGUATOR PROMPT

**File:** `app/ai/prompts/fuzzy_disambiguator.py`
**Purpose:** Given a raw medicine name and candidate matches, help rank candidates.
**Output:** JSON

```
Input variables:
- raw_name: str                  ← what customer said
- candidates: str                ← JSON list of {id, name, generic, strength, form}
- context: str                   ← any context clues from conversation

Output JSON schema:
{
  "best_match_id": "<catalog_id or null>",
  "confidence": "high" | "medium" | "low",
  "reasoning": "<brief explanation>",
  "send_to_customer_for_confirmation": true | false
}

Rules:
- If one candidate is clearly superior, select it and set send_to_customer_for_confirmation
  based on confidence (high=false, medium/low=true)
- If multiple plausible matches, set best_match_id to null and
  send_to_customer_for_confirmation to true
- Never hallucinate a medicine not in candidates list
```

### 4. CHANNEL A ORDER FLOW PROMPT

**File:** `app/ai/prompts/channel_a_order.py`
**Purpose:** Generate customer-facing response messages during ordering.
**Output:** Structured text (WhatsApp-formatted)

```
Input variables:
- distributor_name: str
- customer_name: str
- customer_is_returning: bool
- current_order_items_text: str    ← formatted order summary
- billing_summary_text: str
- intent: str
- entity_extraction_result: str
- fuzzy_match_result: str
- discount_policy: str
- credit_balance_text: str         ← "Aapka credit account hai: PKR 25,000"
- special_instructions: str        ← any distributor-specific notes

Tone: Warm, professional, Roman Urdu. Like a trusted shop attendant.
      Never robotic. Never bureaucratic.
      Use "aap" consistently. Never use "ji" excessively.
      Short responses preferred (under 5 lines). No unnecessary filler.
```

### 5. BILL SUMMARIZER PROMPT

**File:** `app/ai/prompts/bill_summarizer.py`
**Purpose:** Generate a clear, readable bill summary for customer confirmation.
**Output:** WhatsApp-formatted text (NOT JSON)

```
Input variables:
- order_items_json: str         ← JSON list of confirmed items
- billing_summary_json: str     ← totals, discounts, delivery
- distributor_name: str
- delivery_eta: str

Format rules:
- Each item: name (quantity) — PKR amount
- Subtotal, discount (if any), delivery, TOTAL on separate lines
- End with "Confirm karna ho to 'CONFIRM' likhein" instruction
- Keep under 20 lines total
- Use emoji sparingly: ✅ for confirmed, 📦 for delivery

Example output format:
---
📦 *{distributor_name}* Order Summary:

Paracetamol 500mg × 10 strips — PKR 650
Amoxicillin 500mg × 5 boxes — PKR 1,200

Subtotal: PKR 1,850
Discount (5%): -PKR 92
Delivery: PKR 150
*Total: PKR 1,908*

Delivery: {delivery_eta}

Confirm karna ho to *CONFIRM* likhein ✅
---
```

### 6. VOICE FALLBACK PROMPT

**File:** `app/ai/prompts/voice_fallback.py`
**Purpose:** When voice transcription confidence is low, generate a clarification request.
**Output:** Text (WhatsApp message)

```
Input variables:
- partial_transcript: str     ← what was understood
- confidence_score: float
- customer_name: str

Rules:
- Always acknowledge the voice note was received
- State what was understood (partial_transcript)
- Ask customer to confirm or type the order
- Never say "I couldn't understand" — say "Thora aur wazeh kar dain"
```

### 7. LANGUAGE DETECTOR PROMPT

**File:** `app/ai/prompts/language_detector.py`
**Purpose:** Detect language/script of incoming message.
**Output:** JSON

```
Output schema:
{
  "primary_language": "roman_urdu" | "urdu_script" | "english" | "mixed",
  "has_urdu_words": true | false,
  "has_english_words": true | false,
  "script": "latin" | "arabic" | "mixed"
}
```

### 8. ADMIN NLP PROMPT

**File:** `app/ai/prompts/admin_nlp.py`
**Purpose:** Interpret natural language admin commands sent by distributor owner.
**Output:** JSON (structured admin command)

```
Input variables:
- admin_message: str
- available_commands: str     ← list of valid admin command names

Output schema:
{
  "command": "<command_name or null>",
  "parameters": { ... },
  "confidence": "high" | "medium" | "low",
  "clarification_needed": true | false
}
```

---

## PROMPT VERSIONING

Every prompt file includes a version constant at the top:

```python
PROMPT_VERSION = "1.2"
PROMPT_LAST_UPDATED = "2025-01-01"
PROMPT_CHANGE_LOG = """
1.2 - Added voice note handling edge case
1.1 - Fixed Roman Urdu quantity word mapping
1.0 - Initial version
"""
```

When a prompt changes:
1. Increment version in the constant
2. Update change log
3. Run affected test cases in tests/ai/prompts/
4. Commit with message: `feat(ai): update intent_classifier prompt to v1.2 — add voice note intent`

---

## PROMPT TESTING REQUIREMENTS

Every prompt must have a corresponding test file:
`tests/ai/prompts/test_{prompt_name}.py`

Each test file must include:
- At least 10 realistic customer message samples per intent/entity type
- Edge cases: empty input, very long input, mixed script input
- Roman Urdu number word variations
- Assertion on output JSON schema validity (not just non-null)
- Assertion that low-confidence cases are correctly flagged

```python
# tests/ai/prompts/test_entity_extractor.py

@pytest.mark.parametrize("message,expected_name,expected_qty", [
    ("mujhe paracetamol dain", "paracetamol", None),
    ("10 strip augmentin chahiye", "augmentin", 10),
    ("teen daba brufen", "brufen", 3),
    ("paanch seesaw amoxil", "amoxil", 5),
    ("calpol ka ek box", "calpol", 1),
])
async def test_entity_extractor_roman_urdu(message, expected_name, expected_qty, mock_ai):
    result = await extract_entities(message, mock_ai)
    assert result.items[0].medicine_name_raw.lower() == expected_name
    assert result.items[0].quantity_numeric == expected_qty
```

---

## FORBIDDEN IN PROMPTS

- Never instruct the model to guess or invent medicine names
- Never include real API keys, phone numbers, or customer data in static prompt strings
- Never write prompts longer than 2,000 tokens for classification tasks
- Never omit the output format specification from any prompt
- Never write a prompt that could produce different schemas depending on input
- Never leave `{variable}` placeholders unfilled at runtime

---

## GIT COMMIT FORMAT FOR PROMPT CHANGES

```
feat(ai): add bill_summarizer system prompt v1.0

New prompt template for generating WhatsApp-formatted order
confirmation messages before customer final approval.

Variables: order_items_json, billing_summary_json,
           distributor_name, delivery_eta

Output: WhatsApp-formatted text (not JSON)
Temperature: 0.3 (slight variation for natural phrasing)

Includes test cases for:
- Multi-item orders with discount
- Single item, no discount
- Free delivery threshold triggered
- Long medicine names (>30 chars)

Signed-off-by: Abdullah-Khan-Niazi
```

---

*End of SKILL: teletraan-system-prompts v1.0*
