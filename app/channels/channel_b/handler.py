"""Channel B — main message handler / dispatcher.

Routes incoming messages to the correct sales flow stage and handles
owner commands for managing the sales pipeline.

Public entry:
    ``handle_channel_b_message(session, text, ...)`` → list[dict]

Owner commands (processed when sender is config.owner_whatsapp_number):
    - "list prospects" → show active prospects
    - "qualify <number>" → force-qualify a prospect
    - "close <prospect_id>" → mark prospect as converted
    - "lost <prospect_id> <reason>" → mark prospect as lost
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.channels.channel_b.onboarding_flow import handle_onboarding_step
from app.channels.channel_b.sales_flow import handle_sales_step
from app.channels.channel_b.state_machine import (
    get_initial_state,
    transition,
)
from app.channels.interrupts import (
    InterruptType,
    detect_interrupt,
    get_target_state_b,
)
from app.channels.session_expiry import (
    is_session_expired,
    refresh_session_timeout,
    should_warn,
)
from app.core.constants import ProspectStatus, SessionStateB
from app.db.models.prospect import ProspectUpdate
from app.db.models.session import Session
from app.db.repositories.prospect_repo import ProspectRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import build_button_message, build_text_message


# ═══════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════

_WELCOME = (
    "Assalam o Alaikum! 👋 Main TELETRAAN hoon.\n"
    "Hum WhatsApp par medicine distributors ke liye order management system "
    "provide karte hain.\n\n"
    "Kya aap apne business ke liye interested hain? (Yes/Haan)"
)

_EXPIRED = (
    "Session expire ho gaya tha. New conversation start karte hain! 😊\n\n"
    "Kya aap TELETRAAN ke baare mein jaanna chahte hain?"
)

_EXPIRY_WARNING = "⏰ Session thori der mein expire ho jayega. Koi aur baat?"

_HANDOFF = (
    "👤 Aapko humari team se connect kar rahe hain.\n"
    "Owner jald respond karenge."
)

_SUPPORT = (
    "🆘 Kya masla aa raha hai? Apna sawal likhen.\n"
    "Ya 'talk to human' likhen direct baat ke liye."
)

_BACK_TO_MENU = (
    "Main menu mein wapis! 👋\n"
    "Kya aap TELETRAAN ke baare mein jaanna chahte hain?"
)


# ═══════════════════════════════════════════════════════════════════
# Owner command patterns
# ═══════════════════════════════════════════════════════════════════

_CMD_LIST_PROSPECTS = "list prospects"
_CMD_QUALIFY = "qualify "
_CMD_CLOSE = "close "
_CMD_LOST = "lost "


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════


async def handle_channel_b_message(
    session: Session,
    text: str,
    *,
    button_id: str | None = None,
    list_id: str | None = None,
    session_repo: SessionRepository,
    prospect_repo: ProspectRepository | None = None,
    is_owner: bool = False,
) -> list[dict]:
    """Process an inbound Channel B message and return response payloads.

    Args:
        session: Current session (must already be loaded/created).
        text: Text input from user.
        button_id: Button reply payload ID, if interactive.
        list_id: List reply row ID, if interactive.
        session_repo: For session state persistence.
        prospect_repo: For prospect data operations.
        is_owner: Whether the sender is the system owner.

    Returns:
        List of WhatsApp message payloads to send back.
    """
    _pros_repo = prospect_repo or ProspectRepository()
    to = session.whatsapp_number
    state = SessionStateB(session.current_state) if session.current_state != "idle" else SessionStateB.IDLE
    interactive_id = button_id or list_id

    logger.info(
        "channel_b.message_received",
        state=state.value,
        has_text=bool(text),
        has_interactive=bool(interactive_id),
        is_owner=is_owner,
        number_suffix=to[-4:] if len(to) >= 4 else to,
    )

    # ── 1. Owner commands (pipeline management) ─────────────────
    if is_owner and text.strip():
        cmd_result = await _handle_owner_command(text.strip(), to, _pros_repo)
        if cmd_result is not None:
            return cmd_result

    # ── 2. Refresh session timeout ──────────────────────────────
    try:
        await refresh_session_timeout(str(session.id), session_repo)
    except Exception as exc:
        logger.error("channel_b.timeout_refresh_failed", error=str(exc))

    # ── 3. Check session expiry ─────────────────────────────────
    if is_session_expired(session):
        await session_repo.update_state(
            str(session.id),
            SessionStateB.GREETING,
            previous_state=state.value,
        )
        return [build_text_message(to, _EXPIRED)]

    # ── 4. Expiry warning ───────────────────────────────────────
    warning_msgs: list[dict] = []
    if should_warn(session):
        warning_msgs = [build_text_message(to, _EXPIRY_WARNING)]

    # ── 5. Interrupt detection ──────────────────────────────────
    if text.strip():
        interrupt = detect_interrupt(text)
        if interrupt is not None:
            interrupt_msgs = await _handle_interrupt(
                session, interrupt, to, session_repo
            )
            return warning_msgs + interrupt_msgs

    # ── 6. IDLE state → start greeting ──────────────────────────
    if state == SessionStateB.IDLE:
        await session_repo.update_state(
            str(session.id),
            SessionStateB.GREETING,
            previous_state=state.value,
        )
        return warning_msgs + [build_text_message(to, _WELCOME)]

    # ── 7. Dispatch to flow handler ─────────────────────────────
    if state == SessionStateB.ONBOARDING_SETUP:
        flow_msgs = await handle_onboarding_step(
            session,
            text,
            button_id=button_id,
            session_repo=session_repo,
            prospect_repo=_pros_repo,
        )
    else:
        flow_msgs = await handle_sales_step(
            session,
            text,
            button_id=button_id,
            list_id=list_id,
            session_repo=session_repo,
            prospect_repo=_pros_repo,
        )

    return warning_msgs + flow_msgs


# ═══════════════════════════════════════════════════════════════════
# Interrupt handling
# ═══════════════════════════════════════════════════════════════════


async def _handle_interrupt(
    session: Session,
    interrupt: InterruptType,
    to: str,
    session_repo: SessionRepository,
) -> list[dict]:
    """Handle a detected interrupt — transition state and respond."""
    target = get_target_state_b(interrupt)
    if target is None:
        return []

    await session_repo.update_state(
        str(session.id),
        target.value,
        previous_state=session.current_state,
    )

    if interrupt == InterruptType.HANDOFF:
        logger.info(
            "channel_b.handoff",
            session_id=str(session.id),
            whatsapp=to[-4:],
        )
        return [build_text_message(to, _HANDOFF)]
    elif interrupt == InterruptType.HELP:
        return [build_text_message(to, _SUPPORT)]
    elif interrupt in {InterruptType.CANCEL, InterruptType.GOODBYE}:
        return [build_text_message(to, _BACK_TO_MENU)]
    elif interrupt == InterruptType.MENU:
        return [build_text_message(to, _WELCOME)]
    else:
        return [build_text_message(to, _BACK_TO_MENU)]


# ═══════════════════════════════════════════════════════════════════
# Owner commands
# ═══════════════════════════════════════════════════════════════════


async def _handle_owner_command(
    text: str,
    to: str,
    prospect_repo: ProspectRepository,
) -> Optional[list[dict]]:
    """Parse and execute owner pipeline commands.

    Returns list of messages if a command was recognized, None otherwise
    (so the handler falls through to normal flow).
    """
    lower = text.lower().strip()

    # ── list prospects ──────────────────────────────────────────
    if lower == _CMD_LIST_PROSPECTS:
        return await _cmd_list_prospects(to, prospect_repo)

    # ── qualify <whatsapp_number> ───────────────────────────────
    if lower.startswith(_CMD_QUALIFY):
        number = text[len(_CMD_QUALIFY):].strip()
        return await _cmd_qualify(to, number, prospect_repo)

    # ── close <prospect_id> ─────────────────────────────────────
    if lower.startswith(_CMD_CLOSE):
        prospect_id = text[len(_CMD_CLOSE):].strip()
        return await _cmd_close(to, prospect_id, prospect_repo)

    # ── lost <prospect_id> <reason> ─────────────────────────────
    if lower.startswith(_CMD_LOST):
        remainder = text[len(_CMD_LOST):].strip()
        parts = remainder.split(maxsplit=1)
        prospect_id = parts[0] if parts else ""
        reason = parts[1] if len(parts) > 1 else "No reason given"
        return await _cmd_lost(to, prospect_id, reason, prospect_repo)

    return None


async def _cmd_list_prospects(
    to: str, prospect_repo: ProspectRepository
) -> list[dict]:
    """List active (non-converted, non-lost) prospects."""
    active_statuses = [
        ProspectStatus.NEW,
        ProspectStatus.QUALIFIED,
        ProspectStatus.DEMO_BOOKED,
        ProspectStatus.PROPOSAL_SENT,
        ProspectStatus.PAYMENT_PENDING,
    ]
    all_prospects = []
    for status in active_statuses:
        prospects = await prospect_repo.get_by_status(status.value)
        all_prospects.extend(prospects)

    if not all_prospects:
        return [build_text_message(to, "📋 No active prospects.")]

    lines = ["📋 *Active Prospects:*\n"]
    for p in all_prospects[:20]:
        name = p.name or "Unknown"
        biz = p.business_name or ""
        status_emoji = {
            ProspectStatus.NEW: "🆕",
            ProspectStatus.QUALIFIED: "✅",
            ProspectStatus.DEMO_BOOKED: "📅",
            ProspectStatus.PROPOSAL_SENT: "📋",
            ProspectStatus.PAYMENT_PENDING: "💳",
        }.get(p.status, "❓")
        lines.append(
            f"{status_emoji} {name} ({biz})\n"
            f"   📞 ...{p.whatsapp_number[-4:]}\n"
            f"   Status: {p.status.value}\n"
            f"   ID: {p.id}"
        )
    return [build_text_message(to, "\n\n".join(lines))]


async def _cmd_qualify(
    to: str, number: str, prospect_repo: ProspectRepository
) -> list[dict]:
    """Force-qualify a prospect by WhatsApp number."""
    prospect = await prospect_repo.get_by_whatsapp_number(number)
    if not prospect:
        return [build_text_message(to, f"❌ Prospect not found: {number}")]

    await prospect_repo.update(
        str(prospect.id),
        ProspectUpdate(status=ProspectStatus.QUALIFIED),
    )
    return [build_text_message(
        to,
        f"✅ {prospect.name or number} marked as QUALIFIED.",
    )]


async def _cmd_close(
    to: str, prospect_id: str, prospect_repo: ProspectRepository
) -> list[dict]:
    """Mark prospect as converted."""
    try:
        prospect = await prospect_repo.get_by_id_or_raise(prospect_id)
    except Exception:
        return [build_text_message(to, f"❌ Prospect not found: {prospect_id}")]

    await prospect_repo.update(
        str(prospect.id),
        ProspectUpdate(status=ProspectStatus.CONVERTED),
    )
    return [build_text_message(
        to,
        f"✅ {prospect.name or 'Prospect'} marked as CONVERTED.",
    )]


async def _cmd_lost(
    to: str,
    prospect_id: str,
    reason: str,
    prospect_repo: ProspectRepository,
) -> list[dict]:
    """Mark prospect as lost with reason."""
    try:
        prospect = await prospect_repo.get_by_id_or_raise(prospect_id)
    except Exception:
        return [build_text_message(to, f"❌ Prospect not found: {prospect_id}")]

    await prospect_repo.update(
        str(prospect.id),
        ProspectUpdate(status=ProspectStatus.LOST, lost_reason=reason),
    )
    return [build_text_message(
        to,
        f"❌ {prospect.name or 'Prospect'} marked as LOST.\n"
        f"Reason: {reason}",
    )]
