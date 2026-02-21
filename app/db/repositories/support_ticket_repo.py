"""Support ticket repository — all database operations for the support_tickets table."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.support_ticket import (
    SupportTicket,
    SupportTicketCreate,
    SupportTicketUpdate,
)


class SupportTicketRepository:
    """Repository for support_tickets table operations.

    Support tickets are filed by distributors (not retailers) and
    handled by the TELETRAAN owner.  Most reads are scoped by
    ``distributor_id``; the owner view (``get_all_open_tickets``) is
    unscoped.
    """

    TABLE = "support_tickets"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(self, id: str) -> Optional[SupportTicket]:
        """Fetch a single support ticket by primary key.

        Args:
            id: UUID string of the support ticket.

        Returns:
            SupportTicket if found, None otherwise.

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
                return SupportTicket.model_validate(result.data)
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

    async def get_by_id_or_raise(self, id: str) -> SupportTicket:
        """Fetch a single support ticket or raise NotFoundError.

        Args:
            id: UUID string of the support ticket.

        Returns:
            SupportTicket entity.

        Raises:
            NotFoundError: If no ticket matches the given id.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def get_by_ticket_number(
        self, ticket_number: str
    ) -> Optional[SupportTicket]:
        """Look up a support ticket by its human-readable ticket number.

        Ticket numbers are globally unique so no ``distributor_id``
        filter is needed.

        Args:
            ticket_number: Unique ticket number string.

        Returns:
            SupportTicket if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("ticket_number", ticket_number)
                .maybe_single()
                .execute()
            )
            if result.data:
                return SupportTicket.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_ticket_number",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by ticket_number: {exc}",
                operation="get_by_ticket_number",
            ) from exc

    async def create(self, data: SupportTicketCreate) -> SupportTicket:
        """Insert a new support ticket row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created SupportTicket.

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
                ticket_number=data.ticket_number,
            )
            return SupportTicket.model_validate(result.data[0])
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

    async def update(
        self, id: str, data: SupportTicketUpdate
    ) -> SupportTicket:
        """Update an existing support ticket.

        Args:
            id: UUID string of the support ticket to update.
            data: Validated update payload (only non-None fields written).

        Returns:
            The updated SupportTicket.

        Raises:
            NotFoundError: If the ticket does not exist.
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
            return SupportTicket.model_validate(result.data[0])
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

    async def get_open_tickets(
        self, distributor_id: str
    ) -> list[SupportTicket]:
        """Fetch open/in-progress tickets for a specific distributor.

        Args:
            distributor_id: Tenant scope.

        Returns:
            List of open SupportTicket entities ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .in_("status", ["open", "in_progress"])
                .order("created_at", desc=True)
                .execute()
            )
            return [
                SupportTicket.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_open_tickets",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch open {self.TABLE}: {exc}",
                operation="get_open_tickets",
            ) from exc

    async def get_all_open_tickets(self) -> list[SupportTicket]:
        """Fetch all open/in-progress tickets across all distributors.

        This is the TELETRAAN owner's view — no tenant scope.

        Returns:
            List of open SupportTicket entities ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .in_("status", ["open", "in_progress"])
                .order("created_at", desc=True)
                .execute()
            )
            return [
                SupportTicket.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_all_open_tickets",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch all open {self.TABLE}: {exc}",
                operation="get_all_open_tickets",
            ) from exc
