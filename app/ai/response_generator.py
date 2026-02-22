"""Multi-language response generation using the AI provider factory.

Generates context-aware responses for both Channel A (orders) and
Channel B (sales).  Uses the provider factory with fallback.  If AI
is completely unavailable, returns rule-based template responses so
the bot never goes silent.
"""

from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from app.ai.base import AITextResponse
from app.ai.factory import generate_text_with_fallback, get_ai_provider
from app.ai.prompts.channel_a import (
    CHANNEL_A_COMPLAINT_PROMPT,
    CHANNEL_A_GREETING_PROMPT,
    CHANNEL_A_PRICE_STOCK_PROMPT,
    CHANNEL_A_SYSTEM_PROMPT,
    ORDER_SUMMARY_TEMPLATE,
)
from app.ai.prompts.channel_b import (
    CHANNEL_B_DEMO_PROMPT,
    CHANNEL_B_FOLLOWUP_PROMPT,
    CHANNEL_B_SYSTEM_PROMPT,
)
from app.core.constants import AI_MAX_PROMPT_INPUT_LENGTH
from app.core.security import sanitize_for_prompt
from app.notifications.templates import get_template


# ═══════════════════════════════════════════════════════════════════
# CHANNEL A — ORDER CONVERSATION
# ═══════════════════════════════════════════════════════════════════


async def generate_order_response(
    *,
    distributor_name: str,
    order_context: str,
    customer_name: str,
    phone_last4: str,
    customer_message: str,
    conversation_history: Optional[list[dict]] = None,
    language: str = "roman_urdu",
) -> str:
    """Generate a contextual response for a Channel A order conversation.

    Args:
        distributor_name: Name of the distributor.
        order_context: Formatted order state string.
        customer_name: Customer display name.
        phone_last4: Last 4 digits of phone number.
        customer_message: The current customer message.
        conversation_history: Previous messages for context.
        language: Preferred response language.

    Returns:
        Response text string.
    """
    system_prompt = CHANNEL_A_SYSTEM_PROMPT.format(
        distributor_name=distributor_name,
        order_context=order_context or "No active order.",
        customer_name=customer_name or "Customer",
        phone_last4=phone_last4,
    )

    messages = _build_messages(
        conversation_history or [],
        customer_message,
    )

    start = time.monotonic()
    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.7,
        max_tokens=1024,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    if response is not None and response.content.strip():
        logger.info(
            "response.generated",
            channel="a",
            latency_ms=latency_ms,
            tokens=response.tokens_used_output,
        )
        return response.content.strip()

    # Fallback to template
    logger.warning("response.using_template_fallback", channel="a")
    return get_template("error_ai_unavailable", language)


async def generate_greeting(
    *,
    distributor_name: str,
    customer_name: str,
    customer_type: str = "returning",
    time_of_day: str = "day",
    has_previous_orders: bool = False,
    language: str = "roman_urdu",
) -> str:
    """Generate a personalised greeting for a customer.

    Args:
        distributor_name: Distributor name.
        customer_name: Customer display name.
        customer_type: 'new' or 'returning'.
        time_of_day: 'morning', 'afternoon', 'evening'.
        has_previous_orders: Whether the customer has ordered before.
        language: Response language.

    Returns:
        Greeting text.
    """
    system_prompt = CHANNEL_A_GREETING_PROMPT.format(
        distributor_name=distributor_name,
        customer_type=customer_type,
        customer_name=customer_name or "Customer",
        time_of_day=time_of_day,
        has_previous_orders=str(has_previous_orders).lower(),
    )

    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": "Generate greeting"}],
        temperature=0.8,
        max_tokens=256,
    )

    if response is not None and response.content.strip():
        return response.content.strip()

    # Template fallback
    if customer_type == "new":
        return get_template("bot_greeting_new", language)
    if customer_name:
        template = get_template("bot_greeting_returning", language)
        return template.format(name=customer_name)
    return get_template("bot_greeting_no_name", language)


