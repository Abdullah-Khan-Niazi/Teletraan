"""Channel A — customer inquiry handler.

Single-state flow (``INQUIRY_RESPONSE``) that handles:

* **Price inquiry** — fuzzy-match product, show unit price from catalog.
* **Stock check**  — fuzzy-match product, show availability.
* **Order status** — fetch most recent order for this customer.
* **General help** — show a help menu with available actions.

If the AI price/stock generator is unavailable, a deterministic
template fallback is used.  Queries that TELETRAAN cannot answer
(medical advice, delivery disputes, custom pricing) are escalated
to the human operator via the ``HANDOFF`` state.
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import Language, OrderStatus, SessionStateA
from app.db.models.session import Session
from app.db.repositories.order_repo import OrderRepository
from app.db.repositories.session_repo import SessionRepository
from app.inventory.catalog_service import CatalogService
from app.whatsapp.message_types import build_button_message, build_text_message


# ═══════════════════════════════════════════════════════════════════
# KEYWORD SETS  —  keep lowercase, order matters for overlap
# ═══════════════════════════════════════════════════════════════════

_PRICE_KW = {"price", "rate", "kitne", "kimat", "qeemat", "kya rate", "price check"}
_STOCK_KW = {"available", "stock", "hai kya", "milega", "mil", "in stock", "stock check"}
_ORDER_KW = {
    "order status", "mera order", "order kahan", "order tracking",
    "where is my order", "kahan hai", "kab aayega",
}
_HELP_KW = {"help", "madad", "kaise", "how", "guide", "menu"}
_BACK_KW = {"back", "wapas", "menu", "main menu"}
_ORDER_START_KW = {"order", "order karna", "haan order", "place order", "yes order"}

# Things TELETRAAN does NOT handle → HANDOFF
_HANDOFF_KW = {
    "doctor", "medicine advice", "side effect", "side effects",
    "dispute", "refund", "custom price", "custom rate",
    "special deal", "return",
}


# ═══════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════


def _get_prompts(language: str) -> dict[str, str]:
    """Return inquiry flow prompt templates.

    Args:
        language: ``'english'`` or ``'roman_urdu'``.

    Returns:
        Dict of prompt key → template string.
    """
    if language == "english":
        return {
            "welcome": (
                "\u2753 *How can I help?*\n\n"
                "You can ask about:\n"
                "\U0001f4b0 Medicine *price*\n"
                "\U0001f4e6 Medicine *stock*\n"
                "\U0001f4cb *Order status*\n"
                "\u2753 General *help*\n\n"
                "Type your question or say *back* to return."
            ),
            "price_found": (
                "\U0001f4b0 *{name}*\n"
                "Price: Rs. {price_display} per {unit}\n"
                "{stock_status}\n\n"
                "Want to order? Say *order*."
            ),
            "stock_found": (
                "\U0001f4e6 *{name}*\n"
                "Status: {stock_status}\n"
                "Price: Rs. {price_display} per {unit}\n\n"
                "Want to order? Say *order*."
            ),
            "not_found": (
                "\u274c Medicine not found in catalog.\n"
                "Try a different name or check spelling."
            ),
            "order_status": (
                "\U0001f4cb *Order #{order_number}*\n"
                "Status: {status}\n"
                "Items: {item_count}\n"
                "Total: Rs. {total_display}\n"
                "Placed: {date}"
            ),
            "no_orders": (
                "\U0001f4cb You don't have any recent orders.\n"
                "Say *order* to place a new one!"
            ),
            "help": (
                "\u2753 *Help Menu*\n\n"
                "1\ufe0f\u20e3 *Order* — Place a new medicine order\n"
                "2\ufe0f\u20e3 *Catalog* — Browse available medicines\n"
                "3\ufe0f\u20e3 *Complaint* — File a complaint\n"
                "4\ufe0f\u20e3 *Profile* — View/edit your profile\n"
                "5\ufe0f\u20e3 *Price/Stock* — Check medicine availability\n\n"
                "Say any of these or *back* for main menu."
            ),
            "handoff": (
                "\u26a0\ufe0f This question needs human assistance.\n"
                "Connecting you with the distributor..."
            ),
            "ask_which": "Which medicine do you want to check?",
            "btn_order": "\U0001f6d2 Order",
            "btn_back": "\u2b05\ufe0f Back",
        }
    return {
        "welcome": (
            "\u2753 *Kya madad chahiye?*\n\n"
            "Aap pooch sakte hain:\n"
            "\U0001f4b0 Medicine ki *price*\n"
            "\U0001f4e6 Medicine ka *stock*\n"
            "\U0001f4cb *Order status*\n"
            "\u2753 General *help*\n\n"
            "Sawal likhein ya *wapas* likhein menu ke liye."
        ),
        "price_found": (
            "\U0001f4b0 *{name}*\n"
            "Price: Rs. {price_display} per {unit}\n"
            "{stock_status}\n\n"
            "Order karna hai? *order* likhein."
        ),
        "stock_found": (
            "\U0001f4e6 *{name}*\n"
            "Status: {stock_status}\n"
            "Price: Rs. {price_display} per {unit}\n\n"
            "Order karna hai? *order* likhein."
        ),
        "not_found": (
            "\u274c Medicine catalog mein nahi mili.\n"
            "Doosra naam ya spelling try karein."
        ),
        "order_status": (
            "\U0001f4cb *Order #{order_number}*\n"
            "Status: {status}\n"
            "Items: {item_count}\n"
            "Total: Rs. {total_display}\n"
            "Order date: {date}"
        ),
        "no_orders": (
            "\U0001f4cb Aapka koi recent order nahi hai.\n"
            "*order* likhein naya order dene ke liye!"
        ),
        "help": (
            "\u2753 *Help Menu*\n\n"
            "1\ufe0f\u20e3 *Order* — Naya order dein\n"
            "2\ufe0f\u20e3 *Catalog* — Medicines dekhein\n"
            "3\ufe0f\u20e3 *Complaint* — Shikayat darj karein\n"
            "4\ufe0f\u20e3 *Profile* — Profile dekhein/badlein\n"
            "5\ufe0f\u20e3 *Price/Stock* — Medicine ki availability\n\n"
            "Koi bhi likhein ya *wapas* main menu ke liye."
        ),
        "handoff": (
            "\u26a0\ufe0f Yeh sawal insaan se poochna hoga.\n"
            "Distributor se connect kar rahe hain..."
        ),
        "ask_which": "Konsi medicine check karni hai?",
        "btn_order": "\U0001f6d2 Order",
        "btn_back": "\u2b05\ufe0f Wapas",
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════


async def handle_inquiry_step(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    session_repo: SessionRepository,
    order_repo: OrderRepository | None = None,
    catalog_service: CatalogService | None = None,
) -> list[dict]:
    """Handle an inquiry-state message and return response payloads.

    Sub-classifies the incoming message by keyword overlap into
    price, stock, order-status, help, or escalation.  If no sub-intent
    is detected, falls back to the welcome / help prompt.

    Args:
        session: Current session.
        text: Customer text input.
        button_id: Interactive button/list ID if pressed.
        session_repo: For state persistence.
        order_repo: For order lookups.
        catalog_service: For price/stock lookups.

    Returns:
        List of WhatsApp message payloads.
    """
    language = (
        "english"
        if getattr(session, "language", None) == Language.ENGLISH
        else "roman_urdu"
    )
    to = session.whatsapp_number
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    # ── Navigation ──────────────────────────────────────────────
    if button_id == "inquiry_back" or _matches(text_lower, _BACK_KW):
        return await _go_to_menu(session, session_repo)

    if button_id == "inquiry_order" or _matches(text_lower, _ORDER_START_KW):
        return await _go_to_order(session, session_repo)

    # ── Handoff keywords ────────────────────────────────────────
    if _matches(text_lower, _HANDOFF_KW):
        return await _go_to_handoff(session, session_repo, prompts, to)

    # ── Sub-intent classification ───────────────────────────────
    sub_intent = _classify_sub_intent(text_lower)

    if sub_intent == "price":
        return await _handle_price(
            session, text_lower, prompts, to,
            catalog_service=catalog_service,
        )

    if sub_intent == "stock":
        return await _handle_stock(
            session, text_lower, prompts, to,
            catalog_service=catalog_service,
        )

    if sub_intent == "order_status":
        return await _handle_order_status(
            session, prompts, to,
            order_repo=order_repo,
        )

    if sub_intent == "help":
        return [build_text_message(to, prompts["help"])]

    # ── Unrecognised — maybe a medicine name? ───────────────────
    if len(text_lower) >= 3:
        result = await _try_catalog_lookup(
            text_lower, prompts, to,
            catalog_service=catalog_service,
        )
        if result:
            return result

    # Default: re-show welcome
    return [build_text_message(to, prompts["welcome"])]


async def start_inquiry(
    session: Session,
    *,
    session_repo: SessionRepository,
) -> list[dict]:
    """Transition to INQUIRY_RESPONSE and show welcome prompt.

    Args:
        session: Current session.
        session_repo: For state persistence.

    Returns:
        Welcome message with inquiry options.
    """
    language = (
        "english"
        if getattr(session, "language", None) == Language.ENGLISH
        else "roman_urdu"
    )
    to = session.whatsapp_number
    prompts = _get_prompts(language)

    tr = transition(
        session.current_state,
        SessionStateA.INQUIRY_RESPONSE.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.INQUIRY_RESPONSE.value,
            previous_state=session.current_state,
        )

    return [build_button_message(
        to,
        prompts["welcome"],
        buttons=[
            ("inquiry_back", prompts["btn_back"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# SUB-INTENT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════


def _classify_sub_intent(text: str) -> str | None:
    """Classify the inquiry sub-intent from text.

    Args:
        text: Lowered user text.

    Returns:
        Sub-intent string or ``None``.
    """
    if _matches(text, _ORDER_KW):
        return "order_status"
    if _matches(text, _PRICE_KW):
        return "price"
    if _matches(text, _STOCK_KW):
        return "stock"
    if _matches(text, _HELP_KW):
        return "help"
    return None


def _matches(text: str, keywords: set[str]) -> bool:
    """Check if text contains any keyword from the set.

    Args:
        text: Lowered user text.
        keywords: Set of keyword patterns.

    Returns:
        True if any keyword found in text.
    """
    return any(kw in text for kw in keywords)


# ═══════════════════════════════════════════════════════════════════
# PRICE HANDLER
# ═══════════════════════════════════════════════════════════════════


async def _handle_price(
    session: Session,
    text: str,
    prompts: dict[str, str],
    to: str,
    *,
    catalog_service: CatalogService | None,
) -> list[dict]:
    """Look up price for a medicine name extracted from text."""
    medicine_name = _extract_medicine_name(text, _PRICE_KW)
    if not medicine_name:
        return [build_text_message(to, prompts["ask_which"])]

    cat = catalog_service or CatalogService()
    result = await cat.find_medicine(
        str(session.distributor_id),
        medicine_name,
    )

    if not result or not result.matches:
        return [build_text_message(to, prompts["not_found"])]

    top = result.matches[0]
    item = top.catalog_item
    price_display = f"{item.price_per_unit_paisas / 100:.2f}"
    stock_status = (
        "\u2705 In stock" if item.is_in_stock else "\u274c Out of stock"
    )

    return [build_button_message(
        to,
        prompts["price_found"].format(
            name=item.medicine_name,
            price_display=price_display,
            unit=item.unit or "unit",
            stock_status=stock_status,
        ),
        buttons=[
            ("inquiry_order", prompts["btn_order"]),
            ("inquiry_back", prompts["btn_back"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# STOCK HANDLER
# ═══════════════════════════════════════════════════════════════════


async def _handle_stock(
    session: Session,
    text: str,
    prompts: dict[str, str],
    to: str,
    *,
    catalog_service: CatalogService | None,
) -> list[dict]:
    """Look up stock availability for a medicine."""
    medicine_name = _extract_medicine_name(text, _STOCK_KW)
    if not medicine_name:
        return [build_text_message(to, prompts["ask_which"])]

    cat = catalog_service or CatalogService()
    result = await cat.find_medicine(
        str(session.distributor_id),
        medicine_name,
    )

    if not result or not result.matches:
        return [build_text_message(to, prompts["not_found"])]

    top = result.matches[0]
    item = top.catalog_item
    price_display = f"{item.price_per_unit_paisas / 100:.2f}"
    stock_status = (
        "\u2705 In stock" if item.is_in_stock else "\u274c Out of stock"
    )

    return [build_button_message(
        to,
        prompts["stock_found"].format(
            name=item.medicine_name,
            stock_status=stock_status,
            price_display=price_display,
            unit=item.unit or "unit",
        ),
        buttons=[
            ("inquiry_order", prompts["btn_order"]),
            ("inquiry_back", prompts["btn_back"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# ORDER STATUS HANDLER
# ═══════════════════════════════════════════════════════════════════


async def _handle_order_status(
    session: Session,
    prompts: dict[str, str],
    to: str,
    *,
    order_repo: OrderRepository | None,
) -> list[dict]:
    """Show most recent order for this customer."""
    if not session.customer_id:
        return [build_text_message(to, prompts["no_orders"])]

    repo = order_repo or OrderRepository()
    try:
        orders = await repo.get_customer_orders(
            str(session.distributor_id),
            str(session.customer_id),
            limit=1,
        )
    except Exception as exc:
        logger.error("inquiry_flow.order_lookup_failed", error=str(exc))
        return [build_text_message(to, prompts["no_orders"])]

    if not orders:
        return [build_text_message(to, prompts["no_orders"])]

    order = orders[0]
    total_display = f"{order.total_amount_paisas / 100:.2f}" if order.total_amount_paisas else "0.00"
    date_str = order.created_at.strftime("%d %b %Y") if order.created_at else "—"
    status_display = _format_status(order.status)

    return [build_button_message(
        to,
        prompts["order_status"].format(
            order_number=order.order_number or "—",
            status=status_display,
            item_count=order.item_count or 0,
            total_display=total_display,
            date=date_str,
        ),
        buttons=[
            ("inquiry_order", prompts["btn_order"]),
            ("inquiry_back", prompts["btn_back"]),
        ],
    )]


def _format_status(status: str | None) -> str:
    """Pretty-print an order status.

    Args:
        status: Raw status string.

    Returns:
        Emoji-prefixed status label.
    """
    status_map: dict[str, str] = {
        OrderStatus.PENDING: "\u23f3 Pending",
        OrderStatus.CONFIRMED: "\u2705 Confirmed",
        OrderStatus.PROCESSING: "\u2699\ufe0f Processing",
        OrderStatus.DISPATCHED: "\U0001f69a Dispatched",
        OrderStatus.DELIVERED: "\U0001f4e6 Delivered",
        OrderStatus.CANCELLED: "\u274c Cancelled",
        OrderStatus.RETURNED: "\u21a9\ufe0f Returned",
        OrderStatus.PARTIALLY_FULFILLED: "\u26a0\ufe0f Partial",
    }
    return status_map.get(status or "", status or "Unknown")


# ═══════════════════════════════════════════════════════════════════
# CATALOG FALLBACK
# ═══════════════════════════════════════════════════════════════════


async def _try_catalog_lookup(
    text: str,
    prompts: dict[str, str],
    to: str,
    *,
    catalog_service: CatalogService | None,
) -> list[dict] | None:
    """Try to match text as a medicine name.

    Args:
        text: Lowered user text.
        prompts: Prompt dict.
        to: WhatsApp recipient.
        catalog_service: Optional catalog service override.

    Returns:
        Message list if a match was found, ``None`` otherwise.
    """
    cat = catalog_service or CatalogService()
    try:
        from app.inventory.fuzzy_matcher import fuzzy_match_medicine

        result = await cat.find_medicine("", text)
        if result and result.matches and result.matches[0].score >= 70.0:
            top = result.matches[0]
            item = top.catalog_item
            price_display = f"{item.price_per_unit_paisas / 100:.2f}"
            stock_status = (
                "\u2705 In stock" if item.is_in_stock
                else "\u274c Out of stock"
            )
            return [build_button_message(
                to,
                prompts["price_found"].format(
                    name=item.medicine_name,
                    price_display=price_display,
                    unit=item.unit or "unit",
                    stock_status=stock_status,
                ),
                buttons=[
                    ("inquiry_order", prompts["btn_order"]),
                    ("inquiry_back", prompts["btn_back"]),
                ],
            )]
    except Exception as exc:
        logger.debug("inquiry_flow.catalog_fallback_failed", error=str(exc))

    return None


# ═══════════════════════════════════════════════════════════════════
# TEXT EXTRACTION
# ═══════════════════════════════════════════════════════════════════


_STRIP_PATTERN = re.compile(
    r"\b(price|rate|kitne|kimat|qeemat|kya rate|price check"
    r"|available|stock|hai kya|milega|mil|in stock|stock check"
    r"|check|kya|ka|ki|ke|of|the|for|mujhe|batao|bataein)\b",
    re.IGNORECASE,
)


def _extract_medicine_name(text: str, intent_kw: set[str]) -> str:
    """Strip intent keywords from text to extract the medicine name.

    Args:
        text: Lowered user text.
        intent_kw: Intent keyword set to strip.

    Returns:
        Cleaned medicine name, or empty string.
    """
    cleaned = text
    for kw in intent_kw:
        cleaned = cleaned.replace(kw, " ")
    cleaned = _STRIP_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ═══════════════════════════════════════════════════════════════════
# STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════


async def _go_to_menu(
    session: Session,
    session_repo: SessionRepository,
) -> list[dict]:
    """Transition back to MAIN_MENU.

    Args:
        session: Current session.
        session_repo: For state persistence.

    Returns:
        Empty list — main handler shows menu.
    """
    tr = transition(
        session.current_state,
        SessionStateA.MAIN_MENU.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=session.current_state,
        )
    return []


async def _go_to_order(
    session: Session,
    session_repo: SessionRepository,
) -> list[dict]:
    """Transition to ORDER_ITEM_COLLECTION.

    Args:
        session: Current session.
        session_repo: For state persistence.

    Returns:
        Empty list — order flow will show its own prompt.
    """
    tr = transition(
        session.current_state,
        SessionStateA.ORDER_ITEM_COLLECTION.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            previous_state=session.current_state,
        )
    return []


async def _go_to_handoff(
    session: Session,
    session_repo: SessionRepository,
    prompts: dict[str, str],
    to: str,
) -> list[dict]:
    """Transition to HANDOFF for human operator assistance.

    Args:
        session: Current session.
        session_repo: For persistence.
        prompts: Prompt dict.
        to: WhatsApp recipient.

    Returns:
        Handoff notification message.
    """
    tr = transition(
        session.current_state,
        SessionStateA.HANDOFF.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.HANDOFF.value,
            previous_state=session.current_state,
        )
        logger.info(
            "inquiry_flow.handoff",
            session_id=str(session.id),
        )
    return [build_text_message(to, prompts["handoff"])]
