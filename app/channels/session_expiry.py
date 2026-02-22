"""Session expiry — warning and auto-expire logic.

Provides functions to:
1. Check sessions approaching timeout (50 min) and send warnings.
2. Auto-expire sessions past timeout (60 min) with notification.

Designed to be called by the scheduler at regular intervals
(e.g. every 2 minutes).  Also exports a ``check_and_warn``
helper that can be called inline during message processing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from app.core.constants import SESSION_TIMEOUT_MINUTES_DEFAULT, SessionStateA
from app.db.models.session import Session, SessionUpdate
from app.db.repositories.session_repo import SessionRepository


# Thresholds
_WARNING_MINUTES: int = 50
_EXPIRY_MINUTES: int = SESSION_TIMEOUT_MINUTES_DEFAULT  # 60


# ═══════════════════════════════════════════════════════════════════
# INLINE HELPERS (called during message processing)
# ═══════════════════════════════════════════════════════════════════


def is_session_expired(session: Session) -> bool:
    """Check whether a session has passed its expiry timestamp.

    Args:
        session: Session row from the database.

    Returns:
        True if the session is past its ``expires_at``.
    """
    now = datetime.now(timezone.utc)
    return session.expires_at.astimezone(timezone.utc) < now


def minutes_until_expiry(session: Session) -> float:
    """Calculate minutes remaining until session expiry.

    Args:
        session: Session row from the database.

    Returns:
        Minutes remaining (negative if already expired).
    """
    now = datetime.now(timezone.utc)
    delta = session.expires_at.astimezone(timezone.utc) - now
    return delta.total_seconds() / 60


def should_warn(session: Session) -> bool:
    """Check if a session should receive an expiry warning.

    Returns True when the session is within the warning window
    (between 50 and 60 minutes elapsed) and is not idle.

    Args:
        session: Session row from the database.

    Returns:
        True if a warning should be sent.
    """
    if session.current_state == "idle":
        return False

    remaining = minutes_until_expiry(session)
    warning_window = _EXPIRY_MINUTES - _WARNING_MINUTES  # 10 min

    return 0 < remaining <= warning_window


async def refresh_session_timeout(
    session_id: str,
    session_repo: SessionRepository,
) -> Session:
    """Reset the session's expiry timestamp to now + timeout.

    Called when a new message arrives to keep the session alive.

    Args:
        session_id: UUID string of the session.
        session_repo: SessionRepository instance.

    Returns:
        Updated Session.

    Raises:
        DatabaseError: If the update fails.
    """
    new_expiry = datetime.now(timezone.utc) + timedelta(
        minutes=_EXPIRY_MINUTES
    )
    update = SessionUpdate(
        expires_at=new_expiry,
        last_message_at=datetime.now(timezone.utc),
    )
    result = await session_repo.update(session_id, update)
    logger.debug(
        "session.timeout_refreshed",
        session_id=session_id,
        expires_at=new_expiry.isoformat(),
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# BATCH EXPIRY (called by scheduler)
# ═══════════════════════════════════════════════════════════════════


async def process_expiring_sessions(
    session_repo: SessionRepository,
    *,
    send_warning_fn: Optional[object] = None,
    send_expired_fn: Optional[object] = None,
) -> dict[str, int]:
    """Scan sessions for warnings and auto-expiry.

    1. Finds non-idle sessions within the warning window and
       sends a warning (if ``send_warning_fn`` is provided).
    2. Finds sessions past their ``expires_at`` and resets them
       to idle (if ``send_expired_fn`` is provided, notifies first).

    Args:
        session_repo: SessionRepository instance.
        send_warning_fn: Async callable ``(session) -> None`` that
            sends the 50-min warning message via WhatsApp.
        send_expired_fn: Async callable ``(session) -> None`` that
            sends the session-expired notification via WhatsApp.

    Returns:
        Dict with 'warned' and 'expired' counts.
    """
    warned = 0
    expired = 0

    # Step 1 — Process expired sessions
    expired_sessions = await session_repo.get_expired_sessions()
    for session in expired_sessions:
        try:
            if send_expired_fn is not None:
                await send_expired_fn(session)  # type: ignore[misc]

            # Reset to idle and clear order draft
            await session_repo.update_state(
                id=str(session.id),
                new_state="idle",
                previous_state=session.current_state,
                pending_order_draft={},
            )
            expired += 1
            logger.info(
                "session.auto_expired",
                session_id=str(session.id),
                previous_state=session.current_state,
                number_suffix=session.whatsapp_number[-4:],
            )
        except Exception as exc:
            logger.error(
                "session.expiry_failed",
                session_id=str(session.id),
                error=str(exc),
            )

    # Step 2 — Warn approaching sessions
    # We need sessions that are NOT expired yet but within warning window.
    # Since the repo doesn't have a specific method for this, we query
    # non-idle sessions and filter in Python. This is acceptable for the
    # typical volume (hundreds of sessions, not millions).
    try:
        now = datetime.now(timezone.utc)
        warning_cutoff = now + timedelta(
            minutes=(_EXPIRY_MINUTES - _WARNING_MINUTES)
        )
        # Get sessions expiring between now and warning cutoff
        # that are not idle. We use the repo's client for a targeted query.
        from app.db.client import get_db_client

        client = get_db_client()
        result = (
            await client.table("sessions")
            .select("*")
            .neq("current_state", "idle")
            .gt("expires_at", now.isoformat())
            .lte("expires_at", warning_cutoff.isoformat())
            .execute()
        )

        for row in result.data:
            session = Session.model_validate(row)
            # Only warn if not already warned (use state_data flag)
            if session.state_data.get("expiry_warned"):
                continue

            try:
                if send_warning_fn is not None:
                    await send_warning_fn(session)  # type: ignore[misc]

                # Mark as warned so we don't warn again
                state_data = {**session.state_data, "expiry_warned": True}
                await session_repo.update(
                    str(session.id),
                    SessionUpdate(state_data=state_data),
                )
                warned += 1
                logger.info(
                    "session.expiry_warned",
                    session_id=str(session.id),
                    number_suffix=session.whatsapp_number[-4:],
                )
            except Exception as exc:
                logger.error(
                    "session.warning_failed",
                    session_id=str(session.id),
                    error=str(exc),
                )

    except Exception as exc:
        logger.error("session.warning_scan_failed", error=str(exc))

    logger.info(
        "session.expiry_batch_complete",
        warned=warned,
        expired=expired,
    )
    return {"warned": warned, "expired": expired}
