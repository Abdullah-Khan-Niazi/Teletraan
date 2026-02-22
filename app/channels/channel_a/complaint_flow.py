"""Channel A — complaint filing flow.

Three-state flow:

1. ``COMPLAINT_DESCRIPTION`` — customer describes the problem
2. ``COMPLAINT_CATEGORY``    — pick a complaint category
3. ``COMPLAINT_CONFIRM``     — review and submit

Complaints are persisted to the ``complaints`` table and the
distributor is notified via the notification service.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import (
    ComplaintCategory,
    ComplaintPriority,
    ComplaintStatus,
    Language,
    SessionStateA,
)
from app.db.models.complaint import ComplaintCreate
from app.db.models.session import Session
from app.db.repositories.complaint_repo import ComplaintRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import (
    build_button_message,
    build_list_message,
    build_text_message,
)


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

_CONFIRM_ID = "complaint_confirm_yes"
_EDIT_ID = "complaint_confirm_edit"
_CANCEL_ID = "complaint_cancel"

_CATEGORY_MAP: dict[str, ComplaintCategory] = {
    "1": ComplaintCategory.WRONG_ITEM,
    "2": ComplaintCategory.LATE_DELIVERY,
    "3": ComplaintCategory.DAMAGED_GOODS,
    "4": ComplaintCategory.EXPIRED_MEDICINE,
    "5": ComplaintCategory.SHORT_QUANTITY,
    "6": ComplaintCategory.BILLING_ERROR,
    "7": ComplaintCategory.OTHER,
    "wrong item": ComplaintCategory.WRONG_ITEM,
    "galat item": ComplaintCategory.WRONG_ITEM,
    "late delivery": ComplaintCategory.LATE_DELIVERY,
    "der se aya": ComplaintCategory.LATE_DELIVERY,
    "damaged": ComplaintCategory.DAMAGED_GOODS,
    "toota hua": ComplaintCategory.DAMAGED_GOODS,
    "expired": ComplaintCategory.EXPIRED_MEDICINE,
    "expire": ComplaintCategory.EXPIRED_MEDICINE,
    "short quantity": ComplaintCategory.SHORT_QUANTITY,
    "kam maal": ComplaintCategory.SHORT_QUANTITY,
    "billing": ComplaintCategory.BILLING_ERROR,
    "bill galat": ComplaintCategory.BILLING_ERROR,
    "other": ComplaintCategory.OTHER,
    "aur": ComplaintCategory.OTHER,
}


def _get_prompts(language: str) -> dict[str, str]:
    """Return complaint flow prompt templates.

    Args:
        language: ``'english'`` or ``'roman_urdu'``.

    Returns:
        Dict of prompt key → template string.
    """
    if language == "english":
        return {
            "start": (
                "\U0001f4dd *File a Complaint*\n\n"
                "Please describe your problem in detail.\n"
                "Include the order number if possible."
            ),
            "ask_category": (
                "\U0001f4c2 What type of issue is this?\n\n"
                "1. Wrong Item\n"
                "2. Late Delivery\n"
                "3. Damaged Goods\n"
                "4. Expired Medicine\n"
                "5. Short Quantity\n"
                "6. Billing Error\n"
                "7. Other\n\n"
                "Reply with the number or category name."
            ),
            "invalid_category": "Please select a valid category (1-7).",
            "confirm_summary": (
                "\u2705 *Complaint Summary:*\n\n"
                "\U0001f4c2 Category: {category}\n"
                "\U0001f4dd Description: {description}\n\n"
                "Submit this complaint?"
            ),
            "submitted": (
                "\u2705 Complaint submitted!\n"
                "Complaint ID: {complaint_id}\n\n"
                "The distributor has been notified. "
                "We'll keep you updated on the resolution."
            ),
            "cancelled": (
                "\u274c Complaint cancelled.\n"
                "You can file a new one anytime."
            ),
            "btn_submit": "\u2705 Submit",
            "btn_edit": "\u270f\ufe0f Edit",
            "btn_cancel": "\u274c Cancel",
        }
    return {
        "start": (
            "\U0001f4dd *Shikayat Darj Karein*\n\n"
            "Apna masla detail mein batayein.\n"
            "Order number bhi likh dein agar yaad ho."
        ),
        "ask_category": (
            "\U0001f4c2 Kis qism ka masla hai?\n\n"
            "1. Galat Item\n"
            "2. Late Delivery\n"
            "3. Damaged / Toota Hua\n"
            "4. Expired Medicine\n"
            "5. Kam Maal / Short Quantity\n"
            "6. Bill Galat\n"
            "7. Aur / Other\n\n"
            "Number ya naam likhen."
        ),
        "invalid_category": "Sahi category choose karein (1-7).",
        "confirm_summary": (
            "\u2705 *Shikayat Ka Khulaasa:*\n\n"
            "\U0001f4c2 Category: {category}\n"
            "\U0001f4dd Detail: {description}\n\n"
            "Yeh shikayat bhejein?"
        ),
        "submitted": (
            "\u2705 Shikayat darj ho gayi!\n"
            "Shikayat ID: {complaint_id}\n\n"
            "Distributor ko batadiya gaya hai. "
            "Update milta rahega."
        ),
        "cancelled": (
            "\u274c Shikayat cancel.\n"
            "Koi bhi waqt nayi shikayat de sakte hain."
        ),
        "btn_submit": "\u2705 Bhejein",
        "btn_edit": "\u270f\ufe0f Badlein",
        "btn_cancel": "\u274c Cancel",
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════


async def handle_complaint_step(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    session_repo: SessionRepository,
    complaint_repo: ComplaintRepository | None = None,
) -> list[dict]:
    """Dispatch to the appropriate complaint-flow handler.

    Args:
        session: Current session.
        text: Customer text input.
        button_id: Button ID if interactive.
        session_repo: For state persistence.
        complaint_repo: For complaint creation.

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
    c_repo = complaint_repo or ComplaintRepository()

    if state == SessionStateA.COMPLAINT_DESCRIPTION.value:
        return await _handle_description(
            session, text, language=language, to=to,
            session_repo=session_repo,
        )

    if state == SessionStateA.COMPLAINT_CATEGORY.value:
        return await _handle_category(
            session, text, language=language, to=to,
            session_repo=session_repo,
        )

    if state == SessionStateA.COMPLAINT_CONFIRM.value:
        return await _handle_confirm(
            session, text, button_id=button_id,
            language=language, to=to,
            session_repo=session_repo,
            complaint_repo=c_repo,
        )

    return []


