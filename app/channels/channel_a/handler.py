"""Channel A — main message handler / dispatcher.

Every inbound message for a Channel A session arrives here.  The
handler performs the following in order:

1. **Session refresh** — extend the timeout on every incoming message.
2. **Interrupt detection** — check for universal commands (cancel,
   menu, help, handoff, goodbye) that override the current flow.
3. **State-based dispatch** — route to the correct sub-flow:
   onboarding, order, catalog, complaint, profile, inquiry, or
   handoff.
4. **Main-menu rendering** — show the main menu when in
   ``MAIN_MENU`` or ``IDLE`` state.

The handler returns a list of WhatsApp message payloads ready to be
sent via the WhatsApp client.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.ai.nlu import NLUResult, classify_intent
from app.channels.channel_a.catalog_flow import handle_catalog_step, start_catalog
from app.channels.channel_a.complaint_flow import handle_complaint_step, start_complaint
from app.channels.channel_a.inquiry_flow import handle_inquiry_step, start_inquiry
from app.channels.channel_a.onboarding import handle_onboarding_step
from app.channels.channel_a.order_flow import handle_order_step, start_order
from app.channels.channel_a.profile_flow import handle_profile_step, start_profile
from app.channels.channel_a.state_machine import (
    COMPLAINT_STATES,
    ONBOARDING_STATES,
    ORDER_STATES,
    PROFILE_STATES,
    is_onboarding_state,
    is_order_state,
    transition,
)
from app.channels.interrupts import InterruptType, detect_interrupt, get_target_state_a
from app.channels.session_expiry import (
    is_session_expired,
    refresh_session_timeout,
    should_warn,
)
from app.core.constants import Language, SessionStateA
from app.db.models.session import Session
from app.db.repositories.customer_repo import CustomerRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import build_button_message, build_list_message, build_text_message


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

# Button IDs used in main menu
_BTN_ORDER = "menu_order"
_BTN_CATALOG = "menu_catalog"
_BTN_COMPLAINT = "menu_complaint"

# List row IDs
_ROW_ORDER = "menu_order"
_ROW_CATALOG = "menu_catalog"
_ROW_COMPLAINT = "menu_complaint"
_ROW_PROFILE = "menu_profile"
_ROW_INQUIRY = "menu_inquiry"

# Intent → state mapping for menu selection
_INTENT_STATE_MAP: dict[str, SessionStateA] = {
    "place_order": SessionStateA.ORDER_ITEM_COLLECTION,
    "add_item": SessionStateA.ORDER_ITEM_COLLECTION,
    "reorder": SessionStateA.ORDER_ITEM_COLLECTION,
    "complain": SessionStateA.COMPLAINT_DESCRIPTION,
    "ask_price": SessionStateA.INQUIRY_RESPONSE,
    "ask_stock": SessionStateA.INQUIRY_RESPONSE,
    "ask_delivery": SessionStateA.INQUIRY_RESPONSE,
    "ask_help": SessionStateA.INQUIRY_RESPONSE,
}

# Button/list ID → state mapping
_INTERACTIVE_MAP: dict[str, SessionStateA] = {
    _BTN_ORDER: SessionStateA.ORDER_ITEM_COLLECTION,
    _BTN_CATALOG: SessionStateA.CATALOG_BROWSING,
    _BTN_COMPLAINT: SessionStateA.COMPLAINT_DESCRIPTION,
    _ROW_ORDER: SessionStateA.ORDER_ITEM_COLLECTION,
    _ROW_CATALOG: SessionStateA.CATALOG_BROWSING,
    _ROW_COMPLAINT: SessionStateA.COMPLAINT_DESCRIPTION,
    _ROW_PROFILE: SessionStateA.PROFILE_VIEW,
    _ROW_INQUIRY: SessionStateA.INQUIRY_RESPONSE,
}


# ═══════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════


def _get_prompts(language: str) -> dict[str, str]:
    """Return main handler prompt strings.

    Args:
        language: ``'english'`` or ``'roman_urdu'``.

    Returns:
        Dict of prompt key → template string.
    """
    if language == "english":
        return {
            "menu": (
                "\U0001f4cb *Main Menu*\n\n"
                "What would you like to do?"
            ),
            "welcome_back": (
                "\U0001f44b Welcome back, {name}!\n"
                "How can I help you today?"
            ),
            "expired": (
                "\u23f0 Your session has expired.\n"
                "Starting fresh — how can I help?"
            ),
            "expiry_warning": (
                "\u26a0\ufe0f Your session will expire in a few minutes.\n"
                "Send any message to keep it active."
            ),
            "handoff_active": (
                "\U0001f9d1\u200d\U0001f4bc You're connected to a human operator.\n"
                "They will respond shortly. Say *menu* to return."
            ),
            "goodbye": (
                "\U0001f44b Goodbye! Allah Hafiz.\n"
                "Send a message anytime to start again."
            ),
            "unknown": (
                "I didn't understand that.\n"
                "Say *menu* to see your options, or *help* for assistance."
            ),
            "btn_order": "\U0001f6d2 Place Order",
            "btn_catalog": "\U0001f4e6 Browse Catalog",
            "btn_complaint": "\u270d\ufe0f Complaint/Inquiry",
            "row_order": "Place a new medicine order",
            "row_catalog": "Browse available medicines",
            "row_complaint": "File a complaint",
            "row_profile": "View or edit your profile",
            "row_inquiry": "Ask about prices or orders",
        }
    return {
        "menu": (
            "\U0001f4cb *Main Menu*\n\n"
            "Kya karna chahte hain?"
        ),
        "welcome_back": (
            "\U0001f44b Wapas aane ka shukriya, {name}!\n"
            "Kya madad chahiye aaj?"
        ),
        "expired": (
            "\u23f0 Session khatam ho gaya tha.\n"
            "Naya shuru — kya madad chahiye?"
        ),
        "expiry_warning": (
            "\u26a0\ufe0f Session kuch minutes mein khatam hone wala hai.\n"
            "Active rakhne ke liye koi message bhejein."
        ),
        "handoff_active": (
            "\U0001f9d1\u200d\U0001f4bc Aap insaan se connected hain.\n"
            "Wo jaldi jawab denge. *menu* likhein wapas jaane ke liye."
        ),
        "goodbye": (
            "\U0001f44b Allah Hafiz! Phir milte hain.\n"
            "Kisi bhi waqt message karein."
        ),
        "unknown": (
            "Samajh nahi aaya.\n"
            "*menu* likhein options ke liye, ya *help* likhein."
        ),
        "btn_order": "\U0001f6d2 Order Dein",
        "btn_catalog": "\U0001f4e6 Catalog Dekhein",
        "btn_complaint": "\u270d\ufe0f Shikayat/Sawal",
        "row_order": "Naya medicine order dein",
        "row_catalog": "Available medicines dekhein",
        "row_complaint": "Shikayat darj karein",
        "row_profile": "Profile dekhein ya badlein",
        "row_inquiry": "Price ya order ke baare mein poochein",
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════


async def handle_channel_a_message(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    list_id: str | None = None,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None = None,
) -> list[dict]:
    """Process an inbound Channel A message and return response payloads.

    This is the top-level handler for all Channel A conversations.
    It performs session management, interrupt detection, and dispatches
    to the correct sub-flow based on the current FSM state.

    Args:
        session: Current session (must already be loaded/created).
        text: Customer text input (empty string for interactive-only).
        button_id: Button reply payload ID, if interactive.
        list_id: List reply row ID, if interactive.
        session_repo: For session state persistence.
        customer_repo: For customer data operations.

    Returns:
        List of WhatsApp message payloads to send back.
    """
    to = session.whatsapp_number
    language = _resolve_language(session)
    prompts = _get_prompts(language)
    state = session.current_state
    interactive_id = button_id or list_id

    logger.info(
        "channel_a.message_received",
        state=state,
        has_text=bool(text),
        has_interactive=bool(interactive_id),
        number_suffix=to[-4:] if len(to) >= 4 else to,
    )

    # ── 1. Refresh session timeout ──────────────────────────────
    try:
        await refresh_session_timeout(str(session.id), session_repo)
    except Exception as exc:
        logger.error("channel_a.timeout_refresh_failed", error=str(exc))

    # ── 2. Check session expiry ─────────────────────────────────
    if is_session_expired(session):
        return await _handle_expired_session(
            session, prompts, to, session_repo=session_repo,
        )

    # ── 3. Send expiry warning if in warning window ─────────────
    warning_msgs: list[dict] = []
    if should_warn(session):
        warning_msgs = [build_text_message(to, prompts["expiry_warning"])]

    # ── 4. Interrupt detection ──────────────────────────────────
    if text and not interactive_id:
        interrupt = detect_interrupt(text)
        if interrupt:
            result = await _handle_interrupt(
                session, interrupt, prompts, to,
                session_repo=session_repo,
                customer_repo=customer_repo,
            )
            return warning_msgs + result

    # ── 5. Interactive menu selection (button/list) ─────────────
    if interactive_id and interactive_id in _INTERACTIVE_MAP:
        result = await _handle_menu_selection(
            session, interactive_id, text,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )
        return warning_msgs + result

    # ── 6. State-based dispatch ─────────────────────────────────
    result = await _dispatch_by_state(
        session, text, state,
        button_id=button_id,
        list_id=list_id,
        language=language,
        prompts=prompts,
        to=to,
        session_repo=session_repo,
        customer_repo=customer_repo,
    )
    return warning_msgs + result


# ═══════════════════════════════════════════════════════════════════
# STATE DISPATCH
# ═══════════════════════════════════════════════════════════════════


async def _dispatch_by_state(
    session: Session,
    text: str,
    state: str,
    *,
    button_id: str | None,
    list_id: str | None,
    language: str,
    prompts: dict[str, str],
    to: str,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None,
) -> list[dict]:
    """Route message to the handler for the current FSM state.

    Args:
        session: Current session.
        text: Customer text.
        state: Current state value string.
        button_id: Interactive button ID.
        list_id: Interactive list row ID.
        language: Resolved language string.
        prompts: Main handler prompts.
        to: WhatsApp recipient number.
        session_repo: Session persistence.
        customer_repo: Customer data persistence.

    Returns:
        List of WhatsApp message payloads.
    """
    # ── IDLE — treat as new conversation ────────────────────────
    if state == SessionStateA.IDLE.value:
        return await _handle_idle(
            session, text, prompts, to,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )

    # ── MAIN MENU — classify intent and route ───────────────────
    if state == SessionStateA.MAIN_MENU.value:
        return await _handle_main_menu(
            session, text, prompts, to,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )

    # ── Onboarding ──────────────────────────────────────────────
    if is_onboarding_state(state):
        return await handle_onboarding_step(
            session, text,
            button_id=button_id,
            session_repo=session_repo,
            customer_repo=customer_repo or CustomerRepository(),
        )

    # ── Order flow ──────────────────────────────────────────────
    if is_order_state(state):
        return await handle_order_step(
            session, text,
            button_id=button_id,
            session_repo=session_repo,
        )

    # ── Catalog ─────────────────────────────────────────────────
    if state == SessionStateA.CATALOG_BROWSING.value:
        return await handle_catalog_step(
            session, text,
            button_id=button_id,
            session_repo=session_repo,
        )

    # ── Complaint ───────────────────────────────────────────────
    if state in {s.value for s in COMPLAINT_STATES}:
        return await handle_complaint_step(
            session, text,
            button_id=button_id,
            session_repo=session_repo,
        )

    # ── Profile ─────────────────────────────────────────────────
    if state in {s.value for s in PROFILE_STATES}:
        return await handle_profile_step(
            session, text,
            button_id=button_id,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )

    # ── Inquiry ─────────────────────────────────────────────────
    if state == SessionStateA.INQUIRY_RESPONSE.value:
        return await handle_inquiry_step(
            session, text,
            button_id=button_id,
            session_repo=session_repo,
        )

    # ── Handoff ─────────────────────────────────────────────────
    if state == SessionStateA.HANDOFF.value:
        return _handle_handoff_state(
            session, text, prompts, to,
            button_id=button_id,
        )

    # ── Unknown state — recover to main menu ────────────────────
    logger.warning(
        "channel_a.unknown_state",
        state=state,
        session_id=str(session.id),
    )
    await session_repo.update_state(
        str(session.id),
        SessionStateA.MAIN_MENU.value,
        previous_state=state,
    )
    return await _show_main_menu(to, prompts, language)


# ═══════════════════════════════════════════════════════════════════
# IDLE HANDLER
# ═══════════════════════════════════════════════════════════════════


async def _handle_idle(
    session: Session,
    text: str,
    prompts: dict[str, str],
    to: str,
    *,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None,
) -> list[dict]:
    """Handle a message in IDLE state — determine if new or returning.

    New customers are routed to onboarding.  Returning customers
    see the main menu.

    Args:
        session: Current session.
        text: Customer text.
        prompts: Prompt dict.
        to: WhatsApp recipient.
        session_repo: Session persistence.
        customer_repo: Customer persistence.

    Returns:
        List of message payloads.
    """
    language = _resolve_language(session)

    # Check if customer exists
    if session.customer_id:
        # Returning customer → main menu
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
        return await _show_main_menu(to, prompts, language)

    # New customer → onboarding
    from app.channels.channel_a.state_machine import get_initial_state

    initial = get_initial_state(is_new_customer=True)
    tr = transition(session.current_state, initial.value)
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            initial.value,
            previous_state=session.current_state,
        )

    return await handle_onboarding_step(
        session, text,
        button_id=None,
        session_repo=session_repo,
        customer_repo=customer_repo or CustomerRepository(),
    )


# ═══════════════════════════════════════════════════════════════════
# MAIN MENU HANDLER
# ═══════════════════════════════════════════════════════════════════


async def _handle_main_menu(
    session: Session,
    text: str,
    prompts: dict[str, str],
    to: str,
    *,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None,
) -> list[dict]:
    """Handle text input at the main menu — classify intent and route.

    Uses keyword-based NLU to determine what the customer wants,
    then transitions to the appropriate flow.

    Args:
        session: Current session.
        text: Customer text.
        prompts: Prompt dict.
        to: WhatsApp recipient.
        session_repo: Session persistence.
        customer_repo: Customer persistence.

    Returns:
        List of message payloads.
    """
    language = _resolve_language(session)

    if not text.strip():
        return await _show_main_menu(to, prompts, language)

    # Classify intent
    nlu_result = await classify_intent(text)
    intent = nlu_result.intent

    logger.debug(
        "channel_a.menu_intent",
        intent=intent,
        confidence=nlu_result.confidence,
    )

    # Check if intent maps to a known flow
    target_state = _INTENT_STATE_MAP.get(intent)

    if target_state:
        return await _start_flow_from_menu(
            session, text, target_state,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )

    # Special handling for greetings at menu
    if intent == "greet":
        name = "—"
        if session.customer_id and customer_repo:
            try:
                customer = await customer_repo.get_by_id(
                    str(session.customer_id),
                    distributor_id=str(session.distributor_id),
                )
                if customer and customer.name:
                    name = customer.name
            except Exception:
                pass
        msgs = [build_text_message(
            to,
            prompts["welcome_back"].format(name=name),
        )]
        msgs.extend(await _show_main_menu(to, prompts, language))
        return msgs

    # Special handling for goodbye
    if intent == "goodbye":
        tr = transition(
            session.current_state,
            SessionStateA.IDLE.value,
        )
        if tr.allowed:
            await session_repo.update_state(
                str(session.id),
                SessionStateA.IDLE.value,
                previous_state=session.current_state,
            )
        return [build_text_message(to, prompts["goodbye"])]

    # Intent unclear — if text looks like a medicine name, start order
    if len(text.strip()) >= 3 and intent in {"unclear", "view_order"}:
        return await _start_flow_from_menu(
            session, text,
            SessionStateA.ORDER_ITEM_COLLECTION,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )

    # Default: re-show menu
    return await _show_main_menu(to, prompts, language)


# ═══════════════════════════════════════════════════════════════════
# FLOW STARTERS
# ═══════════════════════════════════════════════════════════════════


async def _start_flow_from_menu(
    session: Session,
    text: str,
    target: SessionStateA,
    *,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None,
) -> list[dict]:
    """Transition from MAIN_MENU to the target flow's start state.

    Delegates to the appropriate flow's ``start_*`` function after
    performing the FSM transition.

    Args:
        session: Current session.
        text: Original customer text (passed to order flow).
        target: Target SessionStateA.
        session_repo: Session persistence.
        customer_repo: Customer persistence.

    Returns:
        List of message payloads from the started flow.
    """
    if target == SessionStateA.ORDER_ITEM_COLLECTION:
        return await start_order(
            session, text,
            session_repo=session_repo,
        )

    if target == SessionStateA.CATALOG_BROWSING:
        return await start_catalog(
            session, session_repo=session_repo,
        )

    if target == SessionStateA.COMPLAINT_DESCRIPTION:
        return await start_complaint(
            session, session_repo=session_repo,
        )

    if target == SessionStateA.PROFILE_VIEW:
        return await start_profile(
            session,
            session_repo=session_repo,
            customer_repo=customer_repo,
        )

    if target == SessionStateA.INQUIRY_RESPONSE:
        return await start_inquiry(
            session, session_repo=session_repo,
        )

    # Fallback — just transition
    tr = transition(session.current_state, target.value)
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            target.value,
            previous_state=session.current_state,
        )
    return []


async def _handle_menu_selection(
    session: Session,
    interactive_id: str,
    text: str,
    *,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None,
) -> list[dict]:
    """Handle an interactive menu button or list selection.

    Args:
        session: Current session.
        interactive_id: Button or list row ID.
        text: Any accompanying text.
        session_repo: Session persistence.
        customer_repo: Customer persistence.

    Returns:
        List of message payloads.
    """
    target = _INTERACTIVE_MAP.get(interactive_id)
    if not target:
        return []

    return await _start_flow_from_menu(
        session, text, target,
        session_repo=session_repo,
        customer_repo=customer_repo,
    )


# ═══════════════════════════════════════════════════════════════════
# INTERRUPT HANDLER
# ═══════════════════════════════════════════════════════════════════


async def _handle_interrupt(
    session: Session,
    interrupt: InterruptType,
    prompts: dict[str, str],
    to: str,
    *,
    session_repo: SessionRepository,
    customer_repo: CustomerRepository | None,
) -> list[dict]:
    """Handle a universal interrupt command.

    Transitions the session to the interrupt target state and returns
    the appropriate response.

    Args:
        session: Current session.
        interrupt: Detected interrupt type.
        prompts: Prompt dict.
        to: WhatsApp recipient.
        session_repo: Session persistence.
        customer_repo: Customer persistence.

    Returns:
        List of message payloads.
    """
    target_state = get_target_state_a(interrupt)
    language = _resolve_language(session)

    logger.info(
        "channel_a.interrupt",
        interrupt=interrupt.value,
        from_state=session.current_state,
        to_state=target_state,
    )

    # Perform transition
    tr = transition(session.current_state, target_state)
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            target_state,
            previous_state=session.current_state,
        )

    # Generate response based on interrupt type
    if interrupt == InterruptType.GOODBYE:
        return [build_text_message(to, prompts["goodbye"])]

    if interrupt == InterruptType.HANDOFF:
        return [build_text_message(to, prompts["handoff_active"])]

    if interrupt == InterruptType.HELP:
        return await start_inquiry(
            session, session_repo=session_repo,
        )

    # CANCEL / MENU → show main menu
    return await _show_main_menu(to, prompts, language)


# ═══════════════════════════════════════════════════════════════════
# HANDOFF STATE
# ═══════════════════════════════════════════════════════════════════


def _handle_handoff_state(
    session: Session,
    text: str,
    prompts: dict[str, str],
    to: str,
    *,
    button_id: str | None,
) -> list[dict]:
    """Handle messages while in HANDOFF state.

    All messages are logged but the bot does not respond with
    automated flows — only a "connected to human" reminder.
    The only escape is the "menu" interrupt detected earlier.

    Args:
        session: Current session.
        text: Customer text.
        prompts: Prompt dict.
        to: WhatsApp recipient.
        button_id: Interactive button ID.

    Returns:
        Reminder message.
    """
    logger.info(
        "channel_a.handoff_message",
        session_id=str(session.id),
        text_length=len(text),
    )
    return [build_text_message(to, prompts["handoff_active"])]


# ═══════════════════════════════════════════════════════════════════
# EXPIRED SESSION
# ═══════════════════════════════════════════════════════════════════


async def _handle_expired_session(
    session: Session,
    prompts: dict[str, str],
    to: str,
    *,
    session_repo: SessionRepository,
) -> list[dict]:
    """Reset an expired session and show a fresh start.

    Args:
        session: Expired session.
        prompts: Prompt dict.
        to: WhatsApp recipient.
        session_repo: Session persistence.

    Returns:
        Session expired message + main menu (if customer exists).
    """
    language = _resolve_language(session)

    logger.info(
        "channel_a.session_expired",
        session_id=str(session.id),
        previous_state=session.current_state,
    )

    # Reset to IDLE
    await session_repo.update_state(
        str(session.id),
        SessionStateA.IDLE.value,
        previous_state=session.current_state,
        state_data={},
    )

    msgs: list[dict] = [build_text_message(to, prompts["expired"])]

    if session.customer_id:
        msgs.extend(await _show_main_menu(to, prompts, language))

    return msgs


# ═══════════════════════════════════════════════════════════════════
# MAIN MENU DISPLAY
# ═══════════════════════════════════════════════════════════════════


async def _show_main_menu(
    to: str,
    prompts: dict[str, str],
    language: str,
) -> list[dict]:
    """Build the main menu as a WhatsApp list message.

    Shows 5 options: Order, Catalog, Complaint, Profile, Inquiry.
    Uses a list message for 5 options (buttons support max 3).

    Args:
        to: WhatsApp recipient.
        prompts: Prompt dict.
        language: Language string.

    Returns:
        List containing the menu message payload.
    """
    btn_text = "Select" if language == "english" else "Chunein"

    sections = [{
        "title": "Options" if language == "english" else "Options",
        "rows": [
            {
                "id": _ROW_ORDER,
                "title": prompts["btn_order"][:24],
                "description": prompts["row_order"][:72],
            },
            {
                "id": _ROW_CATALOG,
                "title": prompts["btn_catalog"][:24],
                "description": prompts["row_catalog"][:72],
            },
            {
                "id": _ROW_COMPLAINT,
                "title": prompts["btn_complaint"][:24],
                "description": prompts["row_complaint"][:72],
            },
            {
                "id": _ROW_PROFILE,
                "title": "\U0001f464 Profile"[:24],
                "description": prompts["row_profile"][:72],
            },
            {
                "id": _ROW_INQUIRY,
                "title": "\u2753 Inquiry"[:24],
                "description": prompts["row_inquiry"][:72],
            },
        ],
    }]

    return [build_list_message(
        to,
        prompts["menu"],
        button_text=btn_text,
        sections=sections,
    )]


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _resolve_language(session: Session) -> str:
    """Resolve session language to a simple string.

    Args:
        session: Current session.

    Returns:
        ``'english'`` or ``'roman_urdu'``.
    """
    lang = getattr(session, "language", None)
    if lang == Language.ENGLISH:
        return "english"
    return "roman_urdu"
