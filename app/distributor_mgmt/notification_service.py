"""Batch notification service — announcements, updates, and feature releases.

Sends notifications to all active distributors or a filtered subset.
Each notification is persisted as a ``scheduled_message`` for audit
trail and retry handling.

Supports:
- System-wide announcements
- Feature release notifications
- Maintenance window alerts
- Custom batch messages
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from loguru import logger

from app.core.constants import RecipientType
from app.db.models.audit import AuditLogCreate, ScheduledMessageCreate
from app.db.models.distributor import Distributor
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.scheduled_message_repo import (
    ScheduledMessageRepository,
)
from app.core.constants import ActorType


class NotificationService:
    """Manages batch notifications to distributors.

    All notifications route through ``scheduled_messages`` so the
    scheduler can handle delivery, retries, and failure tracking.

    Attributes:
        _dist_repo: Distributor repository.
        _msg_repo: Scheduled message repository.
        _audit_repo: Audit log repository.
    """

    def __init__(self) -> None:
        self._dist_repo = DistributorRepository()
        self._msg_repo = ScheduledMessageRepository()
        self._audit_repo = AuditRepository()

    async def send_announcement(
        self,
        *,
        title: str,
        body: str,
        actor_id: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        distributor_ids: Optional[list[str]] = None,
    ) -> dict[str, int]:
        """Send an announcement to all active distributors or a subset.

        Args:
            title: Announcement title (used in formatting).
            body: Announcement body text.
            actor_id: UUID of the admin/owner who initiated.
            scheduled_for: When to send (default: immediate).
            distributor_ids: Optional list of specific distributor
                UUIDs.  If None, sends to all active distributors.

        Returns:
            Dict with ``created`` and ``failed`` counts.
        """
        return await self._send_batch(
            message_type="announcement",
            text=f"📢 {title}\n\n{body}",
            actor_id=actor_id,
            scheduled_for=scheduled_for,
            distributor_ids=distributor_ids,
            metadata={"title": title},
        )

    async def send_feature_release(
        self,
        *,
        feature_name: str,
        description: str,
        actor_id: Optional[str] = None,
    ) -> dict[str, int]:
        """Notify distributors about a new feature release.

        Args:
            feature_name: Name of the new feature.
            description: Description of what it does.
            actor_id: UUID of the admin/owner.

        Returns:
            Dict with ``created`` and ``failed`` counts.
        """
        return await self._send_batch(
            message_type="feature_release",
            text=f"🚀 New Feature: {feature_name}\n\n{description}",
            actor_id=actor_id,
            metadata={"feature_name": feature_name},
        )

    async def send_maintenance_alert(
        self,
        *,
        start_time: str,
        duration: str,
        description: str,
        actor_id: Optional[str] = None,
    ) -> dict[str, int]:
        """Notify distributors about upcoming maintenance.

        Args:
            start_time: Human-readable start time string.
            duration: Expected duration string.
            description: What's being maintained.
            actor_id: UUID of the admin/owner.

        Returns:
            Dict with ``created`` and ``failed`` counts.
        """
        text = (
            f"🔧 Scheduled Maintenance\n\n"
            f"Time: {start_time}\n"
            f"Duration: {duration}\n"
            f"Details: {description}\n\n"
            f"Service may be briefly unavailable during this window."
        )
        return await self._send_batch(
            message_type="maintenance_alert",
            text=text,
            actor_id=actor_id,
            metadata={
                "start_time": start_time,
                "duration": duration,
            },
        )

    async def send_custom_notification(
        self,
        *,
        message_type: str,
        text: str,
        actor_id: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        distributor_ids: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> dict[str, int]:
        """Send a custom notification with arbitrary text.

        Args:
            message_type: Machine-readable message type.
            text: Message text content.
            actor_id: UUID of the admin/owner.
            scheduled_for: When to send (default: immediate).
            distributor_ids: Optional target list.
            metadata: Additional metadata.

        Returns:
            Dict with ``created`` and ``failed`` counts.
        """
        return await self._send_batch(
            message_type=message_type,
            text=text,
            actor_id=actor_id,
            scheduled_for=scheduled_for,
            distributor_ids=distributor_ids,
            metadata=metadata,
        )

    # ── Private helpers ─────────────────────────────────────────────

    async def _send_batch(
        self,
        *,
        message_type: str,
        text: str,
        actor_id: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        distributor_ids: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> dict[str, int]:
        """Core batch send logic.

        Resolves the target audience, creates scheduled_message rows,
        and writes an audit log entry.

        Args:
            message_type: Message type identifier.
            text: Formatted message text.
            actor_id: Optional admin UUID.
            scheduled_for: Send time (defaults to now).
            distributor_ids: Optional target list.
            metadata: Additional metadata.

        Returns:
            Dict with ``created`` and ``failed`` counts.
        """
        if scheduled_for is None:
            scheduled_for = datetime.now(tz=timezone.utc)

        distributors = await self._resolve_audience(distributor_ids)
        if not distributors:
            logger.warning(
                "notification.no_recipients",
                message_type=message_type,
            )
            return {"created": 0, "failed": 0}

        batch_id = str(uuid4())
        created = 0
        failed = 0

        for dist in distributors:
            try:
                idempotency_key = (
                    f"batch:{batch_id}:{dist.id}:{message_type}"
                )

                msg_data = ScheduledMessageCreate(
                    distributor_id=dist.id,
                    recipient_number=dist.whatsapp_number,
                    recipient_type=RecipientType.DISTRIBUTOR,
                    message_type=message_type,
                    message_payload={
                        "text": text,
                        "batch_id": batch_id,
                        **(metadata or {}),
                    },
                    scheduled_for=scheduled_for,
                    reference_id=dist.id,
                    reference_type="distributor",
                    idempotency_key=idempotency_key,
                )

                await self._msg_repo.create(msg_data)
                created += 1

            except Exception as exc:
                logger.error(
                    "notification.create_failed",
                    distributor_id=str(dist.id),
                    message_type=message_type,
                    error=str(exc),
                )
                failed += 1

        # Audit the batch
        await self._audit_batch(
            batch_id=batch_id,
            message_type=message_type,
            total=len(distributors),
            created=created,
            failed=failed,
            actor_id=actor_id,
        )

        logger.info(
            "notification.batch_complete",
            batch_id=batch_id,
            message_type=message_type,
            total=len(distributors),
            created=created,
            failed=failed,
        )

        return {"created": created, "failed": failed}

    async def _resolve_audience(
        self,
        distributor_ids: Optional[list[str]] = None,
    ) -> list[Distributor]:
        """Resolve the target audience for a batch notification.

        If ``distributor_ids`` is provided, fetches each by ID.
        Otherwise fetches all active distributors.

        Args:
            distributor_ids: Optional list of specific UUIDs.

        Returns:
            List of Distributor entities.
        """
        if distributor_ids:
            distributors: list[Distributor] = []
            for did in distributor_ids:
                try:
                    dist = await self._dist_repo.get_by_id(did)
                    if dist and dist.is_active and not dist.is_deleted:
                        distributors.append(dist)
                except Exception as exc:
                    logger.warning(
                        "notification.audience_fetch_failed",
                        distributor_id=did,
                        error=str(exc),
                    )
            return distributors
        return await self._dist_repo.get_active_distributors()

    async def _audit_batch(
        self,
        *,
        batch_id: str,
        message_type: str,
        total: int,
        created: int,
        failed: int,
        actor_id: Optional[str] = None,
    ) -> None:
        """Write an audit log entry for the batch notification.

        Never raises — audit failures are logged but don't block.

        Args:
            batch_id: Unique batch identifier.
            message_type: Message type sent.
            total: Total recipients.
            created: Successfully created count.
            failed: Failed creation count.
            actor_id: Optional admin UUID.
        """
        try:
            audit_entry = AuditLogCreate(
                actor_type=ActorType.OWNER if actor_id else ActorType.SYSTEM,
                actor_id=actor_id,
                action=f"notification.batch.{message_type}",
                entity_type="notification_batch",
                entity_id=batch_id,
                metadata={
                    "batch_id": batch_id,
                    "message_type": message_type,
                    "total_recipients": total,
                    "created": created,
                    "failed": failed,
                },
            )
            await self._audit_repo.create(audit_entry)
        except Exception as exc:
            logger.error(
                "notification.audit_failed",
                batch_id=batch_id,
                error=str(exc),
            )


# ── Module singleton ────────────────────────────────────────────────

notification_service = NotificationService()
