"""Payment reminder generation service with deduplication.

Generates scheduled reminders at 7-day, 3-day, 1-day, and
expiry-day intervals before a distributor's subscription expires.

Deduplication is enforced via the ``idempotency_key`` column on
``scheduled_messages``.  The key format is:

    ``sub_reminder:{distributor_id}:{days_before}:{yyyy-mm}``

This prevents duplicate reminders for the same billing cycle even if
the job runs multiple times per day.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from app.core.config import get_settings
from app.core.constants import RecipientType, SubscriptionStatus
from app.db.models.audit import ScheduledMessageCreate
from app.db.models.distributor import Distributor
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.scheduled_message_repo import (
    ScheduledMessageRepository,
)
from app.notifications.templates import get_template


# ── Reminder schedule definition ────────────────────────────────────

_REMINDER_SCHEDULE: list[dict] = [
    {
        "days_before": 7,
        "template_key": "OWNER_SUBSCRIPTION_7_DAYS",
        "message_type": "subscription_reminder_7d",
    },
    {
        "days_before": 3,
        "template_key": "OWNER_SUBSCRIPTION_3_DAYS",
        "message_type": "subscription_reminder_3d",
    },
    {
        "days_before": 1,
        "template_key": "OWNER_SUBSCRIPTION_1_DAY",
        "message_type": "subscription_reminder_1d",
    },
    {
        "days_before": 0,
        "template_key": "OWNER_SUBSCRIPTION_EXPIRY_DAY",
        "message_type": "subscription_reminder_expiry",
    },
]


class ReminderService:
    """Generates and schedules subscription payment reminders.

    Reminders are created as ``scheduled_messages`` rows with
    idempotency keys to prevent duplicates.  The scheduler picks
    up due messages and sends them via WhatsApp.

    Attributes:
        _dist_repo: Distributor repository.
        _msg_repo: Scheduled message repository.
    """

    def __init__(self) -> None:
        self._dist_repo = DistributorRepository()
        self._msg_repo = ScheduledMessageRepository()

    async def generate_reminders_for_all(self) -> dict[str, int]:
        """Scan all expiring distributors and generate reminders.

        Called by the scheduler job.  For each distributor whose
        subscription_end is within 7 days, checks which reminder
        milestones apply and creates scheduled messages for any
        that haven't been created yet (deduplication via
        idempotency_key).

        Returns:
            Dict with ``created`` and ``skipped`` counts.
        """
        distributors = await self._dist_repo.get_expiring_subscriptions(
            days_ahead=7,
        )
        created = 0
        skipped = 0

        for dist in distributors:
            if dist.subscription_status not in (
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.EXPIRING,
            ):
                continue

            if not dist.subscription_end:
                logger.warning(
                    "reminder.no_subscription_end",
                    distributor_id=str(dist.id),
                )
                continue

            result = await self._generate_reminders_for_distributor(dist)
            created += result["created"]
            skipped += result["skipped"]

        logger.info(
            "reminder.generation_complete",
            total_distributors=len(distributors),
            created=created,
            skipped=skipped,
        )
        return {"created": created, "skipped": skipped}

    async def _generate_reminders_for_distributor(
        self,
        distributor: Distributor,
    ) -> dict[str, int]:
        """Generate reminders for a single distributor.

        Checks each milestone in the reminder schedule and creates
        a scheduled message if the milestone is applicable and
        hasn't been created yet.

        Args:
            distributor: Distributor with subscription_end set.

        Returns:
            Dict with ``created`` and ``skipped`` counts.
        """
        now = datetime.now(tz=timezone.utc)
        sub_end = distributor.subscription_end
        if sub_end is None:
            return {"created": 0, "skipped": 0}

        # Ensure sub_end is timezone-aware
        if sub_end.tzinfo is None:
            sub_end = sub_end.replace(tzinfo=timezone.utc)

        days_until_expiry = (sub_end - now).total_seconds() / 86400
        created = 0
        skipped = 0

        for reminder in _REMINDER_SCHEDULE:
            days_before = reminder["days_before"]

            # Only generate if we're within the window
            if days_until_expiry > days_before:
                continue

            idempotency_key = self._build_idempotency_key(
                distributor_id=str(distributor.id),
                days_before=days_before,
                subscription_end=sub_end,
            )

            # Check for duplicate — try to create; if idempotency_key
            # already exists, the DB UNIQUE constraint will reject it
            already_exists = await self._reminder_exists(idempotency_key)
            if already_exists:
                skipped += 1
                continue

            try:
                await self._create_reminder(
                    distributor=distributor,
                    reminder=reminder,
                    idempotency_key=idempotency_key,
                )
                created += 1
            except Exception as exc:
                logger.error(
                    "reminder.create_failed",
                    distributor_id=str(distributor.id),
                    reminder_type=reminder["message_type"],
                    error=str(exc),
                )
                skipped += 1

        return {"created": created, "skipped": skipped}

    async def _create_reminder(
        self,
        *,
        distributor: Distributor,
        reminder: dict,
        idempotency_key: str,
    ) -> None:
        """Create a single scheduled reminder message.

        Args:
            distributor: Target distributor.
            reminder: Reminder schedule entry with template_key,
                message_type, and days_before.
            idempotency_key: Deduplication key.
        """
        settings = get_settings()
        language = distributor.bot_language_default.value

        # Build the renewal link
        renewal_link = self._build_renewal_link(str(distributor.id))

        # Resolve template and format message
        template_text = get_template(
            reminder["template_key"],
            language,
        )
        message_text = template_text.format(
            renewal_link=renewal_link,
        )

        # Schedule for immediate delivery (the scheduler job will pick
        # them up on the next run)
        scheduled_for = datetime.now(tz=timezone.utc)

        msg_data = ScheduledMessageCreate(
            distributor_id=distributor.id,
            recipient_number=distributor.whatsapp_number,
            recipient_type=RecipientType.DISTRIBUTOR,
            message_type=reminder["message_type"],
            message_payload={
                "text": message_text,
                "template_key": reminder["template_key"],
                "days_before": reminder["days_before"],
                "subscription_end": (
                    distributor.subscription_end.isoformat()
                    if distributor.subscription_end
                    else None
                ),
            },
            scheduled_for=scheduled_for,
            reference_id=distributor.id,
            reference_type="distributor",
            idempotency_key=idempotency_key,
        )

        await self._msg_repo.create(msg_data)

        logger.info(
            "reminder.created",
            distributor_id=str(distributor.id),
            reminder_type=reminder["message_type"],
            number_suffix=distributor.whatsapp_number[-4:],
        )

    async def _reminder_exists(self, idempotency_key: str) -> bool:
        """Check if a reminder with the given idempotency_key already exists.

        Queries the scheduled_messages table for a matching
        idempotency_key.  This is faster than relying on the DB
        UNIQUE constraint and catching the exception.

        Args:
            idempotency_key: The deduplication key to check.

        Returns:
            True if a matching message already exists.
        """
        try:
            from app.db.client import get_db_client

            client = get_db_client()
            result = (
                await client.table("scheduled_messages")
                .select("id")
                .eq("idempotency_key", idempotency_key)
                .maybe_single()
                .execute()
            )
            return result.data is not None
        except Exception as exc:
            logger.error(
                "reminder.dedup_check_failed",
                idempotency_key=idempotency_key,
                error=str(exc),
            )
            # On error, assume it doesn't exist — the DB UNIQUE
            # constraint will catch true duplicates
            return False

    @staticmethod
    def _build_idempotency_key(
        distributor_id: str,
        days_before: int,
        subscription_end: datetime,
    ) -> str:
        """Build a deterministic idempotency key for a reminder.

        Format: ``sub_reminder:{distributor_id}:{days_before}:{yyyy-mm}``

        The year-month component ties the key to a specific billing
        cycle so that a renewed subscription gets fresh reminders.

        Args:
            distributor_id: UUID string.
            days_before: Days-before-expiry milestone.
            subscription_end: Subscription expiry date.

        Returns:
            Idempotency key string.
        """
        cycle = subscription_end.strftime("%Y-%m")
        return f"sub_reminder:{distributor_id}:{days_before}:{cycle}"

    @staticmethod
    def _build_renewal_link(distributor_id: str) -> str:
        """Build the subscription renewal link.

        Uses the payment_callback_base_url from settings if available,
        otherwise returns a placeholder.

        Args:
            distributor_id: UUID string.

        Returns:
            Renewal URL string.
        """
        settings = get_settings()
        base_url = settings.payment_callback_base_url
        if base_url:
            return f"{base_url}/renew/{distributor_id}"
        return f"https://teletraan.pk/renew/{distributor_id}"

    async def generate_suspension_notification(
        self,
        distributor: Distributor,
    ) -> None:
        """Send a suspension notification to a distributor.

        Called by the subscription manager when a distributor is
        suspended.  Creates a scheduled message with the suspension
        template.

        Args:
            distributor: The suspended distributor.
        """
        settings = get_settings()
        language = distributor.bot_language_default.value
        renewal_link = self._build_renewal_link(str(distributor.id))

        template_text = get_template(
            "OWNER_SUBSCRIPTION_SUSPENDED",
            language,
        )
        message_text = template_text.format(
            renewal_link=renewal_link,
            grace_days=distributor.grace_period_days,
        )

        idempotency_key = (
            f"sub_suspended:{distributor.id}:"
            f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}"
        )

        already_exists = await self._reminder_exists(idempotency_key)
        if already_exists:
            return

        msg_data = ScheduledMessageCreate(
            distributor_id=distributor.id,
            recipient_number=distributor.whatsapp_number,
            recipient_type=RecipientType.DISTRIBUTOR,
            message_type="subscription_suspended",
            message_payload={
                "text": message_text,
                "template_key": "OWNER_SUBSCRIPTION_SUSPENDED",
                "grace_period_days": distributor.grace_period_days,
            },
            scheduled_for=datetime.now(tz=timezone.utc),
            reference_id=distributor.id,
            reference_type="distributor",
            idempotency_key=idempotency_key,
        )

        await self._msg_repo.create(msg_data)

        logger.info(
            "reminder.suspension_notification_created",
            distributor_id=str(distributor.id),
            number_suffix=distributor.whatsapp_number[-4:],
        )

    async def generate_cancellation_notification(
        self,
        distributor: Distributor,
    ) -> None:
        """Send a cancellation notification to a distributor.

        Called by the subscription manager when a distributor's
        subscription is cancelled after grace period expiry.

        Args:
            distributor: The cancelled distributor.
        """
        language = distributor.bot_language_default.value

        template_text = get_template(
            "OWNER_SUBSCRIPTION_CANCELLED",
            language,
        )
        message_text = template_text.format(
            support_link="https://teletraan.pk/support",
        )

        idempotency_key = (
            f"sub_cancelled:{distributor.id}:"
            f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}"
        )

        already_exists = await self._reminder_exists(idempotency_key)
        if already_exists:
            return

        msg_data = ScheduledMessageCreate(
            distributor_id=distributor.id,
            recipient_number=distributor.whatsapp_number,
            recipient_type=RecipientType.DISTRIBUTOR,
            message_type="subscription_cancelled",
            message_payload={
                "text": message_text,
                "template_key": "OWNER_SUBSCRIPTION_CANCELLED",
            },
            scheduled_for=datetime.now(tz=timezone.utc),
            reference_id=distributor.id,
            reference_type="distributor",
            idempotency_key=idempotency_key,
        )

        await self._msg_repo.create(msg_data)

        logger.info(
            "reminder.cancellation_notification_created",
            distributor_id=str(distributor.id),
            number_suffix=distributor.whatsapp_number[-4:],
        )


# ── Module singleton ────────────────────────────────────────────────

reminder_service = ReminderService()