async def generate_complaint_response(
    *,
    distributor_name: str,
    complaint_category: str,
    customer_message: str,
    order_reference: str = "N/A",
    language: str = "roman_urdu",
) -> str:
    """Generate a complaint acknowledgement response.

    Args:
        distributor_name: Distributor name.
        complaint_category: Category of complaint.
        customer_message: Customer's complaint text.
        order_reference: Related order ID if any.
        language: Response language.

    Returns:
        Complaint response text.
    """
    safe_message = sanitize_for_prompt(customer_message, max_length=500)

    system_prompt = CHANNEL_A_COMPLAINT_PROMPT.format(
        distributor_name=distributor_name,
        complaint_category=complaint_category,
        customer_message=safe_message,
        order_reference=order_reference,
    )

    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": safe_message}],
        temperature=0.5,
        max_tokens=512,
    )

    if response is not None and response.content.strip():
        return response.content.strip()

    return get_template("complaint_logged", language)


async def generate_price_stock_response(
    *,
    distributor_name: str,
    query_type: str,
    product_name: str,
    catalog_data: str,
    language: str = "roman_urdu",
) -> str:
    """Generate a price or stock query response.

    Args:
        distributor_name: Distributor name.
        query_type: 'price' or 'stock'.
        product_name: Product being queried.
        catalog_data: Formatted catalog info.
        language: Response language.

    Returns:
        Response text.
    """
    system_prompt = CHANNEL_A_PRICE_STOCK_PROMPT.format(
        distributor_name=distributor_name,
        query_type=query_type,
        product_name=product_name,
        catalog_data=catalog_data or "Not found in catalog.",
    )

    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": f"{query_type}: {product_name}"}],
        temperature=0.3,
        max_tokens=512,
    )

    if response is not None and response.content.strip():
        return response.content.strip()

    return get_template("error_ai_unavailable", language)


def format_order_summary(
    *,
    order_number: str,
    customer_name: str,
    items: list[dict],
    subtotal: int,
    discount: int = 0,
    total: int,
    payment_method: str = "Pending",
    delivery_info: str = "TBD",
) -> str:
    """Format a complete order summary using the template.

    All monetary values in paisas — converted to PKR for display.

    Args:
        order_number: Order ID.
        customer_name: Customer name.
        items: List of item dicts with name, qty, unit, price_paisas.
        subtotal: Subtotal in paisas.
        discount: Discount in paisas.
        total: Total in paisas.
        payment_method: Payment method string.
        delivery_info: Delivery details.

    Returns:
        Formatted order summary string.
    """
    item_lines = []
    for i, item in enumerate(items, 1):
        name = item.get("name", "Unknown")
        qty = item.get("qty", 0)
        unit = item.get("unit", "x")
        price = item.get("price_paisas", 0) / 100
        line_total = qty * price
        item_lines.append(f"{i}. {name} — {qty} {unit} × PKR {price:,.0f} = PKR {line_total:,.0f}")

    discount_line = ""
    if discount > 0:
        discount_line = f"Discount: -PKR {discount / 100:,.0f}\n"

    return ORDER_SUMMARY_TEMPLATE.format(
        order_number=order_number,
        customer_name=customer_name or "Customer",
        item_lines="\n".join(item_lines),
        subtotal=f"{subtotal / 100:,.0f}",
        discount_line=discount_line,
        total=f"{total / 100:,.0f}",
        payment_method=payment_method,
        delivery_info=delivery_info,
    )


# ═══════════════════════════════════════════════════════════════════
# CHANNEL B — SALES CONVERSATION
# ═══════════════════════════════════════════════════════════════════


