"""Channel A finite state machine — order management for retailers.

Defines all valid states, transitions, and universal interrupt handling
for the Channel A conversation flow.  The FSM is stateless itself; it
reads the current state from the session and returns the target state
after validating the transition.

States are defined in ``app.core.constants.SessionStateA``.
"""

from __future__ import annotations

from loguru import logger

from app.core.constants import SessionStateA


# ═══════════════════════════════════════════════════════════════════
# TRANSITION TABLE
# ═══════════════════════════════════════════════════════════════════

# Maps each state to the set of states it may legally transition to.
# Every entry is sourced from the UX conversation flow spec.

_TRANSITIONS: dict[SessionStateA, set[SessionStateA]] = {
    SessionStateA.IDLE: {
        SessionStateA.ONBOARDING_NAME,
        SessionStateA.MAIN_MENU,
        SessionStateA.ORDER_ITEM_COLLECTION,  # returning customer shortcut
        SessionStateA.HANDOFF,
    },
    # ── Onboarding sub-flow ─────────────────────────────────────
    SessionStateA.ONBOARDING_NAME: {
        SessionStateA.ONBOARDING_SHOP,
        SessionStateA.HANDOFF,
    },
    SessionStateA.ONBOARDING_SHOP: {
        SessionStateA.ONBOARDING_ADDRESS,
        SessionStateA.ONBOARDING_NAME,  # correction loop
        SessionStateA.HANDOFF,
    },
    SessionStateA.ONBOARDING_ADDRESS: {
        SessionStateA.ONBOARDING_CONFIRM,
        SessionStateA.ONBOARDING_SHOP,  # correction loop
        SessionStateA.HANDOFF,
    },
    SessionStateA.ONBOARDING_CONFIRM: {
        SessionStateA.MAIN_MENU,
        SessionStateA.ONBOARDING_NAME,  # restart onboarding
        SessionStateA.HANDOFF,
    },
    # ── Main menu ───────────────────────────────────────────────
    SessionStateA.MAIN_MENU: {
        SessionStateA.ORDER_ITEM_COLLECTION,
        SessionStateA.CATALOG_BROWSING,
        SessionStateA.COMPLAINT_DESCRIPTION,
        SessionStateA.PROFILE_VIEW,
        SessionStateA.INQUIRY_RESPONSE,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,  # timeout / goodbye
    },
    # ── Order flow ──────────────────────────────────────────────
    SessionStateA.ORDER_ITEM_COLLECTION: {
        SessionStateA.ORDER_ITEM_CONFIRMATION,
        SessionStateA.ORDER_AMBIGUITY_RESOLUTION,
        SessionStateA.ORDER_BILL_PREVIEW,
        SessionStateA.MAIN_MENU,  # cancel / menu interrupt
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.ORDER_ITEM_CONFIRMATION: {
        SessionStateA.ORDER_ITEM_COLLECTION,  # add more
        SessionStateA.ORDER_BILL_PREVIEW,
        SessionStateA.ORDER_AMBIGUITY_RESOLUTION,
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.ORDER_AMBIGUITY_RESOLUTION: {
        SessionStateA.ORDER_ITEM_COLLECTION,
        SessionStateA.ORDER_ITEM_CONFIRMATION,
        SessionStateA.ORDER_BILL_PREVIEW,
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.ORDER_BILL_PREVIEW: {
        SessionStateA.ORDER_DISCOUNT_REQUEST,
        SessionStateA.ORDER_FINAL_CONFIRMATION,
        SessionStateA.ORDER_ITEM_COLLECTION,  # edit loop
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.ORDER_DISCOUNT_REQUEST: {
        SessionStateA.ORDER_BILL_PREVIEW,
        SessionStateA.ORDER_FINAL_CONFIRMATION,
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.ORDER_FINAL_CONFIRMATION: {
        SessionStateA.MAIN_MENU,  # order complete → back to menu
        SessionStateA.ORDER_ITEM_COLLECTION,  # customer wants to edit
        SessionStateA.IDLE,  # done
        SessionStateA.HANDOFF,
    },
    # ── Catalog browsing ────────────────────────────────────────
    SessionStateA.CATALOG_BROWSING: {
        SessionStateA.ORDER_ITEM_COLLECTION,  # found something to order
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    # ── Complaint flow ──────────────────────────────────────────
    SessionStateA.COMPLAINT_DESCRIPTION: {
        SessionStateA.COMPLAINT_CATEGORY,
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.COMPLAINT_CATEGORY: {
        SessionStateA.COMPLAINT_CONFIRM,
        SessionStateA.COMPLAINT_DESCRIPTION,  # correction
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.COMPLAINT_CONFIRM: {
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    # ── Profile flow ────────────────────────────────────────────
    SessionStateA.PROFILE_VIEW: {
        SessionStateA.PROFILE_EDIT,
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    SessionStateA.PROFILE_EDIT: {
        SessionStateA.PROFILE_VIEW,
        SessionStateA.MAIN_MENU,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    # ── Inquiry ─────────────────────────────────────────────────
    SessionStateA.INQUIRY_RESPONSE: {
        SessionStateA.MAIN_MENU,
        SessionStateA.ORDER_ITEM_COLLECTION,
        SessionStateA.HANDOFF,
        SessionStateA.IDLE,
    },
    # ── Handoff ─────────────────────────────────────────────────
    SessionStateA.HANDOFF: {
        SessionStateA.MAIN_MENU,  # operator returns control
        SessionStateA.IDLE,
    },
}

# Universal interrupt targets — reachable from ANY state
_UNIVERSAL_INTERRUPTS: set[SessionStateA] = {
    SessionStateA.MAIN_MENU,
    SessionStateA.IDLE,
    SessionStateA.HANDOFF,
}


# ═══════════════════════════════════════════════════════════════════
# STATE GROUPS (for categorical checks)
# ═══════════════════════════════════════════════════════════════════

ONBOARDING_STATES: frozenset[SessionStateA] = frozenset({
    SessionStateA.ONBOARDING_NAME,
    SessionStateA.ONBOARDING_SHOP,
    SessionStateA.ONBOARDING_ADDRESS,
    SessionStateA.ONBOARDING_CONFIRM,
})

ORDER_STATES: frozenset[SessionStateA] = frozenset({
    SessionStateA.ORDER_ITEM_COLLECTION,
    SessionStateA.ORDER_ITEM_CONFIRMATION,
    SessionStateA.ORDER_AMBIGUITY_RESOLUTION,
    SessionStateA.ORDER_BILL_PREVIEW,
    SessionStateA.ORDER_DISCOUNT_REQUEST,
    SessionStateA.ORDER_FINAL_CONFIRMATION,
})

COMPLAINT_STATES: frozenset[SessionStateA] = frozenset({
    SessionStateA.COMPLAINT_DESCRIPTION,
    SessionStateA.COMPLAINT_CATEGORY,
    SessionStateA.COMPLAINT_CONFIRM,
})

PROFILE_STATES: frozenset[SessionStateA] = frozenset({
    SessionStateA.PROFILE_VIEW,
    SessionStateA.PROFILE_EDIT,
})


# ═══════════════════════════════════════════════════════════════════
# TRANSITION VALIDATION
# ═══════════════════════════════════════════════════════════════════


class TransitionResult:
    """Result of a state transition attempt.

    Attributes:
        allowed: Whether the transition is valid.
        current_state: The state transitioned from.
        target_state: The requested target state.
        reason: Human-readable reason if disallowed.
    """

    __slots__ = ("allowed", "current_state", "target_state", "reason")

    def __init__(
        self,
        allowed: bool,
        current_state: SessionStateA,
        target_state: SessionStateA,
        reason: str = "",
    ) -> None:
        self.allowed = allowed
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason


def can_transition(
    current: str,
    target: str,
) -> TransitionResult:
    """Check whether a state transition is valid.

    Validates against the transition table. Universal interrupts
    (menu, idle, handoff) are always allowed from any state.

    Args:
        current: Current FSM state name.
        target: Desired target state name.

    Returns:
        TransitionResult indicating whether the transition is allowed.
    """
    try:
        current_state = SessionStateA(current)
        target_state = SessionStateA(target)
    except ValueError:
        logger.warning(
            "fsm_a.invalid_state",
            current=current,
            target=target,
        )
        return TransitionResult(
            allowed=False,
            current_state=SessionStateA.IDLE,
            target_state=SessionStateA.IDLE,
            reason=f"Invalid state name: current='{current}', target='{target}'",
        )

    # Universal interrupts are always allowed
    if target_state in _UNIVERSAL_INTERRUPTS:
        return TransitionResult(
            allowed=True,
            current_state=current_state,
            target_state=target_state,
        )

    # Check transition table
    allowed_targets = _TRANSITIONS.get(current_state, set())
    if target_state in allowed_targets:
        return TransitionResult(
            allowed=True,
            current_state=current_state,
            target_state=target_state,
        )

    logger.warning(
        "fsm_a.transition_denied",
        current=current,
        target=target,
    )
    return TransitionResult(
        allowed=False,
        current_state=current_state,
        target_state=target_state,
        reason=(
            f"Transition from '{current}' to '{target}' is not allowed. "
            f"Allowed targets: {sorted(s.value for s in allowed_targets)}"
        ),
    )


def transition(
    current: str,
    target: str,
) -> TransitionResult:
    """Validate and execute a state transition.

    Convenience wrapper: validates the transition and logs the result.

    Args:
        current: Current FSM state name.
        target: Desired target state name.

    Returns:
        TransitionResult — check ``.allowed`` before persisting.
    """
    result = can_transition(current, target)

    if result.allowed:
        logger.info(
            "fsm_a.transition",
            from_state=current,
            to_state=target,
        )
    else:
        logger.warning(
            "fsm_a.transition_denied",
            from_state=current,
            to_state=target,
            reason=result.reason,
        )

    return result


def get_allowed_transitions(current: str) -> list[str]:
    """Return all states reachable from the given state.

    Includes universal interrupts.

    Args:
        current: Current FSM state name.

    Returns:
        Sorted list of allowed target state names.
    """
    try:
        current_state = SessionStateA(current)
    except ValueError:
        return []

    allowed = _TRANSITIONS.get(current_state, set()) | _UNIVERSAL_INTERRUPTS
    return sorted(s.value for s in allowed)


def is_order_state(state: str) -> bool:
    """Check whether the given state is part of the order flow.

    Args:
        state: FSM state name.

    Returns:
        True if the state is an order-related state.
    """
    try:
        return SessionStateA(state) in ORDER_STATES
    except ValueError:
        return False


def is_onboarding_state(state: str) -> bool:
    """Check whether the given state is part of the onboarding flow.

    Args:
        state: FSM state name.

    Returns:
        True if the state is an onboarding-related state.
    """
    try:
        return SessionStateA(state) in ONBOARDING_STATES
    except ValueError:
        return False


def get_initial_state(is_new_customer: bool) -> SessionStateA:
    """Determine the starting state for a new session.

    New customers go to onboarding; returning customers go to main menu.

    Args:
        is_new_customer: True if the customer has no profile yet.

    Returns:
        Starting SessionStateA.
    """
    if is_new_customer:
        return SessionStateA.ONBOARDING_NAME
    return SessionStateA.MAIN_MENU
