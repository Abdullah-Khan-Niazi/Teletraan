"""Complaint repository — all database operations for the complaints table."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.complaint import Complaint, ComplaintCreate, ComplaintUpdate


class ComplaintRepository:
    """Repository for complaints table operations.

    Complaints are tenant-scoped via ``distributor_id``.  Most reads
    accept an optional ``distributor_id`` for additional safety, but
    look-ups by globally-unique ``ticket_number`` omit it.
    """

    TABLE = "complaints"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(
        self, id: str, *, distributor_id: str | None = None
    ) -> Optional[Complaint]:
        """Fetch a single complaint by primary key.

        Args:
            id: UUID string of the complaint.
            distributor_id: Optional tenant scope for extra safety.

        Returns:
            Complaint if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            query = (
                client.table(self.TABLE)
                .select("*")
                .eq("id", id)
            )
            if distributor_id is not None:
                query = query.eq("distributor_id", distributor_id)
            result = await query.maybe_single().execute()
            if result.data:
                return Complaint.model_validate(result.data)
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

    async def get_by_id_or_raise(
        self, id: str, *, distributor_id: str | None = None
    ) -> Complaint:
        """Fetch a single complaint or raise NotFoundError.

        Args:
            id: UUID string of the complaint.
            distributor_id: Optional tenant scope.

        Returns:
            Complaint entity.

        Raises:
            NotFoundError: If no complaint matches the given id.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id, distributor_id=distributor_id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def get_by_ticket_number(
        self, ticket_number: str
    ) -> Optional[Complaint]:
        """Look up a complaint by its human-readable ticket number.

        Ticket numbers are globally unique so no ``distributor_id``
        filter is needed.

        Args:
            ticket_number: Unique ticket number string.

        Returns:
            Complaint if found, None otherwise.

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
                return Complaint.model_validate(result.data)
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

    async def create(self, data: ComplaintCreate) -> Complaint:
        """Insert a new complaint row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created Complaint.

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
            return Complaint.model_validate(result.data[0])
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
        self,
        id: str,
        data: ComplaintUpdate,
        *,
        distributor_id: str | None = None,
    ) -> Complaint:
        """Update an existing complaint.

        Args:
            id: UUID string of the complaint to update.
            data: Validated update payload (only non-None fields written).
            distributor_id: Optional tenant scope for extra safety.

        Returns:
            The updated Complaint.

        Raises:
            NotFoundError: If the complaint does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True, mode="json")
            if not payload:
                return await self.get_by_id_or_raise(
                    id, distributor_id=distributor_id
                )
            query = (
                client.table(self.TABLE)
                .update(payload)
                .eq("id", id)
            )
            if distributor_id is not None:
                query = query.eq("distributor_id", distributor_id)
            result = await query.execute()
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for update",
                    operation="update",
                )
            return Complaint.model_validate(result.data[0])
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

    async def get_open_complaints(
        self, distributor_id: str
    ) -> list[Complaint]:
        """Fetch complaints with status 'open' or 'in_progress'.

        Args:
            distributor_id: Tenant scope.

        Returns:
            List of open/in-progress Complaint entities.

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
            return [Complaint.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_open_complaints",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch open {self.TABLE}: {exc}",
                operation="get_open_complaints",
            ) from exc

    async def get_customer_complaints(
        self, distributor_id: str, customer_id: str
    ) -> list[Complaint]:
        """Fetch all complaints filed by a specific customer.

        Args:
            distributor_id: Tenant scope.
            customer_id: UUID string of the customer.

        Returns:
            List of Complaint entities ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("customer_id", customer_id)
                .order("created_at", desc=True)
                .execute()
            )
            return [Complaint.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_customer_complaints",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for customer: {exc}",
                operation="get_customer_complaints",
            ) from exc
