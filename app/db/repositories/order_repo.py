"""Order repository — all database operations for the orders table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.order import (
    Order,
    OrderCreate,
    OrderItem,
    OrderUpdate,
)


class OrderRepository:
    """Repository for orders table operations.

    All read operations require ``distributor_id`` for tenant isolation.
    """

    TABLE = "orders"
    ITEMS_TABLE = "order_items"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(
        self, id: str, *, distributor_id: str
    ) -> Optional[Order]:
        """Fetch a single order by primary key within a tenant.

        Args:
            id: UUID string of the order.
            distributor_id: Tenant scope — required.

        Returns:
            Order if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Order.model_validate(result.data)
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
        self, id: str, *, distributor_id: str
    ) -> Order:
        """Fetch a single order or raise NotFoundError.

        Args:
            id: UUID string of the order.
            distributor_id: Tenant scope — required.

        Returns:
            Order entity.

        Raises:
            NotFoundError: If no order matches the given id + tenant.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id, distributor_id=distributor_id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: OrderCreate) -> Order:
        """Insert a new order row.

        Args:
            data: Validated creation payload (must include distributor_id).

        Returns:
            The newly created Order.

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
                order_number=data.order_number,
            )
            return Order.model_validate(result.data[0])
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
        self, id: str, data: OrderUpdate, *, distributor_id: str
    ) -> Order:
        """Update an existing order.

        Args:
            id: UUID string of the order to update.
            data: Validated update payload (only non-None fields written).
            distributor_id: Tenant scope — required.

        Returns:
            The updated Order.

        Raises:
            NotFoundError: If the order does not exist within the tenant.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True, mode="json")
            if not payload:
                return await self.get_by_id_or_raise(
                    id, distributor_id=distributor_id
                )
            result = (
                await client.table(self.TABLE)
                .update(payload)
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for update",
                    operation="update",
                )
            return Order.model_validate(result.data[0])
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

    async def get_by_order_number(
        self, order_number: str
    ) -> Optional[Order]:
        """Look up an order by its human-readable order number.

        Order numbers are globally unique, so no ``distributor_id`` is
        strictly required.  However, the result still carries the
        ``distributor_id`` for downstream tenant checks.

        Args:
            order_number: The unique human-readable order number string.

        Returns:
            Order if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("order_number", order_number)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Order.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_order_number",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by order_number: {exc}",
                operation="get_by_order_number",
            ) from exc

    async def get_customer_orders(
        self,
        distributor_id: str,
        customer_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Order]:
        """Fetch orders for a specific customer, newest first.

        Args:
            distributor_id: Tenant scope.
            customer_id: UUID string of the customer.
            limit: Maximum rows to return (default 20).
            offset: Number of rows to skip (default 0).

        Returns:
            List of Order entities ordered by created_at DESC.

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
                .range(offset, offset + limit - 1)
                .execute()
            )
            return [Order.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_customer_orders",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch customer orders: {exc}",
                operation="get_customer_orders",
            ) from exc

    async def get_orders_by_status(
        self,
        distributor_id: str,
        status: str,
        *,
        limit: int = 50,
    ) -> list[Order]:
        """Fetch orders filtered by status for a distributor.

        Args:
            distributor_id: Tenant scope.
            status: Order status string to filter on.
            limit: Maximum rows to return (default 50).

        Returns:
            List of matching Order entities.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [Order.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_orders_by_status",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by status: {exc}",
                operation="get_orders_by_status",
            ) from exc

    async def get_recent_orders(
        self,
        distributor_id: str,
        *,
        hours: int = 24,
    ) -> list[Order]:
        """Fetch orders created within the last N hours.

        Args:
            distributor_id: Tenant scope.
            hours: Lookback window in hours (default 24).

        Returns:
            List of recent Order entities ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            cutoff = (
                datetime.now(tz=timezone.utc) - timedelta(hours=hours)
            ).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .execute()
            )
            return [Order.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_recent_orders",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch recent {self.TABLE}: {exc}",
                operation="get_recent_orders",
            ) from exc

    async def get_order_with_items(
        self, order_id: str, distributor_id: str
    ) -> tuple[Order, list[OrderItem]]:
        """Fetch an order together with all its line items.

        Args:
            order_id: UUID string of the order.
            distributor_id: Tenant scope.

        Returns:
            Tuple of (Order, list of OrderItem).

        Raises:
            NotFoundError: If the order does not exist within the tenant.
            DatabaseError: On query failure.
        """
        try:
            order = await self.get_by_id_or_raise(
                order_id, distributor_id=distributor_id
            )
            client = get_db_client()
            items_result = (
                await client.table(self.ITEMS_TABLE)
                .select("*")
                .eq("order_id", order_id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            items = [
                OrderItem.model_validate(row) for row in items_result.data
            ]
            return order, items
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_order_with_items",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch order with items: {exc}",
                operation="get_order_with_items",
            ) from exc
