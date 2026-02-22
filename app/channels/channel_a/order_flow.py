"""Channel A — complete order flow (item collection → bill → confirm).

Handles six session states:

1. ``ORDER_ITEM_COLLECTION``      — customer adds items by name/qty
2. ``ORDER_ITEM_CONFIRMATION``    — confirm a single fuzzy-matched item
3. ``ORDER_AMBIGUITY_RESOLUTION`` — choose from multiple matches
4. ``ORDER_BILL_PREVIEW``         — show calculated bill, offer edit
5. ``ORDER_DISCOUNT_REQUEST``     — customer asks for discount
6. ``ORDER_FINAL_CONFIRMATION``   — confirm or cancel the order

Each state handler receives the current Session, the customer's text
input (already transcribed if voice), and returns ``list[dict]`` of
WhatsApp message payloads.
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import (
    FUZZY_MATCH_HIGH_CONFIDENCE,
    FUZZY_MATCH_THRESHOLD,
    MAX_ITEMS_PER_ORDER_DEFAULT,
    DiscountRequestStatus,
    InputMethod,
    Language,
    OrderFlowStep,
    SessionStateA,
)
from app.db.models.session import Session
from app.db.repositories.session_repo import SessionRepository
from app.inventory.catalog_service import CatalogService
from app.inventory.fuzzy_matcher import format_match_options
from app.orders.billing_service import BillingService
from app.orders.context_manager import (
    add_item_to_context,
    cancel_order,
    context_to_display_string,
    create_empty_context,
    get_context_from_session,
    mark_bill_shown,
    mark_confirmed,
    recalculate_with_billing,
    remove_item_from_context,
    save_context_to_session,
    update_item_quantity,
    validate_context,
)
from app.whatsapp.message_types import (
    build_button_message,
    build_list_message,
    build_text_message,
)


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

_DONE_KEYWORDS: frozenset[str] = frozenset({
    "done", "bas", "bill", "bill dikhao", "order confirm",
    "hogaya", "aur nahi", "that's all", "that's it", "thats all",
    "ho gaya", "bilkul", "confirm", "check out", "checkout",
})

_CANCEL_KEYWORDS: frozenset[str] = frozenset({
    "cancel", "cancel order", "cancel karo", "nahi chahiye",
    "rehne do", "chhoro", "order cancel",
})

_EDIT_KEYWORDS: frozenset[str] = frozenset({
    "edit", "badlo", "change", "tabdeel", "hata do", "remove",
    "edit karo", "add more", "aur add karo",
})

_CONFIRM_ID = "order_confirm_yes"
_EDIT_ID = "order_confirm_edit"
_CANCEL_ID = "order_confirm_cancel"
_ITEM_CONFIRM_ID = "item_confirm_yes"
_ITEM_REJECT_ID = "item_confirm_no"

_MAX_LIST_ITEMS = 10  # WhatsApp list message row limit


# ═══════════════════════════════════════════════════════════════════
# PROMPTS (bilingual)
# ═══════════════════════════════════════════════════════════════════


def _get_prompts(language: str) -> dict[str, str]:
    """Get order-flow prompt templates.

    Args:
        language: ``'english'`` or ``'roman_urdu'`` (default).

    Returns:
        Dict of prompt keys → format strings.
    """
    if language == "english":
        return {
            "start": (
                "\U0001f4e6 *Order Mode*\n\n"
                "Tell me the medicine name and quantity.\n"
                "Example: _Paracetamol 10 strips_\n\n"
                "When done, say *bill* or *done*."
            ),
            "item_added": (
                "\u2705 Added: {name} × {qty} {unit} @ Rs.{price}\n\n"
                "Want to add more? Or say *done* for bill."
            ),
            "item_added_oos": (
                "\u26a0\ufe0f Added (out of stock): {name} × {qty} {unit} "
                "@ Rs.{price}\n"
                "_Item is currently out of stock but order accepted._\n\n"
                "Want to add more? Or say *done* for bill."
            ),
            "item_confirm": (
                "Did you mean *{name}*?\n"
                "{strength_line}"
                "Price: Rs.{price}/{unit}\n\n"
                "Confirm or reject?"
            ),
            "disambiguate": (
                "Multiple matches found for \"{query}\":\n\n"
                "{options}\n\n"
                "Reply with the number (1-{count}) or type again."
            ),
            "no_match": (
                "\u274c No medicine found for \"{query}\".\n"
                "Please check spelling and try again."
            ),
            "ask_qty": (
                "\U0001f522 How many {unit}s of *{name}* do you want?\n"
                "(Enter a number)"
            ),
            "invalid_qty": "Please enter a valid quantity (1-999).",
            "max_items": (
                "\u26a0\ufe0f Maximum {max} items reached.\n"
                "Say *done* to see your bill."
            ),
            "bill_header": "\U0001f4cb *Your Bill*\n",
            "bill_prompt": (
                "\n\nReply:\n"
                "\u2705 *Confirm* — place order\n"
                "\u270f\ufe0f *Edit* — change items\n"
                "\U0001f4b0 *Discount* — request discount"
            ),
            "discount_ask": (
                "\U0001f4b0 Want a discount? Tell me what you need:\n"
                "Example: _10% discount_ or _2+1 on Paracetamol_"
            ),
            "discount_submitted": (
                "\u2705 Discount request submitted!\n"
                "The distributor will review it.\n\n"
                "Meanwhile, confirm your order or edit it?"
            ),
            "confirm_ask": (
                "\u2705 Ready to confirm your order?\n"
                "This will send the order to the distributor."
            ),
            "order_confirmed": (
                "\U0001f389 *Order Confirmed!*\n\n"
                "Your order has been sent to the distributor.\n"
                "You'll receive updates on delivery.\n\n"
                "Order ID: {order_id}\n"
                "Total: Rs.{total}"
            ),
            "order_cancelled": (
                "\u274c Order cancelled.\n"
                "You can start a new order anytime."
            ),
            "empty_order": "Your order is empty. Add some items first!",
            "edit_which": (
                "\u270f\ufe0f What would you like to change?\n"
                "• *remove [item name/number]* — remove an item\n"
                "• *change [item] to [qty]* — update quantity\n"
                "• *add [item name]* — add more items\n"
                "• *done* — back to bill"
            ),
            "item_removed": "\u2705 Removed: {name}",
            "item_updated": "\u2705 Updated: {name} × {qty} {unit}",
            "validation_error": "\u26a0\ufe0f {error}",
            "btn_confirm": "\u2705 Confirm",
            "btn_edit": "\u270f\ufe0f Edit",
            "btn_cancel": "\u274c Cancel",
            "btn_yes": "\u2705 Yes",
            "btn_no": "\u274c No",
        }
    # ── Roman Urdu (default) ──────────────────────────────────
    return {
        "start": (
            "\U0001f4e6 *Order Mode*\n\n"
            "Medicine ka naam aur quantity bataein.\n"
            "Misal: _Paracetamol 10 strip_\n\n"
            "Jab ho jaye toh *bill* ya *done* kahein."
        ),
        "item_added": (
            "\u2705 Add ho gaya: {name} × {qty} {unit} @ Rs.{price}\n\n"
            "Koi aur cheez? Ya *done* bolo bill ke liye."
        ),
        "item_added_oos": (
            "\u26a0\ufe0f Add ho gaya (stock mein nahi): {name} × {qty} "
            "{unit} @ Rs.{price}\n"
            "_Abhi stock mein nahi hai lekin order accept hai._\n\n"
            "Koi aur cheez? Ya *done* bolo bill ke liye."
        ),
        "item_confirm": (
            "Kya aap *{name}* chahte hain?\n"
            "{strength_line}"
            "Price: Rs.{price}/{unit}\n\n"
            "Confirm ya reject karein?"
        ),
        "disambiguate": (
            "\"{query}\" ke liye kai matches mile:\n\n"
            "{options}\n\n"
            "Number (1-{count}) se chunein ya dobara likhen."
        ),
        "no_match": (
            "\u274c \"{query}\" nahi mili.\n"
            "Spelling check karein aur dobara try karein."
        ),
        "ask_qty": (
            "\U0001f522 *{name}* ke kitne {unit} chahiye?\n"
            "(Number likhein)"
        ),
        "invalid_qty": "Sahi quantity likhein (1-999).",
        "max_items": (
            "\u26a0\ufe0f Maximum {max} items ho gayi.\n"
            "*done* bolo bill dekhne ke liye."
        ),
        "bill_header": "\U0001f4cb *Bill Ka Preview*\n",
        "bill_prompt": (
            "\n\nReply karein:\n"
            "\u2705 *Confirm* — order place karein\n"
            "\u270f\ufe0f *Edit* — items change karein\n"
            "\U0001f4b0 *Discount* — discount maangein"
        ),
        "discount_ask": (
            "\U0001f4b0 Discount chahiye? Bataein kya chahye:\n"
            "Misal: _10% discount_ ya _2+1 Paracetamol pe_"
        ),
        "discount_submitted": (
            "\u2705 Discount request bhej di!\n"
            "Distributor review karega.\n\n"
            "Order confirm karein ya edit karein?"
        ),
        "confirm_ask": (
            "\u2705 Order confirm karna hai?\n"
            "Yeh distributor ko bhej diya jayega."
        ),
        "order_confirmed": (
            "\U0001f389 *Order Confirm Ho Gaya!*\n\n"
            "Aapka order distributor ko bhej diya gaya hai.\n"
            "Delivery updates aate rahenge.\n\n"
            "Order ID: {order_id}\n"
            "Total: Rs.{total}"
        ),
        "order_cancelled": (
            "\u274c Order cancel ho gaya.\n"
            "Koi bhi waqt naya order de sakte hain."
        ),
        "empty_order": "Order khaali hai. Pehle kuch items add karein!",
        "edit_which": (
            "\u270f\ufe0f Kya change karna hai?\n"
            "• *remove [item naam/number]* — hatane ke liye\n"
            "• *change [item] to [qty]* — quantity change\n"
            "• *add [item naam]* — aur add karein\n"
            "• *done* — wapas bill pe"
        ),
        "item_removed": "\u2705 Hata diya: {name}",
        "item_updated": "\u2705 Update: {name} × {qty} {unit}",
        "validation_error": "\u26a0\ufe0f {error}",
        "btn_confirm": "\u2705 Confirm",
        "btn_edit": "\u270f\ufe0f Edit",
        "btn_cancel": "\u274c Cancel",
        "btn_yes": "\u2705 Haan",
        "btn_no": "\u274c Nahi",
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════


async def handle_order_step(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    session_repo: SessionRepository,
    catalog_service: CatalogService | None = None,
    billing_service: BillingService | None = None,
) -> list[dict]:
    """Dispatch to the appropriate order-flow state handler.

    Args:
        session: Current session with state and order context.
        text: Customer's text input (already transcribed if voice).
        button_id: Interactive button ID if customer pressed a button.
        session_repo: For persisting state changes.
        catalog_service: For medicine search and stock checks.
        billing_service: For bill calculation.

    Returns:
        List of WhatsApp message payloads to send.
    """
    state = session.current_state
    language = (
        "english"
        if getattr(session, "language", None) == Language.ENGLISH
        else "roman_urdu"
    )
    to = session.whatsapp_number
    distributor_id = str(session.distributor_id)

    cat = catalog_service or CatalogService()
    bill = billing_service or BillingService()

    if state == SessionStateA.ORDER_ITEM_COLLECTION.value:
        return await _handle_item_collection(
            session, text, button_id=button_id,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, catalog_service=cat,
        )

    if state == SessionStateA.ORDER_ITEM_CONFIRMATION.value:
        return await _handle_item_confirmation(
            session, text, button_id=button_id,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, catalog_service=cat,
        )

    if state == SessionStateA.ORDER_AMBIGUITY_RESOLUTION.value:
        return await _handle_ambiguity_resolution(
            session, text, button_id=button_id,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, catalog_service=cat,
        )

    if state == SessionStateA.ORDER_BILL_PREVIEW.value:
        return await _handle_bill_preview(
            session, text, button_id=button_id,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, billing_service=bill,
        )

    if state == SessionStateA.ORDER_DISCOUNT_REQUEST.value:
        return await _handle_discount_request(
            session, text, button_id=button_id,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, billing_service=bill,
        )

    if state == SessionStateA.ORDER_FINAL_CONFIRMATION.value:
        return await _handle_final_confirmation(
            session, text, button_id=button_id,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, billing_service=bill,
        )

    logger.warning("order_flow.unknown_state", state=state)
    return []


async def start_order(
    session: Session,
    *,
    session_repo: SessionRepository,
) -> list[dict]:
    """Enter order mode — create empty context, transition to ITEM_COLLECTION.

    Args:
        session: Current session.
        session_repo: For state persistence.

    Returns:
        Welcome message for order mode.
    """
    language = (
        "english"
        if getattr(session, "language", None) == Language.ENGLISH
        else "roman_urdu"
    )
    to = session.whatsapp_number
    prompts = _get_prompts(language)

    context = create_empty_context()
    tr = transition(
        session.current_state,
        SessionStateA.ORDER_ITEM_COLLECTION.value,
    )
    if not tr.allowed:
        logger.warning(
            "order_flow.start_blocked",
            current=session.current_state,
            reason=tr.reason,
        )
        return [build_text_message(to, prompts["empty_order"])]

    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_ITEM_COLLECTION.value,
        previous_state=session.current_state,
    )
    await save_context_to_session(
        context, str(session.id), session_repo,
    )

    logger.info("order_flow.started", session_id=str(session.id))
    return [build_text_message(to, prompts["start"])]


# ═══════════════════════════════════════════════════════════════════
# STATE: ORDER_ITEM_COLLECTION
# ═══════════════════════════════════════════════════════════════════


async def _handle_item_collection(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    catalog_service: CatalogService,
) -> list[dict]:
    """Handle customer adding items by name/quantity.

    Parses the input for medicine name and optional quantity, runs
    fuzzy matching, and either auto-adds (high confidence), asks for
    confirmation (medium confidence), or shows disambiguation options
    (low confidence / multiple matches).
    """
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    # Check for "done" / "bill" keywords
    if text_lower in _DONE_KEYWORDS:
        return await _transition_to_bill_preview(
            session, language=language, to=to,
            distributor_id=distributor_id,
            session_repo=session_repo,
        )

    # Check for cancel
    if text_lower in _CANCEL_KEYWORDS:
        return await _cancel_current_order(
            session, language=language, to=to,
            session_repo=session_repo,
        )

    # Check max items
    context = get_context_from_session(session)
    active_items = [i for i in context.items if not i.cancelled]
    if len(active_items) >= MAX_ITEMS_PER_ORDER_DEFAULT:
        return [build_text_message(
            to,
            prompts["max_items"].format(max=MAX_ITEMS_PER_ORDER_DEFAULT),
        )]

    # Parse name and quantity from input
    name_raw, quantity = _parse_item_input(text)

    # Fuzzy search
    match_result = await catalog_service.find_medicine(
        distributor_id, name_raw,
    )

    # No matches
    if not match_result.matches:
        return [build_text_message(
            to,
            prompts["no_match"].format(query=name_raw),
        )]

    # Auto-selected (high confidence single match)
    if match_result.auto_selected:
        return await _auto_add_item(
            session, context, match_result.auto_selected,
            quantity=quantity, name_raw=name_raw,
            language=language, to=to, distributor_id=distributor_id,
            session_repo=session_repo, catalog_service=catalog_service,
        )

    # Needs disambiguation (multiple matches, no clear winner)
    if match_result.needs_disambiguation:
        return await _show_disambiguation(
            session, context, match_result.matches,
            query=name_raw, quantity=quantity,
            language=language, to=to,
            session_repo=session_repo,
        )

    # Single match with medium confidence — ask for confirmation
    top = match_result.matches[0]
    return await _ask_item_confirmation(
        session, context, top,
        quantity=quantity, name_raw=name_raw,
        language=language, to=to,
        session_repo=session_repo,
    )


# ═══════════════════════════════════════════════════════════════════
# STATE: ORDER_ITEM_CONFIRMATION
# ═══════════════════════════════════════════════════════════════════


async def _handle_item_confirmation(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    catalog_service: CatalogService,
) -> list[dict]:
    """Handle yes/no response to item confirmation."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    # Check button responses
    is_yes = (
        button_id == _ITEM_CONFIRM_ID
        or text_lower in {"yes", "haan", "ji", "y", "ha", "1", "confirm"}
    )
    is_no = (
        button_id == _ITEM_REJECT_ID
        or text_lower in {"no", "nahi", "na", "n", "nhi", "2", "reject"}
    )

    state_data = session.state_data or {}
    pending = state_data.get("pending_item", {})

    if is_yes and pending:
        # Add the pending item to context
        context = get_context_from_session(session)
        catalog_id = pending.get("catalog_id")
        quantity = pending.get("quantity", 1)
        name_raw = pending.get("name_raw", "")

        # Check stock
        is_oos = False
        stock_qty = None
        if catalog_id:
            item = await catalog_service.get_item_by_id(
                distributor_id, catalog_id,
            )
            if item:
                is_available, avail = await catalog_service.check_stock_availability(
                    distributor_id, catalog_id, quantity,
                )
                is_oos = not is_available
                stock_qty = avail

        context, line_id = add_item_to_context(
            context,
            catalog_id=catalog_id,
            name_raw=name_raw,
            name_matched=pending.get("name_matched", ""),
            name_display=pending.get("name_display", ""),
            generic_name=pending.get("generic_name"),
            brand_name=pending.get("brand_name"),
            strength=pending.get("strength"),
            form=pending.get("form"),
            unit=pending.get("unit", "strip"),
            quantity=quantity,
            price_per_unit_paisas=pending.get("price", 0),
            is_out_of_stock=is_oos,
            stock_available=stock_qty,
            fuzzy_match_score=pending.get("fuzzy_score"),
        )

        # Save context and transition back to collection
        await save_context_to_session(
            context, str(session.id), session_repo,
        )
        # Clear pending item
        state_data.pop("pending_item", None)
        tr = transition(
            session.current_state,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            previous_state=session.current_state,
            state_data=state_data,
        )

        price_display = pending.get("price", 0) / 100
        template = (
            prompts["item_added_oos"] if is_oos else prompts["item_added"]
        )
        return [build_text_message(
            to,
            template.format(
                name=pending.get("name_display", name_raw),
                qty=quantity,
                unit=pending.get("unit", "strip"),
                price=f"{price_display:,.0f}",
            ),
        )]

    if is_no:
        # Reject — go back to collection
        state_data.pop("pending_item", None)
        tr = transition(
            session.current_state,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            previous_state=session.current_state,
            state_data=state_data,
        )
        return [build_text_message(
            to,
            prompts["no_match"].format(query=pending.get("name_raw", "?")),
        )]

    # Unrecognised response — re-prompt
    return [build_button_message(
        to,
        prompts["item_confirm"].format(
            name=pending.get("name_display", "?"),
            strength_line=(
                f"Strength: {pending['strength']}\n"
                if pending.get("strength")
                else ""
            ),
            price=f"{pending.get('price', 0) / 100:,.0f}",
            unit=pending.get("unit", "strip"),
        ),
        buttons=[
            (_ITEM_CONFIRM_ID, prompts["btn_yes"]),
            (_ITEM_REJECT_ID, prompts["btn_no"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# STATE: ORDER_AMBIGUITY_RESOLUTION
# ═══════════════════════════════════════════════════════════════════


async def _handle_ambiguity_resolution(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    catalog_service: CatalogService,
) -> list[dict]:
    """Handle customer picking from numbered disambiguation list."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()
    state_data = session.state_data or {}
    options = state_data.get("disambiguation_options", [])
    pending_qty = state_data.get("pending_quantity", 1)
    pending_name_raw = state_data.get("pending_name_raw", "")

    # Check for done/cancel
    if text_lower in _DONE_KEYWORDS:
        return await _transition_to_bill_preview(
            session, language=language, to=to,
            distributor_id=distributor_id,
            session_repo=session_repo,
        )
    if text_lower in _CANCEL_KEYWORDS:
        state_data.pop("disambiguation_options", None)
        state_data.pop("pending_quantity", None)
        state_data.pop("pending_name_raw", None)
        tr = transition(
            session.current_state,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            previous_state=session.current_state,
            state_data=state_data,
        )
        return [build_text_message(
            to, prompts["no_match"].format(query=pending_name_raw),
        )]

    # Try to parse selection number
    selection = _parse_selection(text_lower, len(options))
    if selection is not None and 0 <= selection < len(options):
        chosen = options[selection]
        catalog_id = chosen.get("catalog_id")

        # Check stock
        is_oos = False
        stock_qty = None
        if catalog_id:
            is_available, avail = await catalog_service.check_stock_availability(
                distributor_id, catalog_id, pending_qty,
            )
            is_oos = not is_available
            stock_qty = avail

        context = get_context_from_session(session)
        context, line_id = add_item_to_context(
            context,
            catalog_id=catalog_id,
            name_raw=pending_name_raw,
            name_matched=chosen.get("name", ""),
            name_display=chosen.get("name", ""),
            generic_name=chosen.get("generic_name"),
            brand_name=chosen.get("brand_name"),
            strength=chosen.get("strength"),
            form=chosen.get("form"),
            unit=chosen.get("unit", "strip"),
            quantity=pending_qty,
            price_per_unit_paisas=chosen.get("price", 0),
            is_out_of_stock=is_oos,
            stock_available=stock_qty,
            fuzzy_match_score=chosen.get("score"),
        )

        await save_context_to_session(
            context, str(session.id), session_repo,
        )

        # Clear disambiguation state, back to collection
        state_data.pop("disambiguation_options", None)
        state_data.pop("pending_quantity", None)
        state_data.pop("pending_name_raw", None)

        tr = transition(
            session.current_state,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            previous_state=session.current_state,
            state_data=state_data,
        )

        price_display = chosen.get("price", 0) / 100
        template = (
            prompts["item_added_oos"] if is_oos else prompts["item_added"]
        )
        return [build_text_message(
            to,
            template.format(
                name=chosen.get("name", "?"),
                qty=pending_qty,
                unit=chosen.get("unit", "strip"),
                price=f"{price_display:,.0f}",
            ),
        )]

    # Not a valid number — re-show options or treat as new search
    if options:
        opts_text = "\n".join(
            f"{i + 1}. {o.get('name', '?')}"
            + (f" {o.get('strength', '')}" if o.get("strength") else "")
            + f" — Rs.{o.get('price', 0) / 100:,.0f}"
            for i, o in enumerate(options)
        )
        return [build_text_message(
            to,
            prompts["disambiguate"].format(
                query=pending_name_raw,
                options=opts_text,
                count=len(options),
            ),
        )]

    # Fallback — no options stored, go back to collection
    tr = transition(
        session.current_state,
        SessionStateA.ORDER_ITEM_COLLECTION.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_ITEM_COLLECTION.value,
        previous_state=session.current_state,
        state_data=state_data,
    )
    return [build_text_message(to, prompts["start"])]


# ═══════════════════════════════════════════════════════════════════
# STATE: ORDER_BILL_PREVIEW
# ═══════════════════════════════════════════════════════════════════


async def _handle_bill_preview(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    billing_service: BillingService,
) -> list[dict]:
    """Handle bill preview state — confirm, edit, or request discount."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    # Confirm
    if button_id == _CONFIRM_ID or text_lower in {
        "confirm", "haan", "yes", "ji", "ha",
    }:
        return await _transition_to_final_confirm(
            session, language=language, to=to,
            distributor_id=distributor_id,
            session_repo=session_repo,
        )

    # Edit
    if button_id == _EDIT_ID or text_lower in _EDIT_KEYWORDS:
        return await _transition_to_edit(
            session, language=language, to=to,
            session_repo=session_repo,
        )

    # Discount request
    if text_lower in {
        "discount", "discount do", "discount chahiye",
        "discount dein", "riyayat",
    }:
        tr = transition(
            session.current_state,
            SessionStateA.ORDER_DISCOUNT_REQUEST.value,
        )
        if tr.allowed:
            await session_repo.update_state(
                str(session.id),
                SessionStateA.ORDER_DISCOUNT_REQUEST.value,
                previous_state=session.current_state,
            )
            return [build_text_message(to, prompts["discount_ask"])]

    # Cancel
    if button_id == _CANCEL_ID or text_lower in _CANCEL_KEYWORDS:
        return await _cancel_current_order(
            session, language=language, to=to,
            session_repo=session_repo,
        )

    # Unrecognised — re-show bill with buttons
    context = get_context_from_session(session)
    bill_text = billing_service.format_bill_preview(
        context, language=language,
    )
    return [build_button_message(
        to,
        bill_text + prompts["bill_prompt"],
        buttons=[
            (_CONFIRM_ID, prompts["btn_confirm"]),
            (_EDIT_ID, prompts["btn_edit"]),
            (_CANCEL_ID, prompts["btn_cancel"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# STATE: ORDER_DISCOUNT_REQUEST
# ═══════════════════════════════════════════════════════════════════


async def _handle_discount_request(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    billing_service: BillingService,
) -> list[dict]:
    """Handle customer's discount request text."""
    prompts = _get_prompts(language)

    # Store the discount request in context
    context = get_context_from_session(session)

    from app.db.models.order_context import OrderLevelDiscountRequest

    context.order_level_discount_request = OrderLevelDiscountRequest(
        request_text=text.strip(),
        status=DiscountRequestStatus.PENDING,
    )

    await save_context_to_session(
        context, str(session.id), session_repo,
    )

    # Go back to bill preview
    tr = transition(
        session.current_state,
        SessionStateA.ORDER_BILL_PREVIEW.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_BILL_PREVIEW.value,
        previous_state=session.current_state,
    )

    logger.info(
        "order_flow.discount_requested",
        session_id=str(session.id),
        request_text=text[:50],
    )

    return [build_button_message(
        to,
        prompts["discount_submitted"],
        buttons=[
            (_CONFIRM_ID, prompts["btn_confirm"]),
            (_EDIT_ID, prompts["btn_edit"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# STATE: ORDER_FINAL_CONFIRMATION
# ═══════════════════════════════════════════════════════════════════


async def _handle_final_confirmation(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    billing_service: BillingService,
) -> list[dict]:
    """Handle final yes/no confirmation before placing the order."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    is_yes = (
        button_id == _CONFIRM_ID
        or text_lower in {"yes", "confirm", "haan", "ji", "ha", "y", "1"}
    )
    is_no = (
        button_id == _CANCEL_ID
        or text_lower in _CANCEL_KEYWORDS
    )
    is_edit = (
        button_id == _EDIT_ID
        or text_lower in _EDIT_KEYWORDS
    )

    if is_yes:
        context = get_context_from_session(session)

        # Validate
        errors = validate_context(context)
        if errors:
            return [build_text_message(
                to,
                prompts["validation_error"].format(error=errors[0]),
            )]

        # Mark confirmed
        context = mark_confirmed(context)
        await save_context_to_session(
            context, str(session.id), session_repo,
        )

        # Transition to main menu
        tr = transition(
            session.current_state,
            SessionStateA.MAIN_MENU.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=session.current_state,
        )

        total_rs = context.pricing_snapshot.total_paisas / 100
        order_id = str(context.session_order_id)[:8].upper()

        logger.info(
            "order_flow.order_confirmed",
            session_id=str(session.id),
            total=context.pricing_snapshot.total_paisas,
            items=len([i for i in context.items if not i.cancelled]),
        )

        return [build_text_message(
            to,
            prompts["order_confirmed"].format(
                order_id=order_id,
                total=f"{total_rs:,.0f}",
            ),
        )]

    if is_no:
        return await _cancel_current_order(
            session, language=language, to=to,
            session_repo=session_repo,
        )

    if is_edit:
        return await _transition_to_edit(
            session, language=language, to=to,
            session_repo=session_repo,
        )

    # Unrecognised — re-prompt with buttons
    return [build_button_message(
        to,
        prompts["confirm_ask"],
        buttons=[
            (_CONFIRM_ID, prompts["btn_confirm"]),
            (_EDIT_ID, prompts["btn_edit"]),
            (_CANCEL_ID, prompts["btn_cancel"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: AUTO-ADD HIGH-CONFIDENCE ITEM
# ═══════════════════════════════════════════════════════════════════


async def _auto_add_item(
    session: Session,
    context: OrderContext,
    match_result: object,
    *,
    quantity: int,
    name_raw: str,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
    catalog_service: CatalogService,
) -> list[dict]:
    """Add a high-confidence match directly, no confirmation needed.

    Args:
        session: Current session.
        context: Current order context.
        match_result: The auto-selected FuzzyMatchResult.
        quantity: Quantity to add.
        name_raw: Raw customer input.
        language: Display language.
        to: WhatsApp number.
        distributor_id: Tenant scope.
        session_repo: For persistence.
        catalog_service: For stock checks.

    Returns:
        Confirmation message payloads.
    """
    prompts = _get_prompts(language)
    item = match_result.item  # CatalogItem

    # Check stock
    is_oos = False
    stock_qty = None
    is_available, avail = await catalog_service.check_stock_availability(
        distributor_id, str(item.id), quantity,
    )
    is_oos = not is_available
    stock_qty = avail

    context, line_id = add_item_to_context(
        context,
        catalog_id=str(item.id),
        name_raw=name_raw,
        name_matched=item.medicine_name,
        name_display=item.medicine_name,
        generic_name=item.generic_name,
        brand_name=item.brand_name,
        strength=item.strength,
        form=item.form.value if item.form else None,
        unit=item.unit or "strip",
        quantity=quantity,
        price_per_unit_paisas=item.price_per_unit_paisas,
        is_out_of_stock=is_oos,
        stock_available=stock_qty,
        fuzzy_match_score=match_result.score,
    )

    await save_context_to_session(
        context, str(session.id), session_repo,
    )

    price_display = item.price_per_unit_paisas / 100
    template = prompts["item_added_oos"] if is_oos else prompts["item_added"]

    return [build_text_message(
        to,
        template.format(
            name=item.medicine_name,
            qty=quantity,
            unit=item.unit or "strip",
            price=f"{price_display:,.0f}",
        ),
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: ASK ITEM CONFIRMATION (MEDIUM CONFIDENCE)
# ═══════════════════════════════════════════════════════════════════


async def _ask_item_confirmation(
    session: Session,
    context: OrderContext,
    match_result: object,
    *,
    quantity: int,
    name_raw: str,
    language: str,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Show a medium-confidence match and ask for confirmation.

    Stores the match in ``state_data['pending_item']`` for the
    confirmation handler.
    """
    prompts = _get_prompts(language)
    item = match_result.item

    # Store pending item in state_data
    state_data = dict(session.state_data or {})
    state_data["pending_item"] = {
        "catalog_id": str(item.id),
        "name_raw": name_raw,
        "name_matched": item.medicine_name,
        "name_display": item.medicine_name,
        "generic_name": item.generic_name,
        "brand_name": item.brand_name,
        "strength": item.strength,
        "form": item.form.value if item.form else None,
        "unit": item.unit or "strip",
        "price": item.price_per_unit_paisas,
        "quantity": quantity,
        "fuzzy_score": match_result.score,
    }

    tr = transition(
        session.current_state,
        SessionStateA.ORDER_ITEM_CONFIRMATION.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_ITEM_CONFIRMATION.value,
        previous_state=session.current_state,
        state_data=state_data,
    )

    price_display = item.price_per_unit_paisas / 100
    return [build_button_message(
        to,
        prompts["item_confirm"].format(
            name=item.medicine_name,
            strength_line=(
                f"Strength: {item.strength}\n"
                if item.strength
                else ""
            ),
            price=f"{price_display:,.0f}",
            unit=item.unit or "strip",
        ),
        buttons=[
            (_ITEM_CONFIRM_ID, prompts["btn_yes"]),
            (_ITEM_REJECT_ID, prompts["btn_no"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: SHOW DISAMBIGUATION OPTIONS
# ═══════════════════════════════════════════════════════════════════


async def _show_disambiguation(
    session: Session,
    context: OrderContext,
    matches: list,
    *,
    query: str,
    quantity: int,
    language: str,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Show numbered list of match options for customer to pick.

    Stores options in ``state_data['disambiguation_options']``.
    """
    prompts = _get_prompts(language)

    # Cap at max list items
    capped = matches[:_MAX_LIST_ITEMS]

    options_data = []
    for m in capped:
        item = m.item
        options_data.append({
            "catalog_id": str(item.id),
            "name": item.medicine_name,
            "generic_name": item.generic_name,
            "brand_name": item.brand_name,
            "strength": item.strength,
            "form": item.form.value if item.form else None,
            "unit": item.unit or "strip",
            "price": item.price_per_unit_paisas,
            "score": m.score,
        })

    state_data = dict(session.state_data or {})
    state_data["disambiguation_options"] = options_data
    state_data["pending_quantity"] = quantity
    state_data["pending_name_raw"] = query

    tr = transition(
        session.current_state,
        SessionStateA.ORDER_AMBIGUITY_RESOLUTION.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_AMBIGUITY_RESOLUTION.value,
        previous_state=session.current_state,
        state_data=state_data,
    )

    opts_text = format_match_options(capped, language=language)

    return [build_text_message(
        to,
        prompts["disambiguate"].format(
            query=query,
            options=opts_text,
            count=len(capped),
        ),
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: TRANSITION TO BILL PREVIEW
# ═══════════════════════════════════════════════════════════════════


async def _transition_to_bill_preview(
    session: Session,
    *,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Calculate bill and show preview with buttons."""
    prompts = _get_prompts(language)
    context = get_context_from_session(session)

    active_items = [i for i in context.items if not i.cancelled]
    if not active_items:
        return [build_text_message(to, prompts["empty_order"])]

    # Full billing calculation
    context = await recalculate_with_billing(
        context, distributor_id,
    )
    context = mark_bill_shown(context)
    await save_context_to_session(
        context, str(session.id), session_repo,
    )

    tr = transition(
        session.current_state,
        SessionStateA.ORDER_BILL_PREVIEW.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_BILL_PREVIEW.value,
        previous_state=session.current_state,
    )

    billing = BillingService()
    bill_text = billing.format_bill_preview(context, language=language)

    return [build_button_message(
        to,
        bill_text + prompts["bill_prompt"],
        buttons=[
            (_CONFIRM_ID, prompts["btn_confirm"]),
            (_EDIT_ID, prompts["btn_edit"]),
            (_CANCEL_ID, prompts["btn_cancel"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: TRANSITION TO FINAL CONFIRMATION
# ═══════════════════════════════════════════════════════════════════


async def _transition_to_final_confirm(
    session: Session,
    *,
    language: str,
    to: str,
    distributor_id: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Move to final confirmation state."""
    prompts = _get_prompts(language)

    tr = transition(
        session.current_state,
        SessionStateA.ORDER_FINAL_CONFIRMATION.value,
    )
    if not tr.allowed:
        logger.warning(
            "order_flow.final_confirm_blocked",
            reason=tr.reason,
        )
        return [build_text_message(to, prompts["confirm_ask"])]

    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_FINAL_CONFIRMATION.value,
        previous_state=session.current_state,
    )

    return [build_button_message(
        to,
        prompts["confirm_ask"],
        buttons=[
            (_CONFIRM_ID, prompts["btn_confirm"]),
            (_EDIT_ID, prompts["btn_edit"]),
            (_CANCEL_ID, prompts["btn_cancel"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: TRANSITION TO EDIT MODE
# ═══════════════════════════════════════════════════════════════════


async def _transition_to_edit(
    session: Session,
    *,
    language: str,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Go back to item collection for edits."""
    prompts = _get_prompts(language)

    tr = transition(
        session.current_state,
        SessionStateA.ORDER_ITEM_COLLECTION.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.ORDER_ITEM_COLLECTION.value,
        previous_state=session.current_state,
    )

    # Show current order and edit instructions
    context = get_context_from_session(session)
    order_summary = context_to_display_string(context, language=language)

    return [build_text_message(
        to,
        order_summary + "\n\n" + prompts["edit_which"],
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPER: CANCEL ORDER
# ═══════════════════════════════════════════════════════════════════


async def _cancel_current_order(
    session: Session,
    *,
    language: str,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Cancel the current order and return to main menu."""
    prompts = _get_prompts(language)

    context = get_context_from_session(session)
    context = cancel_order(context, reason="customer_cancelled")
    await save_context_to_session(
        context, str(session.id), session_repo,
    )

    tr = transition(
        session.current_state,
        SessionStateA.MAIN_MENU.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.MAIN_MENU.value,
        previous_state=session.current_state,
    )

    logger.info(
        "order_flow.order_cancelled",
        session_id=str(session.id),
    )

    return [build_text_message(to, prompts["order_cancelled"])]


# ═══════════════════════════════════════════════════════════════════
# INPUT PARSING UTILITIES
# ═══════════════════════════════════════════════════════════════════


_QTY_PATTERN = re.compile(
    r"(\d{1,3})\s*(?:strip|strips|box|boxes|bottle|bottles|pc|pcs|pack|packs|"
    r"tablet|tablets|tab|tabs|cap|caps|capsule|capsules|unit|units|"
    r"patti|pattian|dabba|dabbe|botal)?$",
    re.IGNORECASE,
)

_LEADING_QTY_PATTERN = re.compile(
    r"^(\d{1,3})\s+(.+)",
)


def _parse_item_input(text: str) -> tuple[str, int]:
    """Extract medicine name and quantity from customer input.

    Handles formats:
    - ``Paracetamol 10 strips``  → (``'paracetamol'``, 10)
    - ``10 Paracetamol``         → (``'paracetamol'``, 10)
    - ``Paracetamol``            → (``'paracetamol'``, 1)

    Args:
        text: Raw customer input.

    Returns:
        Tuple of (medicine name, quantity).
    """
    text = text.strip()
    if not text:
        return "", 1

    # Try trailing quantity pattern: "Paracetamol 10 strips"
    match = _QTY_PATTERN.search(text)
    if match:
        qty = int(match.group(1))
        name = text[: match.start()].strip()
        if name and 1 <= qty <= 999:
            return name, qty

    # Try leading quantity: "10 Paracetamol"
    match = _LEADING_QTY_PATTERN.match(text)
    if match:
        qty = int(match.group(1))
        name = match.group(2).strip()
        if name and 1 <= qty <= 999:
            return name, qty

    return text, 1


def _parse_selection(text: str, max_options: int) -> int | None:
    """Parse a numbered selection from customer text.

    Args:
        text: Cleaned lowercase text.
        max_options: Maximum valid selection number.

    Returns:
        Zero-based index, or None if not a valid selection.
    """
    text = text.strip()
    if text.isdigit():
        num = int(text)
        if 1 <= num <= max_options:
            return num - 1
    return None
