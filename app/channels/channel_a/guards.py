"""Channel A — business hours, credit limit, and human handoff utilities.

Provides pre-processing guards that the main handler (or orchestrator)
calls before dispatching to a flow:

* **Business hours enforcement** — if ordering is outside configured
  hours and ``allow_orders_outside_hours`` is False, returns an
  out-of-hours message.
* **Credit limit check** — blocks order placement when the customer's
  outstanding balance + prospective order total would exceed their
  credit limit (only when credit orders are enabled).
* **Human handoff** — transition to ``HANDOFF`` state, notify the
  distributor, and silence the bot until released.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Optional

import pytz
from loguru import logger

from app.channels.channel_a.state_machine import transition
from app.core.constants import Language, SessionStateA
from app.db.models.audit import BotConfiguration
from app.db.models.customer import Customer
from app.db.models.session import Session
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import build_text_message


# ═══════════════════════════════════════════════════════════════════
# BUSINESS HOURS
# ═══════════════════════════════════════════════════════════════════


def is_within_business_hours(
    config: BotConfiguration | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Check whether the current time is within configured business hours.

    If no config is provided, always returns True (fail-open).

    Args:
        config: Bot configuration for this distributor.
        now: Override for current time (testing).

    Returns:
        True if within hours or no config set.
    """
    if config is None:
        return True

    tz_name = config.timezone or "Asia/Karachi"
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        logger.warning("business_hours.unknown_timezone", tz=tz_name)
        tz = pytz.timezone("Asia/Karachi")

    if now is None:
        now = datetime.now(timezone.utc)
    local_now = now.astimezone(tz)
    current_time = local_now.time()

    start = config.business_hours_start
    end = config.business_hours_end

    if start <= end:
        return start <= current_time <= end
    # Overnight wrap (e.g. 22:00 → 06:00)
    return current_time >= start or current_time <= end


def check_business_hours(
    config: BotConfiguration | None,
    *,
    language: str = "roman_urdu",
    to: str,
) -> list[dict] | None:
    """Return an out-of-hours message if ordering is blocked.

    If ``allow_orders_outside_hours`` is True in config, returns None
    regardless of time.

    Args:
        config: Bot configuration.
        language: Customer language.
        to: WhatsApp recipient.

    Returns:
        Message list if blocked, None if allowed.
    """
    if config is None:
        return None

    if config.allow_orders_outside_hours:
        return None

    if is_within_business_hours(config):
        return None

    # Outside hours and ordering not allowed
    custom_msg = config.out_of_hours_message
    if custom_msg:
        return [build_text_message(to, custom_msg)]

    start_str = config.business_hours_start.strftime("%I:%M %p")
    end_str = config.business_hours_end.strftime("%I:%M %p")

    if language == "english":
        msg = (
            f"\u23f0 We're currently outside business hours.\n"
            f"Our hours are {start_str} — {end_str}.\n"
            f"Please try again during these hours."
        )
    else:
        msg = (
            f"\u23f0 Abhi business hours ke bahar hain.\n"
            f"Humara waqt {start_str} — {end_str} hai.\n"
            f"In auqat mein dobara try karein."
        )

    logger.info("business_hours.outside_hours", to_suffix=to[-4:])
    return [build_text_message(to, msg)]


# ═══════════════════════════════════════════════════════════════════
# CREDIT LIMIT CHECK
# ═══════════════════════════════════════════════════════════════════


def check_credit_limit(
    customer: Customer | None,
    order_total_paisas: int,
    *,
    config: BotConfiguration | None = None,
    language: str = "roman_urdu",
    to: str,
) -> list[dict] | None:
    """Check whether the order would exceed the customer's credit limit.

    Only enforced when:
    1. ``config.credit_orders_enabled`` is True, AND
    2. ``customer.credit_limit_paisas`` > 0

    The check is: outstanding_balance + order_total > credit_limit

    Args:
        customer: Customer model (has credit_limit_paisas and
            outstanding_balance_paisas).
        order_total_paisas: Prospective order total in paisas.
        config: Bot configuration (checks credit_orders_enabled flag).
        language: Customer language.
        to: WhatsApp recipient.

    Returns:
        Warning message list if limit exceeded, None if OK.
    """
    if customer is None:
        return None

    # Credit system must be enabled
    if config is not None and not config.credit_orders_enabled:
        return None

    credit_limit = customer.credit_limit_paisas
    if credit_limit <= 0:
        return None  # 0 or unset — no limit

    outstanding = customer.outstanding_balance_paisas or 0
    total_after = outstanding + order_total_paisas

    if total_after <= credit_limit:
        return None  # Within limit

    limit_display = f"{credit_limit / 100:,.2f}"
    balance_display = f"{outstanding / 100:,.2f}"
    order_display = f"{order_total_paisas / 100:,.2f}"

    if language == "english":
        msg = (
            f"\u26a0\ufe0f *Credit Limit Exceeded*\n\n"
            f"Credit limit: Rs. {limit_display}\n"
            f"Outstanding: Rs. {balance_display}\n"
            f"This order: Rs. {order_display}\n\n"
            f"Please clear your outstanding balance first, "
            f"or contact your distributor."
        )
    else:
        msg = (
            f"\u26a0\ufe0f *Credit Limit Exceed*\n\n"
            f"Credit limit: Rs. {limit_display}\n"
            f"Baqi raqam: Rs. {balance_display}\n"
            f"Yeh order: Rs. {order_display}\n\n"
            f"Pehle outstanding balance clear karein, "
            f"ya distributor se baat karein."
        )

    logger.warning(
        "credit_check.limit_exceeded",
        customer_suffix=to[-4:],
        credit_limit=credit_limit,
        outstanding=outstanding,
        order_total=order_total_paisas,
    )
    return [build_text_message(to, msg)]


