"""Channel A — catalog browsing flow.

Single-state flow (``CATALOG_BROWSING``) that lets customers:
- Search medicines by name
- Browse categories
- View stock/price info
- Jump to ordering a found item

From here customers can transition to ``ORDER_ITEM_COLLECTION``
(to start ordering) or ``MAIN_MENU`` (to leave).
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import Language, SessionStateA
from app.db.models.session import Session
from app.db.repositories.session_repo import SessionRepository
from app.inventory.catalog_service import CatalogService
from app.inventory.fuzzy_matcher import format_match_options
from app.whatsapp.message_types import (
    build_button_message,
    build_list_message,
    build_text_message,
)


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

_ORDER_ID = "catalog_start_order"
_BACK_ID = "catalog_back_menu"


def _get_prompts(language: str) -> dict[str, str]:
    """Return catalog-browsing prompt templates.

    Args:
        language: ``'english'`` or ``'roman_urdu'``.

    Returns:
        Dict of prompt key → template string.
    """
    if language == "english":
        return {
            "welcome": (
                "\U0001f4da *Catalog*\n\n"
                "Type a medicine name to search.\n"
                "Or say *categories* to browse by category.\n\n"
                "Say *back* to return to menu."
            ),
            "search_result": (
                "\U0001f50d Results for \"{query}\":\n\n"
                "{results}\n\n"
                "Want to order something? Say *order [name]*.\n"
                "Or search again."
            ),
            "no_result": (
                "\u274c No results for \"{query}\".\n"
                "Check spelling and try again."
            ),
            "categories": (
                "\U0001f4c1 *Categories:*\n\n"
                "{category_list}\n\n"
                "Reply with a category name to see items."
            ),
            "category_items": (
                "\U0001f4c2 *{category}:*\n\n"
                "{items}\n\n"
                "Search again or say *back*."
            ),
            "item_detail": (
                "\U0001f48a *{name}*\n"
                "{strength_line}"
                "{brand_line}"
                "Price: Rs.{price}/{unit}\n"
                "Stock: {stock_status}\n\n"
                "Say *order* to add to your order."
            ),
            "empty_catalog": "No items in catalog yet.",
            "btn_order": "\U0001f6d2 Order",
            "btn_back": "\u2b05\ufe0f Back",
        }
    return {
        "welcome": (
            "\U0001f4da *Catalog*\n\n"
            "Medicine ka naam likh kar search karein.\n"
            "Ya *categories* likh kar category se dekhein.\n\n"
            "*back* bolo menu pe jaane ke liye."
        ),
        "search_result": (
            "\U0001f50d \"{query}\" ke results:\n\n"
            "{results}\n\n"
            "Order karna hai? *order [naam]* likhein.\n"
            "Ya dobara search karein."
        ),
        "no_result": (
            "\u274c \"{query}\" nahi mili.\n"
            "Spelling check karein aur try karein."
        ),
        "categories": (
            "\U0001f4c1 *Categories:*\n\n"
            "{category_list}\n\n"
            "Category ka naam likh kar items dekhein."
        ),
        "category_items": (
            "\U0001f4c2 *{category}:*\n\n"
            "{items}\n\n"
            "Dobara search karein ya *back* bolo."
        ),
        "item_detail": (
            "\U0001f48a *{name}*\n"
            "{strength_line}"
            "{brand_line}"
            "Price: Rs.{price}/{unit}\n"
            "Stock: {stock_status}\n\n"
            "*order* bolo order mein add karne ke liye."
        ),
        "empty_catalog": "Catalog abhi khaali hai.",
        "btn_order": "\U0001f6d2 Order",
        "btn_back": "\u2b05\ufe0f Wapas",
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════


async def handle_catalog_step(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    session_repo: SessionRepository,
    catalog_service: CatalogService | None = None,
) -> list[dict]:
    """Handle input in CATALOG_BROWSING state.

    Args:
        session: Current session.
        text: Customer text input.
        button_id: Button ID if interactive reply.
        session_repo: For state persistence.
        catalog_service: For catalog operations.

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
    cat = catalog_service or CatalogService()
    distributor_id = str(session.distributor_id)
    text_lower = text.strip().lower()

    # Back to menu
    if button_id == _BACK_ID or text_lower in {"back", "wapas", "menu"}:
        tr = transition(
            session.current_state,
            SessionStateA.MAIN_MENU.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=session.current_state,
        )
        return []  # Main handler will show menu

    # Start ordering
    if button_id == _ORDER_ID or text_lower.startswith("order"):
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
            return []  # Main handler or order flow will take over

    # Browse categories
    if text_lower in {"categories", "category", "cat"}:
        categories = await cat.get_categories(distributor_id)
        if not categories:
            return [build_text_message(to, prompts["empty_catalog"])]
        cat_list = "\n".join(
            f"{i}. {name} ({count} items)"
            for i, (name, count) in enumerate(categories.items(), 1)
        )
        return [build_text_message(
            to, prompts["categories"].format(category_list=cat_list),
        )]

    # Search for medicine
    match_result = await cat.find_medicine(distributor_id, text)

    if not match_result.matches:
        # Try category match
        categories = await cat.get_categories(distributor_id)
        text_title = text.strip().title()
        if text_title in categories:
            items = await cat.get_items_by_category(
                distributor_id, text_title,
            )
            if items:
                items_text = "\n".join(
                    f"{i}. {it.medicine_name}"
                    + (f" {it.strength}" if it.strength else "")
                    + f" — Rs.{it.price_per_unit_paisas / 100:,.0f}"
                    + (" \u2705" if it.is_in_stock else " \u274c OOS")
                    for i, it in enumerate(items[:15], 1)
                )
                return [build_text_message(
                    to,
                    prompts["category_items"].format(
                        category=text_title,
                        items=items_text,
                    ),
                )]

        return [build_text_message(
            to, prompts["no_result"].format(query=text),
        )]

    # Show results
    results_text = format_match_options(
        match_result.matches, language=language,
    )

    return [build_button_message(
        to,
        prompts["search_result"].format(
            query=text,
            results=results_text,
        ),
        buttons=[
            (_ORDER_ID, prompts["btn_order"]),
            (_BACK_ID, prompts["btn_back"]),
        ],
    )]


async def start_catalog(
    session: Session,
    *,
    session_repo: SessionRepository,
) -> list[dict]:
    """Enter catalog browsing mode.

    Args:
        session: Current session.
        session_repo: For state persistence.

    Returns:
        Welcome message for catalog mode.
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
        SessionStateA.CATALOG_BROWSING.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.CATALOG_BROWSING.value,
            previous_state=session.current_state,
        )

    return [build_text_message(to, prompts["welcome"])]
