"""Scheduled message repository — all database operations for the scheduled_messages table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.audit import (
    ScheduledMessage,
    ScheduledMessageCreate,
    ScheduledMessageUpdate,
)


class ScheduledMessageRepository:
    """Repository for scheduled_messages table operations.

    Scheduled messages are queued outbound messages sent by the
    scheduler at ``scheduled_for`` time.  The lifecycle is:
    pending → sent | failed | cancelled.
    """

    TABLE = "scheduled_messages"

    # ── Write ───────────────────────────────────────────────────────

    async def create(self, data: ScheduledMessageCreate) -> ScheduledMessage:
        """Insert a new scheduled message row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created ScheduledMessage.

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
            logger.info(
                "db.record_created",
                table=self.TABLE,
                message_type=data.message_type,
                number_suffix=data.recipient_number[-4:],
            )
            return ScheduledMessage.model_validate(result.data[0])
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

    async def get_due_messages(self) -> list[ScheduledMessage]:
        """Fetch messages that are pending and due for delivery.

        Returns messages where ``status='pending'`` and
        ``scheduled_for <= now``.

        Returns:
            List of ScheduledMessage entities ordered by scheduled_for ASC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("status", "pending")
                .lte("scheduled_for", now)
                .order("scheduled_for")
                .execute()
            )
            return [
                ScheduledMessage.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_due_messages",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch due {self.TABLE}: {exc}",
                operation="get_due_messages",
            ) from exc

    # ── Lifecycle transitions ───────────────────────────────────────

    async def _get_or_raise(self, id: str) -> ScheduledMessage:
        """Internal helper to fetch a scheduled message or raise.

        Args:
            id: UUID string of the scheduled message.

        Returns:
            ScheduledMessage entity.

        Raises:
            NotFoundError: If no message matches the given id.
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("id", id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return ScheduledMessage.model_validate(result.data)
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="_get_or_raise",
            )
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="_get_or_raise",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="_get_or_raise",
            ) from exc

    async def mark_sent(self, id: str) -> ScheduledMessage:
        """Mark a scheduled message as sent.

        Sets ``status='sent'`` and ``sent_at`` to the current UTC time.

        Args:
            id: UUID string of the scheduled message.

        Returns:
            The updated ScheduledMessage.

        Raises:
            NotFoundError: If the message does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .update({"status": "sent", "sent_at": now})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for mark_sent",
                    operation="mark_sent",
                )
            logger.info("scheduled_message.sent", message_id=id)
            return ScheduledMessage.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="mark_sent",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to mark {self.TABLE} as sent: {exc}",
                operation="mark_sent",
            ) from exc

    async def mark_failed(self, id: str, error: str) -> ScheduledMessage:
        """Record a delivery failure for a scheduled message.

        Increments ``retry_count`` and sets ``error_message``.  If
        ``retry_count >= max_retries`` after the increment, also sets
        ``status='failed'``.

        Args:
            id: UUID string of the scheduled message.
            error: Human-readable error description.

        Returns:
            The updated ScheduledMessage.

        Raises:
            NotFoundError: If the message does not exist.
            DatabaseError: On update failure.
        """
        try:
            current = await self._get_or_raise(id)
            new_retry_count = current.retry_count + 1
            payload: dict = {
                "retry_count": new_retry_count,
                "error_message": error,
            }
            if new_retry_count >= current.max_retries:
                payload["status"] = "failed"
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update(payload)
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for mark_failed",
                    operation="mark_failed",
                )
            logger.warning(
                "scheduled_message.failed",
                message_id=id,
                retry_count=new_retry_count,
                max_retries=current.max_retries,
                permanently_failed=new_retry_count >= current.max_retries,
            )
            return ScheduledMessage.model_validate(result.data[0])
        except (NotFoundError, DatabaseError):
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="mark_failed",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to mark {self.TABLE} as failed: {exc}",
                operation="mark_failed",
            ) from exc

    async def cancel(self, id: str) -> ScheduledMessage:
        """Cancel a scheduled message.

        Sets ``status='cancelled'``.

        Args:
            id: UUID string of the scheduled message.

        Returns:
            The updated ScheduledMessage.

        Raises:
            NotFoundError: If the message does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update({"status": "cancelled"})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for cancel",
                    operation="cancel",
                )
            logger.info("scheduled_message.cancelled", message_id=id)
            return ScheduledMessage.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="cancel",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to cancel {self.TABLE}: {exc}",
                operation="cancel",
            ) from exc