async def generate_sales_response(
    *,
    prospect_name: str,
    business_name: str = "",
    funnel_stage: str = "new",
    interaction_summary: str = "",
    prospect_message: str,
    conversation_history: Optional[list[dict]] = None,
    language: str = "roman_urdu",
) -> str:
    """Generate a Channel B sales conversation response.

    Args:
        prospect_name: Prospect display name.
        business_name: Prospect business name.
        funnel_stage: Current funnel stage.
        interaction_summary: Previous interaction summary.
        prospect_message: Current prospect message.
        conversation_history: Previous conversation messages.
        language: Response language.

    Returns:
        Sales response text.
    """
    system_prompt = CHANNEL_B_SYSTEM_PROMPT.format(
        prospect_name=prospect_name or "Prospect",
        business_name=business_name or "Not specified",
        funnel_stage=funnel_stage,
        interaction_summary=interaction_summary or "First contact.",
    )

    messages = _build_messages(
        conversation_history or [],
        prospect_message,
    )

    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.7,
        max_tokens=1024,
    )

    if response is not None and response.content.strip():
        return response.content.strip()

    return (
        "Shukriya aapki dilchaspi ka! TELETRAAN ek WhatsApp-based ordering "
        "system hai medicine distributors ke liye. Kya main aapke business "
        "ke baare mein kuch sawaal pooch sakta hoon?"
    )


async def generate_demo_message(
    *,
    prospect_name: str,
    business_name: str,
    available_slots: str,
    language: str = "roman_urdu",
) -> str:
    """Generate a demo scheduling message.

    Args:
        prospect_name: Prospect name.
        business_name: Business name.
        available_slots: Formatted available time slots.
        language: Response language.

    Returns:
        Demo scheduling response.
    """
    system_prompt = CHANNEL_B_DEMO_PROMPT.format(
        prospect_name=prospect_name or "Prospect",
        business_name=business_name or "your business",
        available_slots=available_slots,
        language=language,
    )

    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": "Schedule demo"}],
        temperature=0.6,
        max_tokens=512,
    )

    if response is not None and response.content.strip():
        return response.content.strip()

    return (
        f"{prospect_name}, demo ke liye yeh waqt available hain:\n"
        f"{available_slots}\n"
        "Kaunsa waqt suit karega?"
    )


async def generate_followup_message(
    *,
    prospect_name: str,
    last_contact_date: str,
    funnel_stage: str,
    previous_context: str,
    language: str = "roman_urdu",
) -> str:
    """Generate a follow-up message for a prospect.

    Args:
        prospect_name: Prospect name.
        last_contact_date: Date of last contact.
        funnel_stage: Current funnel stage.
        previous_context: Summary of previous interaction.
        language: Response language.

    Returns:
        Follow-up message text.
    """
    system_prompt = CHANNEL_B_FOLLOWUP_PROMPT.format(
        prospect_name=prospect_name or "Prospect",
        last_contact_date=last_contact_date,
        funnel_stage=funnel_stage,
        previous_context=previous_context or "Previous conversation about TELETRAAN.",
        language=language,
    )

    response = await generate_text_with_fallback(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": "Generate follow-up"}],
        temperature=0.7,
        max_tokens=512,
    )

    if response is not None and response.content.strip():
        return response.content.strip()

    return (
        f"Assalam o alaikum {prospect_name}! Pichli dafa hum ne TELETRAAN "
        "ke baare mein baat ki thi. Kya aap abhi bhi interested hain? "
        "Koi sawal ho toh zaroor poochein."
    )


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _build_messages(
    history: list[dict],
    current_message: str,
    max_turns: int = 15,
) -> list[dict]:
    """Build a message list from history + current user message.

    Limits to the most recent ``max_turns`` messages to avoid
    blowing token limits.

    Args:
        history: Previous conversation turns.
        current_message: Current user message.
        max_turns: Maximum history turns to include.

    Returns:
        List of message dicts.
    """
    safe_current = sanitize_for_prompt(
        current_message,
        max_length=AI_MAX_PROMPT_INPUT_LENGTH,
    )

    # Take last max_turns from history
    recent = history[-max_turns:] if len(history) > max_turns else history

    messages: list[dict] = []
    for msg in recent:
        messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        })

    messages.append({"role": "user", "content": safe_current})
    return messages
