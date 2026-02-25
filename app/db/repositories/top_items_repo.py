"""Repository for analytics_top_items and analytics_customer_events tables.

Provides batch insert and query methods for product rankings and
customer lifecycle event tracking.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError
from app.db.client import get_db_client
from app.db.models.analytics import (
    CustomerEvent,
    CustomerEventCreate,
    TopItem,
    TopItemCreate,
)


# ═══════════════════════════════════════════════════════════════════
# TOP ITEMS REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class TopItemRepository:
    """Repository for analytics_top_items table operations."""

    TABLE = "analytics_top_items"

    async def replace_for_date(
        self,
        distributor_id: str,
        target_date: date,
        items: list[TopItemCreate],
    ) -> list[TopItem]:
        """Replace all top items for a given date.

        Deletes existing rows for (distributor_id, date) then inserts
        the new batch.  This is idempotent — re-running for the same
        date simply replaces the data.

        Args:
            distributor_id: Tenant scope.
            target_date: Calendar date.
            items: New top item rows.

        Returns:
            The newly inserted TopItem rows.

        Raises:
            DatabaseError: On failure.
        """
        try:
            client = get_db_client()
            # Delete existing rows for this date
            await (
                client.table(self.TABLE)
                .delete()
                .eq("distributor_id", distributor_id)
                .eq("date", str(target_date))
                .execute()
            )
            if not items:
                return []

            payloads = [
                item.model_dump(mode="json") for item in items
            ]
            result = (
                await client.table(self.TABLE)
                .insert(payloads)
                .execute()
            )
            logger.debug(
                "db.top_items_replaced",
                distributor_id=distributor_id,
                date=str(target_date),
                count=len(items),
            )
            return [TopItem.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.replace_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to replace {self.TABLE}: {exc}",
                operation="replace_for_date",
            ) from exc

    async def get_for_date(
        self,
        distributor_id: str,
        target_date: date,
        *,
        limit: int = 10,
    ) -> list[TopItem]:
        """Get top items for a specific date.

        Args:
            distributor_id: Tenant scope.
            target_date: Calendar date.
            limit: Maximum items (default 10).

        Returns:
            List of TopItem ordered by revenue_paisas DESC.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("date", str(target_date))
                .order("revenue_paisas", desc=True)
                .limit(limit)
                .execute()
            )
            return [TopItem.model_validate(row) for row in result.data]
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
        *,
        limit: int = 10,
    ) -> list[TopItem]:
        """Get aggregated top items across a date range.

        Returns raw rows; callers aggregate as needed.

        Args:
            distributor_id: Tenant scope.
            start_date: Range start (inclusive).
            end_date: Range end (inclusive).
            limit: Max rows per date.

        Returns:
            List of TopItem rows.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .gte("date", str(start_date))
                .lte("date", str(end_date))
                .order("revenue_paisas", desc=True)
                .limit(limit * ((end_date - start_date).days + 1))
                .execute()
            )
            return [TopItem.model_validate(row) for row in result.data]
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


# ═══════════════════════════════════════════════════════════════════
# CUSTOMER EVENTS REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class CustomerEventRepository:
    """Repository for analytics_customer_events table operations."""

    TABLE = "analytics_customer_events"

    async def create(self, data: CustomerEventCreate) -> CustomerEvent:
        """Insert a customer lifecycle event.

        Args:
            data: Validated event payload.

        Returns:
            The newly created CustomerEvent.

        Raises:
            DatabaseError: On insert failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .insert(data.model_dump(mode="json"))
                .execute()
            )
            logger.debug(
                "db.customer_event_created",
                event_type=data.event_type,
                customer_id=str(data.customer_id),
            )
            return CustomerEvent.model_validate(result.data[0])
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

    async def get_by_customer(
        self,
        distributor_id: str,
        customer_id: str,
        *,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[CustomerEvent]:
        """Get events for a specific customer.

        Args:
            distributor_id: Tenant scope.
            customer_id: Customer UUID.
            event_type: Optional filter.
            limit: Maximum rows.

        Returns:
            List of CustomerEvent ordered by occurred_at DESC.
        """
        try:
            client = get_db_client()
            query = (
                client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("customer_id", customer_id)
            )
            if event_type:
                query = query.eq("event_type", event_type)
            result = (
                await query
                .order("occurred_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [
                CustomerEvent.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_customer",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_by_customer",
            ) from exc

    async def get_by_type(
        self,
        distributor_id: str,
        event_type: str,
        *,
        limit: int = 100,
    ) -> list[CustomerEvent]:
        """Get events of a specific type across all customers.

        Args:
            distributor_id: Tenant scope.
            event_type: Event type filter.
            limit: Maximum rows.

        Returns:
            List of CustomerEvent ordered by occurred_at DESC.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("event_type", event_type)
                .order("occurred_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [
                CustomerEvent.model_validate(row) for row in result.data
            ]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_type",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_by_type",
            ) from exc


# Module-level singletons
top_item_repo = TopItemRepository()
customer_event_repo = CustomerEventRepository()
