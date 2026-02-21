"""Analytics repository — all database operations for the analytics_events table."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError
from app.db.client import get_db_client
from app.db.models.audit import AnalyticsEvent, AnalyticsEventCreate


class AnalyticsRepository:
    """Repository for analytics_events table operations.

    Analytics events are append-only.  There is no update or delete —
    events are written once and read for reporting.
    """

    TABLE = "analytics_events"

    # ── Write ───────────────────────────────────────────────────────

    async def create(self, data: AnalyticsEventCreate) -> AnalyticsEvent:
        """Insert a new analytics event row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created AnalyticsEvent.

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
                event_type=data.event_type,
            )
            return AnalyticsEvent.model_validate(result.data[0])
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

    async def get_distributor_events(
        self,
        distributor_id: str,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AnalyticsEvent]:
        """Fetch analytics events for a distributor.

        Args:
            distributor_id: Tenant scope.
            event_type: Optional filter by event type.
            limit: Maximum rows to return (default 100).

        Returns:
            List of AnalyticsEvent entities ordered by occurred_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            query = (
                client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
            )
            if event_type is not None:
                query = query.eq("event_type", event_type)
            result = (
                await query
                .order("occurred_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [
                AnalyticsEvent.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_distributor_events",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for distributor: {exc}",
                operation="get_distributor_events",
            ) from exc

    async def get_events_in_range(
        self,
        distributor_id: str,
        start: str,
        end: str,
    ) -> list[AnalyticsEvent]:
        """Fetch analytics events within a time range.

        Args:
            distributor_id: Tenant scope.
            start: ISO 8601 start timestamp (inclusive).
            end: ISO 8601 end timestamp (inclusive).

        Returns:
            List of AnalyticsEvent entities ordered by occurred_at ASC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .gte("occurred_at", start)
                .lte("occurred_at", end)
                .order("occurred_at")
                .execute()
            )
            return [
                AnalyticsEvent.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_events_in_range",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} in range: {exc}",
                operation="get_events_in_range",
            ) from exc
