"""Channel A — customer profile view / edit flow.

Two-state flow:

1. ``PROFILE_VIEW`` — show customer details, offer edit
2. ``PROFILE_EDIT`` — update name, shop name, or address

After edit completes, returns to ``PROFILE_VIEW`` to show updated
data.  ``MAIN_MENU`` transition is always available.
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import Language, MAX_ADDRESS_LENGTH, MAX_NAME_LENGTH, SessionStateA
from app.db.models.customer import Customer, CustomerUpdate
from app.db.models.session import Session
from app.db.repositories.customer_repo import CustomerRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import build_button_message, build_text_message


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

_EDIT_ID = "profile_edit"
_BACK_ID = "profile_back"
_EDIT_NAME_ID = "profile_edit_name"
_EDIT_SHOP_ID = "profile_edit_shop"
_EDIT_ADDR_ID = "profile_edit_address"

_NAME_RE = re.compile(r"^[\w\s.\-']{2,255}$", re.UNICODE)


def _get_prompts(language: str) -> dict[str, str]:
    """Return profile flow prompt templates.

    Args:
        language: ``'english'`` or ``'roman_urdu'``.

    Returns:
        Dict of prompt key → template string.
    """
    if language == "english":
        return {
            "view": (
                "\U0001f464 *Your Profile*\n\n"
                "\U0001f464 Name: {name}\n"
                "\U0001f3ea Shop: {shop_name}\n"
                "\U0001f4cd Address: {address}\n"
                "\U0001f4f1 WhatsApp: {phone_display}\n\n"
                "Want to edit? Say *edit name*, *edit shop*, "
                "or *edit address*."
            ),
            "ask_new_name": "Enter your new name:",
            "ask_new_shop": "Enter your new shop name:",
            "ask_new_address": (
                "Enter your new address:\n(Street, Area, City)"
            ),
            "updated": "\u2705 Updated: {field} → {value}",
            "invalid_name": (
                "Please enter a valid name (2-255 characters, "
                "letters and spaces)."
            ),
            "invalid_shop": "Please enter a valid shop name (2-255 characters).",
            "invalid_address": "Please enter a valid address (5-500 characters).",
            "no_customer": (
                "\u26a0\ufe0f Profile not found.\n"
                "Please complete onboarding first."
            ),
            "btn_edit": "\u270f\ufe0f Edit",
            "btn_back": "\u2b05\ufe0f Back",
        }
    return {
        "view": (
            "\U0001f464 *Aapki Profile*\n\n"
            "\U0001f464 Naam: {name}\n"
            "\U0001f3ea Dukaan: {shop_name}\n"
            "\U0001f4cd Pata: {address}\n"
            "\U0001f4f1 WhatsApp: {phone_display}\n\n"
            "Edit karna hai? *edit name*, *edit shop*, "
            "ya *edit address* likhein."
        ),
        "ask_new_name": "Naya naam likhein:",
        "ask_new_shop": "Nayi dukaan ka naam likhein:",
        "ask_new_address": (
            "Naya pata likhein:\n(Street, Area, City)"
        ),
        "updated": "\u2705 Update: {field} → {value}",
        "invalid_name": (
            "Sahi naam likhein (2-255 characters, "
            "sirf letters aur spaces)."
        ),
        "invalid_shop": "Sahi dukaan ka naam likhein (2-255 characters).",
        "invalid_address": "Sahi pata likhein (5-500 characters).",
        "no_customer": (
            "\u26a0\ufe0f Profile nahi mili.\n"
            "Pehle registration mukammal karein."
        ),
        "btn_edit": "\u270f\ufe0f Edit",
        "btn_back": "\u2b05\ufe0f Wapas",
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════


async def handle_profile_step(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None = None,
) -> list[dict]:
    """Dispatch to profile view or edit handler.

    Args:
        session: Current session.
        text: Customer text input.
        button_id: Button ID if interactive.
        session_repo: For state persistence.
        customer_repo: For customer CRUD.

    Returns:
        List of WhatsApp message payloads.
    """
    state = session.current_state
    language = (
        "english"
        if getattr(session, "language", None) == Language.ENGLISH
        else "roman_urdu"
    )
    to = session.whatsapp_number
    c_repo = customer_repo or CustomerRepository()

    if state == SessionStateA.PROFILE_VIEW.value:
        return await _handle_profile_view(
            session, text, button_id=button_id,
            language=language, to=to,
            session_repo=session_repo, customer_repo=c_repo,
        )

    if state == SessionStateA.PROFILE_EDIT.value:
        return await _handle_profile_edit(
            session, text, button_id=button_id,
            language=language, to=to,
            session_repo=session_repo, customer_repo=c_repo,
        )

    return []


async def start_profile(
    session: Session,
    *,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None = None,
) -> list[dict]:
    """Enter profile view mode and show current details.

    Args:
        session: Current session.
        session_repo: For state persistence.
        customer_repo: For fetching customer data.

    Returns:
        Profile summary message.
    """
    language = (
        "english"
        if getattr(session, "language", None) == Language.ENGLISH
        else "roman_urdu"
    )
    to = session.whatsapp_number
    prompts = _get_prompts(language)
    c_repo = customer_repo or CustomerRepository()

    tr = transition(
        session.current_state,
        SessionStateA.PROFILE_VIEW.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.PROFILE_VIEW.value,
            previous_state=session.current_state,
        )

    if not session.customer_id:
        return [build_text_message(to, prompts["no_customer"])]

    customer = await c_repo.get_by_id(
        str(session.customer_id),
        distributor_id=str(session.distributor_id),
    )
    if not customer:
        return [build_text_message(to, prompts["no_customer"])]

    phone_display = f"****{to[-4:]}" if len(to) >= 4 else to

    return [build_button_message(
        to,
        prompts["view"].format(
            name=customer.name or "—",
            shop_name=customer.shop_name or "—",
            address=customer.address or "—",
            phone_display=phone_display,
        ),
        buttons=[
            (_EDIT_ID, prompts["btn_edit"]),
            (_BACK_ID, prompts["btn_back"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# STATE: PROFILE_VIEW
# ═══════════════════════════════════════════════════════════════════


async def _handle_profile_view(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository,
) -> list[dict]:
    """Handle view state — detect edit intent or go back."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

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
        return []

    # Detect edit intent
    edit_field = None
    if button_id == _EDIT_ID or "edit" in text_lower:
        if "name" in text_lower or "naam" in text_lower:
            edit_field = "name"
        elif "shop" in text_lower or "dukaan" in text_lower:
            edit_field = "shop_name"
        elif "address" in text_lower or "pata" in text_lower:
            edit_field = "address"
        else:
            edit_field = "name"  # Default to name if generic "edit"

    if edit_field:
        state_data = dict(session.state_data or {})
        state_data["profile_edit_field"] = edit_field

        tr = transition(
            session.current_state,
            SessionStateA.PROFILE_EDIT.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.PROFILE_EDIT.value,
            previous_state=session.current_state,
            state_data=state_data,
        )

        field_prompts = {
            "name": prompts["ask_new_name"],
            "shop_name": prompts["ask_new_shop"],
            "address": prompts["ask_new_address"],
        }
        return [build_text_message(to, field_prompts[edit_field])]

    # Unrecognised — re-show profile
    return await start_profile(
        session, session_repo=session_repo, customer_repo=customer_repo,
    )


