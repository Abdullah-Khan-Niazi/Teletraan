"""Audit log repository — all database operations for the audit_log table."""

from __future__ import annotations

from loguru import logger

from app.core.exceptions import DatabaseError
from app.db.client import get_db_client
from app.db.models.audit import AuditLog, AuditLogCreate


class AuditRepository:
    """Repository for audit_log table operations.

    The audit log is **immutable** — rows are only ever inserted and
    read.  There are no update or delete methods by design.
    """

    TABLE = "audit_log"

    # ── Write ───────────────────────────────────────────────────────

    async def create(self, data: AuditLogCreate) -> AuditLog:
        """Insert a new audit log entry.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created AuditLog.

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
                action=data.action,
            )
            return AuditLog.model_validate(result.data[0])
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

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: str,
        *,
        limit: int = 50,
    ) -> list[AuditLog]:
        """Fetch audit history for a specific entity.

        Args:
            entity_type: Type string (e.g. ``'order'``, ``'customer'``).
            entity_id: UUID string of the entity.
            limit: Maximum rows to return (default 50).

        Returns:
            List of AuditLog entries ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("entity_type", entity_type)
                .eq("entity_id", entity_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [AuditLog.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_entity_history",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for entity: {exc}",
                operation="get_entity_history",
            ) from exc

    async def get_distributor_audit(
        self,
        distributor_id: str,
        *,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Fetch audit entries for a distributor's tenant.

        Args:
            distributor_id: Tenant scope.
            limit: Maximum rows to return (default 100).

        Returns:
            List of AuditLog entries ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [AuditLog.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_distributor_audit",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for distributor: {exc}",
                operation="get_distributor_audit",
            ) from exc
