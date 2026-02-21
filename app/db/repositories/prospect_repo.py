"""Prospect repository — all database operations for the prospects table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.prospect import Prospect, ProspectCreate, ProspectUpdate


class ProspectRepository:
    """Repository for prospects table operations.

    Prospects are Channel B leads — potential distributor clients.
    There is no ``distributor_id`` scope because prospects are not yet
    distributors.  WhatsApp number is the natural unique key.
    """

    TABLE = "prospects"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(self, id: str) -> Optional[Prospect]:
        """Fetch a single prospect by primary key.

        Args:
            id: UUID string of the prospect.

        Returns:
            Prospect if found, None otherwise.

        Raises:
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
                return Prospect.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_id",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_by_id",
            ) from exc

    async def get_by_id_or_raise(self, id: str) -> Prospect:
        """Fetch a single prospect or raise NotFoundError.

        Args:
            id: UUID string of the prospect.

        Returns:
            Prospect entity.

        Raises:
            NotFoundError: If no prospect matches the given id.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def get_by_whatsapp_number(
        self, whatsapp_number: str
    ) -> Optional[Prospect]:
        """Look up a prospect by their E.164 WhatsApp number.

        Args:
            whatsapp_number: E.164 formatted phone number.

        Returns:
            Prospect if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("whatsapp_number", whatsapp_number)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Prospect.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_whatsapp_number",
                number_suffix=whatsapp_number[-4:],
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by whatsapp_number: {exc}",
                operation="get_by_whatsapp_number",
            ) from exc

    async def create(self, data: ProspectCreate) -> Prospect:
        """Insert a new prospect row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created Prospect.

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
                number_suffix=data.whatsapp_number[-4:],
            )
            return Prospect.model_validate(result.data[0])
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

    async def update(self, id: str, data: ProspectUpdate) -> Prospect:
        """Update an existing prospect.

        Args:
            id: UUID string of the prospect to update.
            data: Validated update payload (only non-None fields written).

        Returns:
            The updated Prospect.

        Raises:
            NotFoundError: If the prospect does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True, mode="json")
            if not payload:
                return await self.get_by_id_or_raise(id)
            result = (
                await client.table(self.TABLE)
                .update(payload)
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for update",
                    operation="update",
                )
            return Prospect.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update {self.TABLE}: {exc}",
                operation="update",
            ) from exc

    # ── Domain-specific methods ─────────────────────────────────────

    async def get_by_status(
        self, status: str, *, limit: int = 50
    ) -> list[Prospect]:
        """Fetch prospects filtered by funnel status.

        Args:
            status: ProspectStatus value string.
            limit: Maximum rows to return (default 50).

        Returns:
            List of Prospect entities ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [Prospect.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_status",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by status: {exc}",
                operation="get_by_status",
            ) from exc

    async def get_follow_ups_due(self) -> list[Prospect]:
        """Fetch prospects whose follow-up is due and not yet closed.

        Returns prospects where ``follow_up_at <= now`` and status is
        not ``converted`` or ``lost``.

        Returns:
            List of Prospect entities requiring follow-up.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .lte("follow_up_at", now)
                .not_.in_("status", ["converted", "lost"])
                .order("follow_up_at")
                .execute()
            )
            return [Prospect.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_follow_ups_due",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch due follow-ups from {self.TABLE}: {exc}",
                operation="get_follow_ups_due",
            ) from exc
