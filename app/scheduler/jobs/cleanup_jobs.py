"""Cleanup scheduler jobs — session cleanup and expired payment links.

Contains APScheduler jobs for:
- ``run_session_cleanup`` — deletes expired conversation sessions.
- ``run_expired_payment_cleanup`` — marks stale payment links as
  expired.

Job functions **never raise exceptions** to the scheduler.
"""

from __future__ import annotations

from loguru import logger


# ═══════════════════════════════════════════════════════════════════
# SESSION CLEANUP JOB
# ═══════════════════════════════════════════════════════════════════


async def run_session_cleanup() -> None:
    """Delete expired conversation sessions.

    Called by APScheduler at the interval defined by
    ``SESSION_CLEANUP_INTERVAL_HOURS``.

    Fetches sessions where ``expires_at <= now`` and deletes them.
    This keeps the sessions table lean and prevents stale context
    from being used.

    This function never raises.
    """
    logger.info("scheduler.session_cleanup.start")

    try:
        from app.db.repositories.session_repo import SessionRepository

        session_repo = SessionRepository()
        expired_sessions = await session_repo.get_expired_sessions()

        if not expired_sessions:
            logger.debug("scheduler.session_cleanup.none_expired")
            return

        deleted = 0
        failed = 0

        for session in expired_sessions:
            try:
                await session_repo.delete_session(str(session.id))
                deleted += 1
            except Exception as exc:
                logger.error(
                    "scheduler.session_cleanup.delete_failed",
                    session_id=str(session.id),
                    error=str(exc),
                )
                failed += 1

        logger.info(
            "scheduler.session_cleanup.complete",
            total=len(expired_sessions),
            deleted=deleted,
            failed=failed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.session_cleanup.fatal",
            error=str(exc),
        )


# ═══════════════════════════════════════════════════════════════════
# EXPIRED PAYMENT CLEANUP JOB
# ═══════════════════════════════════════════════════════════════════


async def run_expired_payment_cleanup() -> None:
    """Mark stale pending payments as expired.

    Called by APScheduler alongside session cleanup.  Delegates
    to PaymentService.expire_stale_payments() which queries for
    pending payments past their ``link_expires_at`` time.

    This function never raises.
    """
    logger.info("scheduler.payment_cleanup.start")

    try:
        from app.payments.service import payment_service

        result = await payment_service.expire_stale_payments()
        logger.info(
            "scheduler.payment_cleanup.complete",
            expired_count=result,
        )
    except Exception as exc:
        logger.error(
            "scheduler.payment_cleanup.fatal",
            error=str(exc),
        )