def get_available_credit(customer: Customer | None) -> int:
    """Calculate remaining available credit for this customer.

    Args:
        customer: Customer model.

    Returns:
        Available credit in paisas (0 if no limit or no customer).
    """
    if customer is None:
        return 0
    if customer.credit_limit_paisas <= 0:
        return 0
    outstanding = customer.outstanding_balance_paisas or 0
    return max(0, customer.credit_limit_paisas - outstanding)


# ═══════════════════════════════════════════════════════════════════
# HUMAN HANDOFF
# ═══════════════════════════════════════════════════════════════════


async def initiate_handoff(
    session: Session,
    *,
    reason: str,
    session_repo: SessionRepository,
    language: str = "roman_urdu",
    to: str,
) -> list[dict]:
    """Transition the session to HANDOFF state.

    Persists the previous state so the operator can return the
    customer to the correct flow when done.

    Args:
        session: Current session.
        reason: Why handoff was triggered.
        session_repo: For state persistence.
        language: Customer language.
        to: WhatsApp recipient.

    Returns:
        Handoff notification message.
    """
    state_data = dict(session.state_data or {})
    state_data["handoff_reason"] = reason
    state_data["handoff_previous_state"] = session.current_state

    tr = transition(
        session.current_state,
        SessionStateA.HANDOFF.value,
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.HANDOFF.value,
            previous_state=session.current_state,
            state_data=state_data,
        )

    logger.info(
        "handoff.initiated",
        session_id=str(session.id),
        reason=reason,
        previous_state=session.current_state,
    )

    if language == "english":
        msg = (
            "\U0001f9d1\u200d\U0001f4bc *Connecting to human operator*\n\n"
            "Your request has been escalated.\n"
            "A representative will respond shortly.\n\n"
            "Say *menu* anytime to return to the bot."
        )
    else:
        msg = (
            "\U0001f9d1\u200d\U0001f4bc *Insaan se connect ho rahe hain*\n\n"
            "Aapki request escalate ho gayi hai.\n"
            "Koi jaldi jawab dega.\n\n"
            "*menu* likhein bot pe wapas aane ke liye."
        )

    return [build_text_message(to, msg)]


async def release_handoff(
    session: Session,
    *,
    session_repo: SessionRepository,
    language: str = "roman_urdu",
    to: str,
) -> list[dict]:
    """Release the customer from HANDOFF back to the previous state.

    If the previous state is unknown, returns to MAIN_MENU.

    Args:
        session: Current session (must be in HANDOFF state).
        session_repo: For state persistence.
        language: Customer language.
        to: WhatsApp recipient.

    Returns:
        Release notification message.
    """
    state_data = session.state_data or {}
    previous = state_data.get(
        "handoff_previous_state",
        SessionStateA.MAIN_MENU.value,
    )

    # Clean up handoff data
    clean_data = {
        k: v for k, v in state_data.items()
        if not k.startswith("handoff_")
    }

    tr = transition(
        session.current_state,
        SessionStateA.MAIN_MENU.value,  # Usually return to menu
    )
    if tr.allowed:
        await session_repo.update_state(
            str(session.id),
            SessionStateA.MAIN_MENU.value,
            previous_state=session.current_state,
            state_data=clean_data,
        )

    logger.info(
        "handoff.released",
        session_id=str(session.id),
        previous_state=previous,
    )

    if language == "english":
        msg = (
            "\u2705 *Back to bot mode*\n\n"
            "You can continue using the menu.\n"
            "Say *menu* to see your options."
        )
    else:
        msg = (
            "\u2705 *Bot mode wapas*\n\n"
            "Aap menu use kar sakte hain.\n"
            "*menu* likhein options ke liye."
        )

    return [build_text_message(to, msg)]