# ═══════════════════════════════════════════════════════════════════
# STATE: PROFILE_EDIT
# ═══════════════════════════════════════════════════════════════════


async def _handle_profile_edit(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository,
) -> list[dict]:
    """Handle edit state — validate new value and persist."""
    prompts = _get_prompts(language)
    state_data = session.state_data or {}
    field = state_data.get("profile_edit_field", "name")
    value = text.strip()

    # Validate
    if field == "name":
        if not _NAME_RE.match(value) or len(value) > MAX_NAME_LENGTH:
            return [build_text_message(to, prompts["invalid_name"])]
        value = value.title()
        update = CustomerUpdate(name=value)
        display_field = "Name" if language == "english" else "Naam"

    elif field == "shop_name":
        if len(value) < 2 or len(value) > MAX_NAME_LENGTH:
            return [build_text_message(to, prompts["invalid_shop"])]
        update = CustomerUpdate(shop_name=value)
        display_field = "Shop" if language == "english" else "Dukaan"

    elif field == "address":
        if len(value) < 5 or len(value) > MAX_ADDRESS_LENGTH:
            return [build_text_message(to, prompts["invalid_address"])]
        update = CustomerUpdate(address=value)
        display_field = "Address" if language == "english" else "Pata"

    else:
        return [build_text_message(to, prompts["invalid_name"])]

    if not session.customer_id:
        return [build_text_message(to, prompts["no_customer"])]

    # Persist update
    try:
        await customer_repo.update(
            str(session.customer_id),
            update,
            distributor_id=str(session.distributor_id),
        )
        logger.info(
            "profile_flow.updated",
            field=field,
            customer_id=str(session.customer_id),
        )
    except Exception as exc:
        logger.error("profile_flow.update_failed", error=str(exc))
        return [build_text_message(
            to,
            "Update failed. Please try again."
            if language == "english"
            else "Update fail hua. Dobara try karein.",
        )]

    # Clear edit field, go back to view
    clean_data = {
        k: v for k, v in state_data.items()
        if k != "profile_edit_field"
    }
    tr = transition(
        session.current_state,
        SessionStateA.PROFILE_VIEW.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.PROFILE_VIEW.value,
        previous_state=session.current_state,
        state_data=clean_data,
    )

    msgs: list[dict] = [build_text_message(
        to,
        prompts["updated"].format(field=display_field, value=value),
    )]

    # Re-show updated profile
    view_msgs = await start_profile(
        session, session_repo=session_repo, customer_repo=customer_repo,
    )
    msgs.extend(view_msgs)
    return msgs
