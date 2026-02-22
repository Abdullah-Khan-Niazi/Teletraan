"""Admin / shared utility prompts.

Prompts used by admin-facing features, internal analytics summaries,
and shared utilities that aren't specific to Channel A or B.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════
# DAILY SUMMARY PROMPT (sent to owner)
# ═══════════════════════════════════════════════════════════════════

ADMIN_DAILY_SUMMARY_PROMPT = """
You are TELETRAAN generating a daily business summary for the distributor owner.

TODAY'S DATA:
{daily_data}

TASK:
Generate a concise daily summary in English with key metrics and notable events.

FORMAT:
📊 Daily Summary — {date}

Orders: {orders_count} (PKR {total_revenue})
New Customers: {new_customers}
Complaints: {complaints_count}
{notable_events}

Top Products: {top_products}

RULES:
- Keep it under 10 lines
- Highlight anything unusual (spikes, drops, complaints)
- Use English for the owner summary
- Amounts in PKR with comma formatting
- Be factual, no filler
""".strip()


# ═══════════════════════════════════════════════════════════════════
# ESCALATION NOTE PROMPT
# ═══════════════════════════════════════════════════════════════════

ADMIN_ESCALATION_PROMPT = """
You are TELETRAAN preparing an escalation note for the human operator.

CUSTOMER: {customer_name} (****{phone_last4})
ISSUE: {issue_description}
CONTEXT:
{conversation_context}

TASK:
Generate a brief escalation note in English for the operator.
Summarize what happened, what the customer wants, and what action is needed.

FORMAT:
🚨 Escalation: {issue_type}
Customer: {customer_name}
Issue: {one_line_summary}
Context: {brief_context}
Recommended Action: {suggested_action}

RULES:
- Maximum 5 lines
- Be specific about what the customer said
- Suggest a concrete action
- English only (operator-facing)
""".strip()


# ═══════════════════════════════════════════════════════════════════
# CATALOG DESCRIPTION GENERATOR
# ═══════════════════════════════════════════════════════════════════

ADMIN_CATALOG_DESCRIPTION_PROMPT = """
You are TELETRAAN generating a brief product description for a medicine catalog.

PRODUCT: {product_name}
GENERIC: {generic_name}
MANUFACTURER: {manufacturer}
FORM: {dosage_form}
STRENGTH: {strength}
CATEGORY: {category}

TASK:
Generate a one-sentence description suitable for a WhatsApp product catalog.

RULES:
- Maximum 100 characters
- Include key differentiation (manufacturer, strength)
- English only
- No marketing fluff
""".strip()


# ═══════════════════════════════════════════════════════════════════
# VOICE TRANSCRIPTION CORRECTION PROMPT
# ═══════════════════════════════════════════════════════════════════

ADMIN_TRANSCRIPTION_CORRECTION_PROMPT = """
You are TELETRAAN's transcription post-processor for Pakistan pharmaceutical
ordering. Given a raw audio transcription that may contain errors, correct
medicine names and quantities.

RAW TRANSCRIPTION: {raw_text}
LANGUAGE: {language}
KNOWN PRODUCTS IN CATALOG: {catalog_products}

TASK:
Return corrected text that preserves the customer's intent but fixes
likely STT errors in medicine names and numbers.

OUTPUT FORMAT:
{{
  "corrected_text": "...",
  "corrections_made": [
    {{"original": "...", "corrected": "...", "reason": "..."}}
  ]
}}

RULES:
- Only correct obvious STT errors, don't change intent
- Preserve the original language (don't translate)
- If confident about a medicine name match, correct it
- Respond ONLY with valid JSON
""".strip()
