"""Distributor repository — all database operations for the distributors table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.distributor import (
    Distributor,
    DistributorCreate,
    DistributorUpdate,
)


class DistributorRepository:
    """Repository for distributors table operations.

    Distributors ARE the tenant — queries on this table do NOT include
    a ``distributor_id`` scope filter.  The ``id`` column itself is
    the tenant boundary for all other tables.
    """

    TABLE = "distributors"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(self, id: str) -> Optional[Distributor]:
        """Fetch a single distributor by primary key.

        Args:
            id: UUID string of the distributor.

        Returns:
            Distributor if found, None otherwise.

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
                return Distributor.model_validate(result.data)
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

    async def get_by_id_or_raise(self, id: str) -> Distributor:
        """Fetch a single distributor or raise NotFoundError.

        Args:
            id: UUID string of the distributor.

        Returns:
            Distributor entity.

        Raises:
            NotFoundError: If no distributor matches the given id.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: DistributorCreate) -> Distributor:
        """Insert a new distributor row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created Distributor.

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
            logger.info("db.record_created", table=self.TABLE)
            return Distributor.model_validate(result.data[0])
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

    async def update(self, id: str, data: DistributorUpdate) -> Distributor:
        """Update an existing distributor.

        Args:
            id: UUID string of the distributor to update.
            data: Validated update payload (only non-None fields written).

        Returns:
            The updated Distributor.

        Raises:
            NotFoundError: If the distributor does not exist.
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
            return Distributor.model_validate(result.data[0])
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

    async def get_by_whatsapp_number(
        self, whatsapp_number: str
    ) -> Optional[Distributor]:
        """Look up a distributor by their E.164 WhatsApp number.

        Args:
            whatsapp_number: E.164 formatted phone number.

        Returns:
            Distributor if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("whatsapp_number", whatsapp_number)
                .eq("is_deleted", False)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Distributor.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_whatsapp_number",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by whatsapp_number: {exc}",
                operation="get_by_whatsapp_number",
            ) from exc

    async def get_by_phone_number_id(
        self, phone_number_id: str
    ) -> Optional[Distributor]:
        """Look up a distributor by their Meta Cloud API phone-number ID.

        This is the primary lookup path for incoming webhooks — Meta
        sends ``phone_number_id`` in every message payload, and we need
        to map it to the owning distributor.

        Args:
            phone_number_id: Meta Cloud API phone_number_id string.

        Returns:
            Distributor if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("whatsapp_phone_number_id", phone_number_id)
                .eq("is_deleted", False)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Distributor.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_phone_number_id",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by phone_number_id: {exc}",
                operation="get_by_phone_number_id",
            ) from exc

    async def get_active_distributors(self) -> list[Distributor]:
        """Fetch all active, non-deleted distributors.

        Returns:
            List of active Distributor entities (may be empty).

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("is_active", True)
                .eq("is_deleted", False)
                .execute()
            )
            return [Distributor.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_active_distributors",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch active {self.TABLE}: {exc}",
                operation="get_active_distributors",
            ) from exc

    async def get_expiring_subscriptions(
        self, days_ahead: int = 7
    ) -> list[Distributor]:
        """Fetch distributors whose subscriptions expire within N days.

        Only includes distributors with ``subscription_status`` in
        ``('active', 'expiring')`` so we don't send renewal reminders to
        already-suspended or cancelled accounts.

        Args:
            days_ahead: Number of days to look ahead (default 7).

        Returns:
            List of Distributor entities with soon-expiring subscriptions.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            cutoff = (
                datetime.now(tz=timezone.utc) + timedelta(days=days_ahead)
            ).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .in_("subscription_status", ["active", "expiring"])
                .eq("is_deleted", False)
                .lte("subscription_end", cutoff)
                .execute()
            )
            return [Distributor.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_expiring_subscriptions",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch expiring subscriptions: {exc}",
                operation="get_expiring_subscriptions",
            ) from exc

    async def soft_delete(self, id: str) -> bool:
        """Soft-delete a distributor by setting is_deleted and deleted_at.

        Args:
            id: UUID string of the distributor to soft-delete.

        Returns:
            True if the row was found and updated.

        Raises:
            NotFoundError: If the distributor does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(tz=timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .update({"is_deleted": True, "deleted_at": now, "is_active": False})
                .eq("id", id)
                .eq("is_deleted", False)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found or already deleted",
                    operation="soft_delete",
                )
            logger.info("db.record_soft_deleted", table=self.TABLE, id=id)
            return True
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.soft_delete_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to soft-delete {self.TABLE}: {exc}",
                operation="soft_delete",
            ) from exc
