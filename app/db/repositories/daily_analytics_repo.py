"""Repository for the analytics_daily aggregation table.

Provides upsert (on conflict by distributor_id+date), range queries, and
summary helpers used by the analytics services and report generators.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError
from app.db.client import get_db_client
from app.db.models.analytics import DailyAnalytics, DailyAnalyticsCreate


class DailyAnalyticsRepository:
    """Repository for analytics_daily table operations."""

    TABLE = "analytics_daily"

    # ── Upsert ──────────────────────────────────────────────────────

    async def upsert(self, data: DailyAnalyticsCreate) -> DailyAnalytics:
        """Insert or update a daily analytics row.

        Uses the UNIQUE(distributor_id, date) constraint.  If a row
        already exists for the given (distributor_id, date), all metric
        columns are overwritten.

        Args:
            data: Validated daily analytics payload.

        Returns:
            The upserted DailyAnalytics row.

        Raises:
            DatabaseError: On upsert failure.
        """
        try:
            client = get_db_client()
            payload = data.model_dump(mode="json")
            result = (
                await client.table(self.TABLE)
                .upsert(payload, on_conflict="distributor_id,date")
                .execute()
            )
            logger.debug(
                "db.analytics_daily_upserted",
                distributor_id=str(data.distributor_id),
                date=str(data.date),
            )
            return DailyAnalytics.model_validate(result.data[0])
        except Exception as exc:
            logger.error(
                "db.upsert_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to upsert {self.TABLE}: {exc}",
                operation="upsert",
            ) from exc

    # ── Read ────────────────────────────────────────────────────────

    async def get_for_date(
        self,
        distributor_id: str,
        target_date: date,
    ) -> Optional[DailyAnalytics]:
        """Get daily analytics for a specific date.

        Args:
            distributor_id: Tenant scope.
            target_date: Calendar date.

        Returns:
            DailyAnalytics or None if not yet computed.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("date", str(target_date))
                .limit(1)
                .execute()
            )
            if result.data:
                return DailyAnalytics.model_validate(result.data[0])
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_for_date",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_for_date",
            ) from exc

    async def get_range(
        self,
        distributor_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyAnalytics]:
        """Get daily analytics for a date range (inclusive).

        Args:
            distributor_id: Tenant scope.
            start_date: Range start (inclusive).
            end_date: Range end (inclusive).

        Returns:
            List of DailyAnalytics ordered by date ASC.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .gte("date", str(start_date))
                .lte("date", str(end_date))
                .order("date", desc=False)
                .execute()
            )
            return [
                DailyAnalytics.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_range",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} range: {exc}",
                operation="get_range",
            ) from exc

    async def get_latest(
        self,
        distributor_id: str,
        *,
        limit: int = 30,
    ) -> list[DailyAnalytics]:
        """Get the most recent daily analytics rows.

        Args:
            distributor_id: Tenant scope.
            limit: Maximum rows (default 30).

        Returns:
            List ordered by date DESC.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .order("date", desc=True)
                .limit(limit)
                .execute()
            )
            return [
                DailyAnalytics.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_latest",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch latest {self.TABLE}: {exc}",
                operation="get_latest",
            ) from exc


# Module-level singleton
daily_analytics_repo = DailyAnalyticsRepository()
