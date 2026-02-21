"""Notification log repository — all database operations for the notifications_log table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.audit import NotificationLog, NotificationLogCreate


class NotificationRepository:
    """Repository for notifications_log table operations.

    Notifications are mostly append-only; the only mutable field is
    ``delivery_status`` (updated via webhook callbacks from Meta).
    """

    TABLE = "notifications_log"

    # ── Write ───────────────────────────────────────────────────────

    async def create(self, data: NotificationLogCreate) -> NotificationLog:
        """Insert a new notification log entry.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created NotificationLog.

        Raises:
            DatabaseError: On insert failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .insert(data.model_dump(exclude_none=True, mode="json"))
                .execute()
            )
            logger.debug(
                "db.record_created",
                table=self.TABLE,
                notification_type=data.notification_type,
            )
            return NotificationLog.model_validate(result.data[0])
        except Exception as exc:
            logger.error(
                "db.insert_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to create {self.TABLE}: {exc}",
                operation="create",
            ) from exc

    # ── Read ────────────────────────────────────────────────────────

    async def get_recent(
        self, distributor_id: str, *, limit: int = 50
    ) -> list[NotificationLog]:
        """Fetch recent notification entries for a distributor.

        Args:
            distributor_id: Tenant scope.
            limit: Maximum rows to return (default 50).

        Returns:
            List of NotificationLog entities ordered by sent_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .order("sent_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [
                NotificationLog.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_recent",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch recent {self.TABLE}: {exc}",
                operation="get_recent",
            ) from exc

    # ── Update ──────────────────────────────────────────────────────

    async def update_delivery_status(
        self, id: str, status: str
    ) -> NotificationLog:
        """Update the delivery status of a notification.

        Sets ``delivery_status`` and ``delivery_status_updated_at`` to
        the current UTC time.

        Args:
            id: UUID string of the notification log entry.
            status: New delivery status string.

        Returns:
            The updated NotificationLog.

        Raises:
            NotFoundError: If the notification entry does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .update({
                    "delivery_status": status,
                    "delivery_status_updated_at": now,
                })
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for status update",
                    operation="update_delivery_status",
                )
            logger.debug(
                "notification.delivery_status_updated",
                notification_id=id,
                status=status,
            )
            return NotificationLog.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="update_delivery_status",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update delivery status on {self.TABLE}: {exc}",
                operation="update_delivery_status",
            ) from exc
