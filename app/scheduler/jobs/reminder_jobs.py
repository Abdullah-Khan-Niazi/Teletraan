"""Subscription reminder and lifecycle scheduler jobs.

Contains APScheduler jobs for:
- ``run_reminder_check`` — generates payment reminders for expiring
  distributors and runs subscription lifecycle transitions.
- ``run_send_scheduled_messages`` — picks up due scheduled_messages
  and sends them via WhatsApp.

Job functions **never raise exceptions** to the scheduler.
"""

from __future__ import annotations

from loguru import logger

from app.core.config import get_settings


# ═══════════════════════════════════════════════════════════════════
# REMINDER CHECK JOB
# ═══════════════════════════════════════════════════════════════════


async def run_reminder_check() -> None:
    """Generate payment reminders and run subscription lifecycle checks.

    Called by APScheduler at the interval defined by
    ``REMINDER_CHECK_INTERVAL_HOURS``.

    Flow:
        1. Run subscription lifecycle checks (cancel → suspend → mark expiring).
        2. Generate reminder messages for expiring distributors.

    This function never raises.
    """
    logger.info("scheduler.reminder_check.start")

    try:
        from app.distributor_mgmt.subscription_manager import (
            subscription_manager,
        )

        lifecycle_result = await subscription_manager.run_lifecycle_checks()
        logger.info(
            "scheduler.reminder_check.lifecycle_done",
            **lifecycle_result,
        )
    except Exception as exc:
        logger.error(
            "scheduler.reminder_check.lifecycle_failed",
            error=str(exc),
        )

    try:
        from app.distributor_mgmt.reminder_service import reminder_service

        reminder_result = await reminder_service.generate_reminders_for_all()
        logger.info(
            "scheduler.reminder_check.reminders_done",
            **reminder_result,
        )
    except Exception as exc:
        logger.error(
            "scheduler.reminder_check.reminders_failed",
            error=str(exc),
        )

    logger.info("scheduler.reminder_check.complete")


# ═══════════════════════════════════════════════════════════════════
# SEND SCHEDULED MESSAGES JOB
# ═══════════════════════════════════════════════════════════════════


async def run_send_scheduled_messages() -> None:
    """Pick up due scheduled_messages and send them via WhatsApp.

    Called by APScheduler every few minutes.  Fetches messages where
    ``status='pending'`` and ``scheduled_for <= now``, sends each
    via WhatsAppNotifier, and marks as sent or failed.

    This function never raises.
    """
    logger.info("scheduler.send_scheduled.start")

    try:
        from app.db.repositories.scheduled_message_repo import (
            ScheduledMessageRepository,
        )
        from app.notifications.whatsapp_notifier import WhatsAppNotifier

        msg_repo = ScheduledMessageRepository()
        notifier = WhatsAppNotifier()

        due_messages = await msg_repo.get_due_messages()
        if not due_messages:
            logger.debug("scheduler.send_scheduled.none_due")
            return

        sent = 0
        failed = 0

        for msg in due_messages:
            try:
                text = msg.message_payload.get("text", "")
                if not text:
                    await msg_repo.mark_failed(
                        str(msg.id), "Empty message payload"
                    )
                    failed += 1
                    continue

                distributor_id = (
                    str(msg.distributor_id) if msg.distributor_id else None
                )

                await notifier.send_text(
                    distributor_id=distributor_id or "",
                    to_number=msg.recipient_number,
                    text=text,
                )
                await msg_repo.mark_sent(str(msg.id))
                sent += 1

            except Exception as exc:
                logger.error(
                    "scheduler.send_scheduled.send_failed",
                    message_id=str(msg.id),
                    number_suffix=msg.recipient_number[-4:],
                    error=str(exc),
                )
                try:
                    await msg_repo.mark_failed(str(msg.id), str(exc))
                except Exception as mark_exc:
                    logger.error(
                        "scheduler.send_scheduled.mark_failed_error",
                        message_id=str(msg.id),
                        error=str(mark_exc),
                    )
                failed += 1

        logger.info(
            "scheduler.send_scheduled.complete",
            total=len(due_messages),
            sent=sent,
            failed=failed,
        )
    except Exception as exc:
        logger.error(
            "scheduler.send_scheduled.fatal",
            error=str(exc),
        )
