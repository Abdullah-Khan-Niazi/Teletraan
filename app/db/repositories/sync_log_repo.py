"""Inventory sync log repository — database operations for inventory_sync_log."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.audit import (
    InventorySyncLog,
    InventorySyncLogCreate,
    InventorySyncLogUpdate,
)


class InventorySyncLogRepository:
    """Repository for inventory_sync_log table operations.

    Tracks every inventory sync attempt: source file, row counts,
    errors, and completion status.
    """

    TABLE = "inventory_sync_log"

    # ── Write ───────────────────────────────────────────────────────

    async def create(self, data: InventorySyncLogCreate) -> InventorySyncLog:
        """Insert a new sync log entry at the start of a sync operation.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created InventorySyncLog.

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
                distributor_id=str(data.distributor_id),
                sync_source=data.sync_source.value if data.sync_source else None,
            )
            return InventorySyncLog.model_validate(result.data[0])
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
        self, id: str, data: InventorySyncLogUpdate
    ) -> InventorySyncLog:
        """Update a sync log entry (typically on completion or failure).

        Args:
            id: UUID string of the sync log entry.
            data: Validated update payload (only non-None fields written).

        Returns:
            The updated InventorySyncLog.

        Raises:
            NotFoundError: If the sync log entry does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True, mode="json")
            if not payload:
                return await self.get_by_id(id)  # type: ignore[return-value]
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
            return InventorySyncLog.model_validate(result.data[0])
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

    # ── Read ────────────────────────────────────────────────────────

    async def get_by_id(self, id: str) -> Optional[InventorySyncLog]:
        """Fetch a single sync log entry by primary key.

        Args:
            id: UUID string of the sync log entry.

        Returns:
            InventorySyncLog if found, None otherwise.

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
                return InventorySyncLog.model_validate(result.data)
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

    async def get_latest_for_distributor(
        self, distributor_id: str, *, limit: int = 10
    ) -> list[InventorySyncLog]:
        """Fetch the most recent sync log entries for a distributor.

        Args:
            distributor_id: Tenant scope.
            limit: Maximum rows to return (default 10).

        Returns:
            List of InventorySyncLog entries ordered by started_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .order("started_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [
                InventorySyncLog.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_latest_for_distributor",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for distributor: {exc}",
                operation="get_latest_for_distributor",
            ) from exc

    async def get_last_successful_sync(
        self, distributor_id: str
    ) -> Optional[InventorySyncLog]:
        """Fetch the most recent successful (completed) sync for a distributor.

        Args:
            distributor_id: Tenant scope.

        Returns:
            InventorySyncLog if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("status", "completed")
                .order("completed_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if result.data:
                return InventorySyncLog.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_last_successful_sync",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch last successful {self.TABLE}: {exc}",
                operation="get_last_successful_sync",
            ) from exc
