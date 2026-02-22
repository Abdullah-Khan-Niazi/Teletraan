"""Channel A — customer onboarding (registration) flow.

Handles the four-step onboarding sequence:

1. ``ONBOARDING_NAME``    — collect customer name
2. ``ONBOARDING_SHOP``    — collect shop name
3. ``ONBOARDING_ADDRESS`` — collect address (and parse city)
4. ``ONBOARDING_CONFIRM`` — show summary, buttons [Confirm / Edit]

Voice messages are supported at every step — the caller is
responsible for transcribing audio BEFORE dispatching here.
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import (
    MAX_ADDRESS_LENGTH,
    MAX_NAME_LENGTH,
    Language,
    SessionStateA,
)
from app.db.models.customer import CustomerCreate
from app.db.models.session import Session
from app.db.repositories.customer_repo import CustomerRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import build_button_message, build_text_message


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

_CONFIRM_ID = "onboarding_confirm_yes"
_EDIT_ID = "onboarding_confirm_edit"

# Known cities for auto-extraction from address
_KNOWN_CITIES: frozenset[str] = frozenset({
    "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
    "multan", "peshawar", "quetta", "sialkot", "gujranwala",
    "hyderabad", "bahawalpur", "sargodha", "sukkur", "larkana",
    "gujrat", "mardan", "abbottabad", "sahiwal", "okara",
    "wah cantt", "dera ghazi khan", "mingora", "chiniot",
    "kamalia", "muzaffargarh", "jhelum", "sadiqabad",
    "jacobabad", "sheikhupura", "mirpur", "kohat",
    "jhang", "nawabshah", "kasur", "rahim yar khan",
    "mansehra", "swabi", "chakwal", "khairpur",
})


# ═══════════════════════════════════════════════════════════════════
# PROMPTS (bilingual — Roman Urdu / English)
# ═══════════════════════════════════════════════════════════════════


def _get_prompts(language: str) -> dict[str, str]:
    """Get onboarding prompt strings for the given language.

    Args:
        language: ``'english'`` or ``'roman_urdu'`` (default).

    Returns:
        Dict of prompt keys → text strings.
    """
    if language == "english":
        return {
            "welcome": (
                "Assalam o Alaikum! \U0001f44b Welcome to {distributor_name}.\n\n"
                "It looks like this is your first time here. "
                "Let's set up your account quickly.\n\n"
                "What is your name?"
            ),
            "ask_shop": "Thanks, {name}! \U0001f60a What is your shop name?",
            "ask_address": (
                "Got it! Now please share your shop address.\n"
                "(Street, Area, City)"
            ),
            "confirm_summary": (
                "\u2705 Here are your details:\n\n"
                "\U0001f464 Name: {name}\n"
                "\U0001f3ea Shop: {shop_name}\n"
                "\U0001f4cd Address: {address}\n"
                "\U0001f4f1 WhatsApp: {phone_display}\n\n"
                "Is this correct?"
            ),
            "success": (
                "Excellent! Your account is set up! \U0001f389\n\n"
                "You can now place orders, browse the catalog, "
                "or submit complaints.\n\n"
                "What would you like to do?"
            ),
            "edit_restart": "No problem! Let's start over.\n\nWhat is your name?",
            "invalid_name": (
                "Please enter a valid name (2-255 characters, "
                "letters and spaces only)."
            ),
            "invalid_shop": "Please enter a valid shop name (2-255 characters).",
            "invalid_address": (
                "Please enter a valid address (5-500 characters).\n"
                "Include street, area, and city."
            ),
            "btn_confirm": "\u2705 Confirm",
            "btn_edit": "\u270f\ufe0f Edit",
        }
    else:
        return {
            "welcome": (
                "Assalam o Alaikum! \U0001f44b {distributor_name} mein "
                "khush aamdeed.\n\n"
                "Lagta hai aap pehli baar aa rahe hain. "
                "Chalein, jaldi se account bana lete hain.\n\n"
                "Aapka naam kya hai?"
            ),
            "ask_shop": "Shukriya, {name} bhai! \U0001f60a Aapki dukaan ka naam?",
            "ask_address": (
                "Waah! Ab apni dukaan ka pata bataiye.\n"
                "(Gali, Mohalla, Sheher)"
            ),
            "confirm_summary": (
                "\u2705 Aapki details:\n\n"
                "\U0001f464 Naam: {name}\n"
                "\U0001f3ea Dukaan: {shop_name}\n"
                "\U0001f4cd Pata: {address}\n"
                "\U0001f4f1 WhatsApp: {phone_display}\n\n"
                "Kya ye details theek hain?"
            ),
            "success": (
                "Zabardast! Aapka account ban gaya! \U0001f389\n\n"
                "Ab aap order de sakte hain, catalog dekh sakte hain, "
                "ya complaint kar sakte hain.\n\n"
                "Kya karna chahein ge?"
            ),
            "edit_restart": (
                "Koi baat nahi! Dubara shuru karte hain.\n\n"
                "Aapka naam kya hai?"
            ),
            "invalid_name": (
                "Meherbani se apna naam likhein (2-255 characters, "
                "sirf huroof aur spaces)."
            ),
            "invalid_shop": "Meherbani se dukaan ka naam likhein (2-255 characters).",
            "invalid_address": (
                "Meherbani se dukaan ka pata likhein (5-500 characters).\n"
                "Gali, Mohalla, aur Sheher shamil karein."
            ),
            "btn_confirm": "\u2705 Haan",
            "btn_edit": "\u270f\ufe0f Edit",
        }


# ═══════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════

# Allow letters (any script), spaces, dots, hyphens, apostrophes
_NAME_REGEX = re.compile(r"^[\w\s.\-']{2,255}$", re.UNICODE)
_SHOP_REGEX = re.compile(r"^[\w\s.\-'&#/()]{2,255}$", re.UNICODE)


def _validate_name(name: str) -> str | None:
    """Validate and clean a customer name.

    Args:
        name: Raw name input.

    Returns:
        Cleaned name or None if invalid.
    """
    name = name.strip()[:MAX_NAME_LENGTH]
    if len(name) < 2 or not _NAME_REGEX.match(name):
        return None
    # Title-case
    return name.title()


def _validate_shop_name(shop: str) -> str | None:
    """Validate and clean a shop name.

    Args:
        shop: Raw shop name input.

    Returns:
        Cleaned shop name or None if invalid.
    """
    shop = shop.strip()[:MAX_NAME_LENGTH]
    if len(shop) < 2 or not _SHOP_REGEX.match(shop):
        return None
    return shop.strip()


def _validate_address(address: str) -> str | None:
    """Validate an address string.

    Args:
        address: Raw address input.

    Returns:
        Cleaned address or None if invalid.
    """
    address = address.strip()[:MAX_ADDRESS_LENGTH]
    if len(address) < 5:
        return None
    return address.strip()


def _extract_city(address: str) -> str | None:
    """Try to extract city name from an address string.

    Checks the last comma-separated segment and known city names.

    Args:
        address: Address text.

    Returns:
        City name (title-cased) or None.
    """
    if not address:
        return None

    lower = address.lower()

    # Try last comma segment
    segments = [s.strip() for s in address.split(",")]
    if segments:
        last = segments[-1].lower().strip()
        if last in _KNOWN_CITIES:
            return segments[-1].strip().title()

    # Scan all words for known city
    for city in _KNOWN_CITIES:
        if city in lower:
            return city.title()

    return None


# ═══════════════════════════════════════════════════════════════════
# RESPONSE BUILDERS
# ═══════════════════════════════════════════════════════════════════


def _phone_display(whatsapp_number: str) -> str:
    """Mask phone number for display — show last 4 digits.

    Args:
        whatsapp_number: E.164 format number.

    Returns:
        Masked string like ``****1234``.
    """
    return f"****{whatsapp_number[-4:]}"


# ═══════════════════════════════════════════════════════════════════
# STEP HANDLERS
# ═══════════════════════════════════════════════════════════════════


async def handle_onboarding_step(
    session: Session,
    text: str,
    *,
    distributor_name: str = "TELETRAAN",
    session_repo: SessionRepository | None = None,
    customer_repo: CustomerRepository | None = None,
) -> list[dict]:
    """Route an onboarding message to the appropriate step handler.

    This is the main entry point for the onboarding flow. It inspects
    ``session.current_state`` and delegates to the correct step.

    Args:
        session: Current session object.
        text: Transcribed user text (voice already converted).
        distributor_name: Name shown in welcome message.
        session_repo: SessionRepository instance (default created).
        customer_repo: CustomerRepository instance (default created).

    Returns:
        List of WhatsApp message payloads to send.
    """
    s_repo = session_repo or SessionRepository()
    c_repo = customer_repo or CustomerRepository()
    lang = getattr(session, "language", Language.ROMAN_URDU)
    language = "english" if lang == Language.ENGLISH else "roman_urdu"
    state = session.current_state
    prompts = _get_prompts(language)
    to = session.whatsapp_number

    logger.info(
        "onboarding.step",
        state=state,
        number_suffix=to[-4:],
    )

    if state == SessionStateA.ONBOARDING_NAME.value:
        return await _handle_name_step(
            session, text, to, prompts, s_repo, language,
        )

    if state == SessionStateA.ONBOARDING_SHOP.value:
        return await _handle_shop_step(
            session, text, to, prompts, s_repo, language,
        )

    if state == SessionStateA.ONBOARDING_ADDRESS.value:
        return await _handle_address_step(
            session, text, to, prompts, s_repo, language,
        )

    if state == SessionStateA.ONBOARDING_CONFIRM.value:
        return await _handle_confirm_step(
            session, text, to, prompts, s_repo, c_repo, language,
        )

    # Should not reach here, but handle gracefully
    logger.warning("onboarding.unexpected_state", state=state)
    return [build_text_message(to, prompts["welcome"].format(
        distributor_name=distributor_name,
    ))]


async def start_onboarding(
    session: Session,
    *,
    distributor_name: str = "TELETRAAN",
    session_repo: SessionRepository | None = None,
) -> list[dict]:
    """Begin the onboarding flow — send welcome and transition to name step.

    Called when a new (unregistered) customer sends their first message.

    Args:
        session: Current session (in IDLE state).
        distributor_name: Name shown in welcome message.
        session_repo: SessionRepository instance.

    Returns:
        List of WhatsApp message payloads to send.
    """
    s_repo = session_repo or SessionRepository()
    lang = getattr(session, "language", Language.ROMAN_URDU)
    language = "english" if lang == Language.ENGLISH else "roman_urdu"
    prompts = _get_prompts(language)
    to = session.whatsapp_number

    # Transition to name collection step
    t_result = transition(
        session.current_state, SessionStateA.ONBOARDING_NAME.value
    )
    if t_result.allowed:
        await s_repo.update_state(
            str(session.id),
            SessionStateA.ONBOARDING_NAME.value,
            previous_state=session.current_state,
            state_data={},
        )

    welcome = prompts["welcome"].format(distributor_name=distributor_name)
    logger.info(
        "onboarding.started",
        number_suffix=to[-4:],
    )
    return [build_text_message(to, welcome)]


# ═══════════════════════════════════════════════════════════════════
# INDIVIDUAL STEP HANDLERS
# ═══════════════════════════════════════════════════════════════════


async def _handle_name_step(
    session: Session,
    text: str,
    to: str,
    prompts: dict[str, str],
    s_repo: SessionRepository,
    language: str,
) -> list[dict]:
    """Handle name collection step.

    Args:
        session: Current session.
        text: User's name input.
        to: WhatsApp number.
        prompts: Language-appropriate prompt dict.
        s_repo: SessionRepository.
        language: Language code.

    Returns:
        List of message payloads.
    """
    name = _validate_name(text)
    if not name:
        logger.debug("onboarding.invalid_name", input=text[:20])
        return [build_text_message(to, prompts["invalid_name"])]

    # Save name in state_data and transition to shop step
    state_data = dict(session.state_data)
    state_data["name"] = name

    t_result = transition(
        SessionStateA.ONBOARDING_NAME.value,
        SessionStateA.ONBOARDING_SHOP.value,
    )
    if t_result.allowed:
        await s_repo.update_state(
            str(session.id),
            SessionStateA.ONBOARDING_SHOP.value,
            previous_state=SessionStateA.ONBOARDING_NAME.value,
            state_data=state_data,
        )

    msg = prompts["ask_shop"].format(name=name)
    logger.info("onboarding.name_collected", name=name[:20])
    return [build_text_message(to, msg)]


async def _handle_shop_step(
    session: Session,
    text: str,
    to: str,
    prompts: dict[str, str],
    s_repo: SessionRepository,
    language: str,
) -> list[dict]:
    """Handle shop name collection step.

    Args:
        session: Current session.
        text: User's shop name input.
        to: WhatsApp number.
        prompts: Language-appropriate prompt dict.
        s_repo: SessionRepository.
        language: Language code.

    Returns:
        List of message payloads.
    """
    shop_name = _validate_shop_name(text)
    if not shop_name:
        logger.debug("onboarding.invalid_shop", input=text[:20])
        return [build_text_message(to, prompts["invalid_shop"])]

    state_data = dict(session.state_data)
    state_data["shop_name"] = shop_name

    t_result = transition(
        SessionStateA.ONBOARDING_SHOP.value,
        SessionStateA.ONBOARDING_ADDRESS.value,
    )
    if t_result.allowed:
        await s_repo.update_state(
            str(session.id),
            SessionStateA.ONBOARDING_ADDRESS.value,
            previous_state=SessionStateA.ONBOARDING_SHOP.value,
            state_data=state_data,
        )

    logger.info("onboarding.shop_collected", shop_name=shop_name[:20])
    return [build_text_message(to, prompts["ask_address"])]


async def _handle_address_step(
    session: Session,
    text: str,
    to: str,
    prompts: dict[str, str],
    s_repo: SessionRepository,
    language: str,
) -> list[dict]:
    """Handle address collection step.

    Attempts to extract city name from the address automatically.

    Args:
        session: Current session.
        text: User's address input.
        to: WhatsApp number.
        prompts: Language-appropriate prompt dict.
        s_repo: SessionRepository.
        language: Language code.

    Returns:
        List of message payloads.
    """
    address = _validate_address(text)
    if not address:
        logger.debug("onboarding.invalid_address", input=text[:20])
        return [build_text_message(to, prompts["invalid_address"])]

    city = _extract_city(address)

    state_data = dict(session.state_data)
    state_data["address"] = address
    if city:
        state_data["city"] = city

    t_result = transition(
        SessionStateA.ONBOARDING_ADDRESS.value,
        SessionStateA.ONBOARDING_CONFIRM.value,
    )
    if t_result.allowed:
        await s_repo.update_state(
            str(session.id),
            SessionStateA.ONBOARDING_CONFIRM.value,
            previous_state=SessionStateA.ONBOARDING_ADDRESS.value,
            state_data=state_data,
        )

    # Build confirmation summary
    name = state_data.get("name", "")
    shop_name = state_data.get("shop_name", "")
    phone_disp = _phone_display(session.whatsapp_number)

    summary = prompts["confirm_summary"].format(
        name=name,
        shop_name=shop_name,
        address=address,
        phone_display=phone_disp,
    )

    buttons = [
        (_CONFIRM_ID, prompts["btn_confirm"]),
        (_EDIT_ID, prompts["btn_edit"]),
    ]

    logger.info(
        "onboarding.address_collected",
        city=city or "unknown",
    )
    return [build_button_message(to, summary, buttons)]


async def _handle_confirm_step(
    session: Session,
    text: str,
    to: str,
    prompts: dict[str, str],
    s_repo: SessionRepository,
    c_repo: CustomerRepository,
    language: str,
) -> list[dict]:
    """Handle confirmation step.

    If user presses Confirm → create customer in DB, transition
    to MAIN_MENU.  If Edit → restart from ONBOARDING_NAME.

    Also handles text-based confirmation for non-button responses.

    Args:
        session: Current session.
        text: Button ID or text response.
        to: WhatsApp number.
        prompts: Language-appropriate prompt dict.
        s_repo: SessionRepository.
        c_repo: CustomerRepository.
        language: Language code.

    Returns:
        List of message payloads.
    """
    normalised = text.strip().lower()

    # Check for edit/restart
    is_edit = (
        normalised == _EDIT_ID
        or normalised in {"edit", "nahi", "nah", "no", "galat", "dobara"}
    )
    if is_edit:
        return await _restart_onboarding(session, to, prompts, s_repo)

    # Check for confirm
    is_confirm = (
        normalised == _CONFIRM_ID
        or normalised in {"haan", "yes", "ha", "ji", "theek", "correct", "sahi"}
    )
    if not is_confirm:
        # Ambiguous — re-show summary with buttons
        state_data = session.state_data
        summary = prompts["confirm_summary"].format(
            name=state_data.get("name", ""),
            shop_name=state_data.get("shop_name", ""),
            address=state_data.get("address", ""),
            phone_display=_phone_display(session.whatsapp_number),
        )
        buttons = [
            (_CONFIRM_ID, prompts["btn_confirm"]),
            (_EDIT_ID, prompts["btn_edit"]),
        ]
        return [build_button_message(to, summary, buttons)]

    # Create customer
    state_data = session.state_data
    name = state_data.get("name", "Unknown")
    shop_name = state_data.get("shop_name", "Unknown Shop")
    address = state_data.get("address")
    city = state_data.get("city")

    lang_pref = Language.ENGLISH if language == "english" else Language.ROMAN_URDU

    customer_data = CustomerCreate(
        distributor_id=session.distributor_id,
        whatsapp_number=session.whatsapp_number,
        name=name,
        shop_name=shop_name,
        address=address,
        city=city,
        language_preference=lang_pref,
        is_verified=True,
    )

    customer = await c_repo.create(customer_data)

    # Link customer to session and transition to main menu
    t_result = transition(
        SessionStateA.ONBOARDING_CONFIRM.value,
        SessionStateA.MAIN_MENU.value,
    )
    if t_result.allowed:
        await s_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=SessionStateA.ONBOARDING_CONFIRM.value,
            state_data={},
        )

    # Update session's customer_id
    from app.db.models.session import SessionUpdate

    await s_repo.update(
        str(session.id),
        SessionUpdate(customer_id=customer.id),
    )

    logger.info(
        "onboarding.complete",
        customer_id=str(customer.id),
        number_suffix=to[-4:],
    )

    return [build_text_message(to, prompts["success"])]


async def _restart_onboarding(
    session: Session,
    to: str,
    prompts: dict[str, str],
    s_repo: SessionRepository,
) -> list[dict]:
    """Restart the onboarding flow from the name step.

    Args:
        session: Current session.
        to: WhatsApp number.
        prompts: Language-appropriate prompt dict.
        s_repo: SessionRepository.

    Returns:
        List of message payloads.
    """
    t_result = transition(
        SessionStateA.ONBOARDING_CONFIRM.value,
        SessionStateA.ONBOARDING_NAME.value,
    )
    if t_result.allowed:
        await s_repo.update_state(
            str(session.id),
            SessionStateA.ONBOARDING_NAME.value,
            previous_state=SessionStateA.ONBOARDING_CONFIRM.value,
            state_data={},
        )

    logger.info("onboarding.restarted", number_suffix=to[-4:])
    return [build_text_message(to, prompts["edit_restart"])]
