"""Channel B finite state machine — sales qualification and onboarding.

Defines all valid states, transitions, and universal interrupt handling
for the Channel B conversation flow.  Channel B handles software sales
funnel: greeting → qualification → service selection → demo booking →
proposal → payment → onboarding → conversion.

States are defined in ``app.core.constants.SessionStateB``.
"""

from __future__ import annotations

from loguru import logger

from app.core.constants import SessionStateB


# ═══════════════════════════════════════════════════════════════════
# TRANSITION TABLE
# ═══════════════════════════════════════════════════════════════════

_TRANSITIONS: dict[SessionStateB, set[SessionStateB]] = {
    SessionStateB.IDLE: {
        SessionStateB.GREETING,
        SessionStateB.HANDOFF,
    },
    SessionStateB.GREETING: {
        SessionStateB.SERVICE_SELECTION,
        SessionStateB.QUALIFICATION_NAME,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    # ── Service selection ───────────────────────────────────────
    SessionStateB.SERVICE_SELECTION: {
        SessionStateB.SERVICE_DETAIL,
        SessionStateB.QUALIFICATION_NAME,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.SERVICE_DETAIL: {
        SessionStateB.QUALIFICATION_NAME,
        SessionStateB.SERVICE_SELECTION,  # back
        SessionStateB.DEMO_BOOKING,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    # ── Qualification sub-flow ──────────────────────────────────
    SessionStateB.QUALIFICATION_NAME: {
        SessionStateB.QUALIFICATION_BUSINESS,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.QUALIFICATION_BUSINESS: {
        SessionStateB.QUALIFICATION_CITY,
        SessionStateB.QUALIFICATION_NAME,  # correction
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.QUALIFICATION_CITY: {
        SessionStateB.QUALIFICATION_RETAILER_COUNT,
        SessionStateB.QUALIFICATION_BUSINESS,  # correction
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.QUALIFICATION_RETAILER_COUNT: {
        SessionStateB.DEMO_BOOKING,
        SessionStateB.PROPOSAL_SENT,
        SessionStateB.SERVICE_SELECTION,  # loop back if unsure
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    # ── Demo and proposal ───────────────────────────────────────
    SessionStateB.DEMO_BOOKING: {
        SessionStateB.PROPOSAL_SENT,
        SessionStateB.FOLLOW_UP,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.PROPOSAL_SENT: {
        SessionStateB.PAYMENT_PENDING,
        SessionStateB.DEMO_BOOKING,  # request another demo
        SessionStateB.FOLLOW_UP,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    # ── Payment and onboarding ──────────────────────────────────
    SessionStateB.PAYMENT_PENDING: {
        SessionStateB.ONBOARDING_SETUP,
        SessionStateB.PROPOSAL_SENT,  # retry / different plan
        SessionStateB.FOLLOW_UP,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.ONBOARDING_SETUP: {
        SessionStateB.FOLLOW_UP,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    # ── Follow-up and support ───────────────────────────────────
    SessionStateB.FOLLOW_UP: {
        SessionStateB.PROPOSAL_SENT,
        SessionStateB.PAYMENT_PENDING,
        SessionStateB.DEMO_BOOKING,
        SessionStateB.SUPPORT,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    SessionStateB.SUPPORT: {
        SessionStateB.SERVICE_SELECTION,
        SessionStateB.FOLLOW_UP,
        SessionStateB.HANDOFF,
        SessionStateB.IDLE,
    },
    # ── Handoff ─────────────────────────────────────────────────
    SessionStateB.HANDOFF: {
        SessionStateB.GREETING,  # operator returns control
        SessionStateB.IDLE,
    },
}

# Universal interrupt targets — reachable from ANY state
_UNIVERSAL_INTERRUPTS: set[SessionStateB] = {
    SessionStateB.IDLE,
    SessionStateB.HANDOFF,
    SessionStateB.SUPPORT,
}


# ═══════════════════════════════════════════════════════════════════
# STATE GROUPS
# ═══════════════════════════════════════════════════════════════════

QUALIFICATION_STATES: frozenset[SessionStateB] = frozenset({
    SessionStateB.QUALIFICATION_NAME,
    SessionStateB.QUALIFICATION_BUSINESS,
    SessionStateB.QUALIFICATION_CITY,
    SessionStateB.QUALIFICATION_RETAILER_COUNT,
})

SALES_FUNNEL_STATES: frozenset[SessionStateB] = frozenset({
    SessionStateB.GREETING,
    SessionStateB.SERVICE_SELECTION,
    SessionStateB.SERVICE_DETAIL,
    SessionStateB.DEMO_BOOKING,
    SessionStateB.PROPOSAL_SENT,
    SessionStateB.PAYMENT_PENDING,
    SessionStateB.ONBOARDING_SETUP,
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
        current_state: SessionStateB,
        target_state: SessionStateB,
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

    Validates against the transition table.  Universal interrupts
    (idle, handoff, support) are always allowed from any state.

    Args:
        current: Current FSM state name.
        target: Desired target state name.

    Returns:
        TransitionResult indicating whether the transition is allowed.
    """
    try:
        current_state = SessionStateB(current)
        target_state = SessionStateB(target)
    except ValueError:
        logger.warning(
            "fsm_b.invalid_state",
            current=current,
            target=target,
        )
        return TransitionResult(
            allowed=False,
            current_state=SessionStateB.IDLE,
            target_state=SessionStateB.IDLE,
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
        "fsm_b.transition_denied",
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
            "fsm_b.transition",
            from_state=current,
            to_state=target,
        )
    else:
        logger.warning(
            "fsm_b.transition_denied",
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
        current_state = SessionStateB(current)
    except ValueError:
        return []

    allowed = _TRANSITIONS.get(current_state, set()) | _UNIVERSAL_INTERRUPTS
    return sorted(s.value for s in allowed)


def is_qualification_state(state: str) -> bool:
    """Check whether the given state is part of the qualification flow.

    Args:
        state: FSM state name.

    Returns:
        True if the state is a qualification-related state.
    """
    try:
        return SessionStateB(state) in QUALIFICATION_STATES
    except ValueError:
        return False


def is_sales_funnel_state(state: str) -> bool:
    """Check whether the given state is part of the sales funnel.

    Args:
        state: FSM state name.

    Returns:
        True if the state is a sales-funnel-related state.
    """
    try:
        return SessionStateB(state) in SALES_FUNNEL_STATES
    except ValueError:
        return False


def get_initial_state() -> SessionStateB:
    """Return the starting state for a new Channel B session.

    Returns:
        SessionStateB.GREETING.
    """
    return SessionStateB.GREETING
