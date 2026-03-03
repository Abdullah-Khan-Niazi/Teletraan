"""Universal interrupt handling — cancel / menu from any state.

Detects universal interrupt commands in customer messages and returns
the appropriate target state.  This module is channel-agnostic; both
Channel A and Channel B use it during message processing to check
whether the customer is requesting a global action before passing
the message to the current state handler.

Interrupt commands are matched case-insensitively against a set of
keywords in English, Roman Urdu, and Urdu script.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from loguru import logger


class InterruptType(StrEnum):
    """Types of universal interrupts.

    Attributes:
        CANCEL: Customer wants to cancel the current flow.
        MENU: Customer wants to go back to the main menu.
        HELP: Customer requests help.
        HANDOFF: Customer wants to talk to a human.
        GOODBYE: Customer wants to end the conversation.
    """

    CANCEL = "cancel"
    MENU = "menu"
    HELP = "help"
    HANDOFF = "handoff"
    GOODBYE = "goodbye"


# ═══════════════════════════════════════════════════════════════════
# INTERRUPT KEYWORD MAPS
# ═══════════════════════════════════════════════════════════════════

_CANCEL_KEYWORDS: frozenset[str] = frozenset({
    "cancel", "ruko", "band karo", "band", "nahi", "nahi chahiye",
    "mat", "mat karo", "stop", "cancel karo", "rehne do",
})

_MENU_KEYWORDS: frozenset[str] = frozenset({
    "menu", "main menu", "wapas", "back", "go back", "wapis",
    "start", "shuru", "home", "main", "menu dikha",
})

_HELP_KEYWORDS: frozenset[str] = frozenset({
    "help", "madad", "kaise", "how", "guide", "madad chahiye",
    "kya kar sakta hoon", "help me",
})

_HANDOFF_KEYWORDS: frozenset[str] = frozenset({
    "insaan", "human", "operator", "manager", "baat karo",
    "agent", "real person", "insaan se baat", "banda bulao",
    "talk to human", "talk to agent",
})

_GOODBYE_KEYWORDS: frozenset[str] = frozenset({
    "bye", "goodbye", "allah hafiz", "khuda hafiz", "alvida",
    "khatam",
})


# ═══════════════════════════════════════════════════════════════════
# INTERRUPT DETECTION
# ═══════════════════════════════════════════════════════════════════


def detect_interrupt(text: str) -> Optional[InterruptType]:
    """Check customer message for universal interrupt commands.

    Compares the full normalised text and individual words/phrases
    against known keyword sets.  Priority order: handoff > cancel >
    menu > help > goodbye.

    Args:
        text: Raw customer message text.

    Returns:
        InterruptType if an interrupt is detected, None otherwise.
    """
    normalised = text.strip().lower()

    if not normalised:
        return None

    # Check exact match first (fastest path for single-word commands)
    if normalised in _HANDOFF_KEYWORDS:
        logger.info("interrupt.detected", interrupt_type="handoff")
        return InterruptType.HANDOFF

    if normalised in _CANCEL_KEYWORDS:
        logger.info("interrupt.detected", interrupt_type="cancel")
        return InterruptType.CANCEL

    if normalised in _MENU_KEYWORDS:
        logger.info("interrupt.detected", interrupt_type="menu")
        return InterruptType.MENU

    if normalised in _HELP_KEYWORDS:
        logger.info("interrupt.detected", interrupt_type="help")
        return InterruptType.HELP

    if normalised in _GOODBYE_KEYWORDS:
        logger.info("interrupt.detected", interrupt_type="goodbye")
        return InterruptType.GOODBYE

    # Check substring match for multi-word keywords
    for keyword in _HANDOFF_KEYWORDS:
        if len(keyword) > 3 and keyword in normalised:
            logger.info("interrupt.detected", interrupt_type="handoff")
            return InterruptType.HANDOFF

    for keyword in _CANCEL_KEYWORDS:
        if len(keyword) > 3 and keyword in normalised:
            logger.info("interrupt.detected", interrupt_type="cancel")
            return InterruptType.CANCEL

    for keyword in _MENU_KEYWORDS:
        if len(keyword) > 3 and keyword in normalised:
            logger.info("interrupt.detected", interrupt_type="menu")
            return InterruptType.MENU

    return None


def get_target_state_a(interrupt: InterruptType) -> str:
    """Map an interrupt to the Channel A target state.

    Args:
        interrupt: Detected interrupt type.

    Returns:
        Target SessionStateA value as string.
    """
    from app.core.constants import SessionStateA

    mapping = {
        InterruptType.CANCEL: SessionStateA.MAIN_MENU,
        InterruptType.MENU: SessionStateA.MAIN_MENU,
        InterruptType.HELP: SessionStateA.INQUIRY_RESPONSE,
        InterruptType.HANDOFF: SessionStateA.HANDOFF,
        InterruptType.GOODBYE: SessionStateA.IDLE,
    }
    return mapping[interrupt].value


def get_target_state_b(interrupt: InterruptType) -> str:
    """Map an interrupt to the Channel B target state.

    Args:
        interrupt: Detected interrupt type.

    Returns:
        Target SessionStateB value as string.
    """
    from app.core.constants import SessionStateB

    mapping = {
        InterruptType.CANCEL: SessionStateB.IDLE,
        InterruptType.MENU: SessionStateB.SERVICE_SELECTION,
        InterruptType.HELP: SessionStateB.SUPPORT,
        InterruptType.HANDOFF: SessionStateB.HANDOFF,
        InterruptType.GOODBYE: SessionStateB.IDLE,
    }
    return mapping[interrupt].value


def get_interrupt_response(
    interrupt: InterruptType,
    language: str = "roman_urdu",
) -> str:
    """Get the bot response message for an interrupt.

    Args:
        interrupt: Detected interrupt type.
        language: Language code ('roman_urdu', 'english', 'urdu').

    Returns:
        Response text string.
    """
    if language == "english":
        responses = {
            InterruptType.CANCEL: "Order cancelled. Back to main menu.",
            InterruptType.MENU: "Going back to the main menu.",
            InterruptType.HELP: "How can I help you? Tell me what you need.",
            InterruptType.HANDOFF: (
                "Connecting you with our team. "
                "Someone will respond shortly. \U0001f64f"
            ),
            InterruptType.GOODBYE: (
                "Thank you! Whenever you need anything, just send a message. "
                "Allah Hafiz! \U0001f44b"
            ),
        }
    else:
        responses = {
            InterruptType.CANCEL: "Order cancel ho gaya. Main menu par wapas ja rahe hain.",
            InterruptType.MENU: "Main menu par wapas ja rahe hain.",
            InterruptType.HELP: "Bataiye, kya madad chahiye? Main aapki khidmat mein hazir hoon.",
            InterruptType.HANDOFF: (
                "Hamari team se connect kar raha hoon. "
                "Koi jald jawab dega. \U0001f64f"
            ),
            InterruptType.GOODBYE: (
                "Shukriya! Jab bhi zaroorat ho, message bhej dein. "
                "Allah Hafiz! \U0001f44b"
            ),
        }

    return responses.get(interrupt, "")