async def start_complaint(
    session: Session,
    *,
    session_repo: SessionRepository,
) -> list[dict]:
    """Enter complaint flow.

    Args:
        session: Current session.
        session_repo: For state persistence.

    Returns:
        Opening prompt.
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
        SessionStateA.COMPLAINT_DESCRIPTION.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.COMPLAINT_DESCRIPTION.value,
            previous_state=session.current_state,
        )

    return [build_text_message(to, prompts["start"])]


# ═══════════════════════════════════════════════════════════════════
# STATE: COMPLAINT_DESCRIPTION
# ═══════════════════════════════════════════════════════════════════


async def _handle_description(
    session: Session,
    text: str,
    *,
    language: str,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Capture complaint description, move to category selection."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    if text_lower in {"cancel", "cancel karo", "rehne do"}:
        tr = transition(
            session.current_state,
            SessionStateA.MAIN_MENU.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=session.current_state,
        )
        return [build_text_message(to, prompts["cancelled"])]

    if len(text.strip()) < 10:
        return [build_text_message(
            to,
            "Please describe the issue in more detail (at least 10 characters)."
            if language == "english"
            else "Thodi aur detail dein (kam az kam 10 characters).",
        )]

    state_data = dict(session.state_data or {})
    state_data["complaint_description"] = text.strip()[:2000]

    tr = transition(
        session.current_state,
        SessionStateA.COMPLAINT_CATEGORY.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.COMPLAINT_CATEGORY.value,
        previous_state=session.current_state,
        state_data=state_data,
    )

    return [build_text_message(to, prompts["ask_category"])]


# ═══════════════════════════════════════════════════════════════════
# STATE: COMPLAINT_CATEGORY
# ═══════════════════════════════════════════════════════════════════


async def _handle_category(
    session: Session,
    text: str,
    *,
    language: str,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Parse category selection, move to confirmation."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    category = _CATEGORY_MAP.get(text_lower)
    if not category:
        return [build_text_message(to, prompts["invalid_category"])]

    state_data = dict(session.state_data or {})
    state_data["complaint_category"] = category.value

    tr = transition(
        session.current_state,
        SessionStateA.COMPLAINT_CONFIRM.value,
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.COMPLAINT_CONFIRM.value,
        previous_state=session.current_state,
        state_data=state_data,
    )

    description = state_data.get("complaint_description", "")[:100]
    cat_display = category.value.replace("_", " ").title()

    return [build_button_message(
        to,
        prompts["confirm_summary"].format(
            category=cat_display,
            description=description,
        ),
        buttons=[
            (_CONFIRM_ID, prompts["btn_submit"]),
            (_EDIT_ID, prompts["btn_edit"]),
            (_CANCEL_ID, prompts["btn_cancel"]),
        ],
    )]


# ═══════════════════════════════════════════════════════════════════
# STATE: COMPLAINT_CONFIRM
# ═══════════════════════════════════════════════════════════════════


async def _handle_confirm(
    session: Session,
    text: str,
    *,
    button_id: str | None,
    language: str,
    to: str,
    session_repo: SessionRepository,
    complaint_repo: ComplaintRepository,
) -> list[dict]:
    """Submit or cancel the complaint."""
    prompts = _get_prompts(language)
    text_lower = text.strip().lower()

    is_yes = (
        button_id == _CONFIRM_ID
        or text_lower in {"yes", "haan", "submit", "bhejo", "ji"}
    )
    is_edit = (
        button_id == _EDIT_ID
        or text_lower in {"edit", "badlo", "dobara"}
    )
    is_cancel = (
        button_id == _CANCEL_ID
        or text_lower in {"cancel", "nahi", "na", "rehne do"}
    )

    state_data = session.state_data or {}

    if is_yes:
        # Create complaint in DB
        complaint_data = ComplaintCreate(
            distributor_id=session.distributor_id,
            customer_id=session.customer_id,
            category=ComplaintCategory(
                state_data.get("complaint_category", "other")
            ),
            description=state_data.get("complaint_description", ""),
            priority=ComplaintPriority.NORMAL,
            status=ComplaintStatus.OPEN,
        )

        try:
            complaint = await complaint_repo.create(complaint_data)
            complaint_id = str(complaint.id)[:8].upper()

            logger.info(
                "complaint_flow.submitted",
                complaint_id=str(complaint.id),
                category=complaint_data.category.value,
            )

            # Back to menu
            tr = transition(
                session.current_state,
                SessionStateA.MAIN_MENU.value,
            )
            # Clear complaint state data
            clean_data = {
                k: v for k, v in state_data.items()
                if not k.startswith("complaint_")
            }
            await session_repo.update_state(
                str(session.id),
                SessionStateA.MAIN_MENU.value,
                previous_state=session.current_state,
                state_data=clean_data,
            )

            return [build_text_message(
                to, prompts["submitted"].format(complaint_id=complaint_id),
            )]

        except Exception as exc:
            logger.error(
                "complaint_flow.create_failed",
                error=str(exc),
            )
            return [build_text_message(
                to,
                "Sorry, there was an error submitting your complaint. "
                "Please try again."
                if language == "english"
                else "Maafi, shikayat darj karne mein masla hua. "
                "Dobara try karein.",
            )]

    if is_edit:
        # Go back to description
        tr = transition(
            session.current_state,
            SessionStateA.COMPLAINT_DESCRIPTION.value,
        )
        await session_repo.update_state(
            str(session.id),
            SessionStateA.COMPLAINT_DESCRIPTION.value,
            previous_state=session.current_state,
        )
        return [build_text_message(to, prompts["start"])]

    if is_cancel:
        tr = transition(
            session.current_state,
            SessionStateA.MAIN_MENU.value,
        )
        clean_data = {
            k: v for k, v in state_data.items()
            if not k.startswith("complaint_")
        }
        await session_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=session.current_state,
            state_data=clean_data,
        )
        return [build_text_message(to, prompts["cancelled"])]

    # Re-prompt
    description = state_data.get("complaint_description", "")[:100]
    cat_val = state_data.get("complaint_category", "other")
    cat_display = cat_val.replace("_", " ").title()
    return [build_button_message(
        to,
        prompts["confirm_summary"].format(
            category=cat_display,
            description=description,
        ),
        buttons=[
            (_CONFIRM_ID, prompts["btn_submit"]),
            (_EDIT_ID, prompts["btn_edit"]),
            (_CANCEL_ID, prompts["btn_cancel"]),
        ],
    )]
