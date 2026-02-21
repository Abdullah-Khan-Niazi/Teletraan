"""Order-item repository — all database operations for the order_items table."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.order import OrderItem, OrderItemCreate


class OrderItemRepository:
    """Repository for order_items table operations.

    All read operations require ``distributor_id`` for tenant isolation.
    Order items are immutable after creation — there is no general
    ``OrderItemUpdate`` model.  The only mutable field is
    ``quantity_fulfilled``, exposed via ``update_fulfillment()``.
    """

    TABLE = "order_items"

    # ── Standard reads ──────────────────────────────────────────────

    async def get_by_id(
        self, id: str, *, distributor_id: str
    ) -> Optional[OrderItem]:
        """Fetch a single order item by primary key within a tenant.

        Args:
            id: UUID string of the order item.
            distributor_id: Tenant scope — required.

        Returns:
            OrderItem if found, None otherwise.

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
                return OrderItem.model_validate(result.data)
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
    ) -> OrderItem:
        """Fetch a single order item or raise NotFoundError.

        Args:
            id: UUID string of the order item.
            distributor_id: Tenant scope — required.

        Returns:
            OrderItem entity.

        Raises:
            NotFoundError: If no order item matches the given id + tenant.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id, distributor_id=distributor_id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: OrderItemCreate) -> OrderItem:
        """Insert a single order item row.

        Args:
            data: Validated creation payload (includes distributor_id).

        Returns:
            The newly created OrderItem.

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
                order_id=str(data.order_id),
            )
            return OrderItem.model_validate(result.data[0])
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

    # ── Domain-specific methods ─────────────────────────────────────

    async def get_by_order(
        self, order_id: str, distributor_id: str
    ) -> list[OrderItem]:
        """Fetch all line items belonging to an order.

        Args:
            order_id: UUID string of the parent order.
            distributor_id: Tenant scope.

        Returns:
            List of OrderItem entities (may be empty).

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("order_id", order_id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            return [OrderItem.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_order",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by order: {exc}",
                operation="get_by_order",
            ) from exc

    async def create_batch(
        self, items: list[OrderItemCreate]
    ) -> list[OrderItem]:
        """Bulk-insert multiple order items in a single round-trip.

        Args:
            items: List of validated creation payloads.

        Returns:
            List of newly created OrderItem entities.

        Raises:
            DatabaseError: On insert failure.
        """
        if not items:
            return []
        try:
            client = get_db_client()
            payloads = [
                item.model_dump(exclude_none=True, mode="json")
                for item in items
            ]
            result = (
                await client.table(self.TABLE).insert(payloads).execute()
            )
            logger.info(
                "db.batch_created",
                table=self.TABLE,
                count=len(result.data),
            )
            return [OrderItem.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.batch_insert_failed",
                table=self.TABLE,
                count=len(items),
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to batch-create {self.TABLE}: {exc}",
                operation="create_batch",
            ) from exc

    async def update_fulfillment(
        self, id: str, quantity_fulfilled: int
    ) -> OrderItem:
        """Update the fulfilled quantity for an order item.

        This is the only mutation allowed on order items after creation.
        The caller (order service) is responsible for validating that
        ``quantity_fulfilled <= quantity_ordered``.

        Args:
            id: UUID string of the order item.
            quantity_fulfilled: Updated fulfilled count.

        Returns:
            The updated OrderItem.

        Raises:
            NotFoundError: If the order item does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update({"quantity_fulfilled": quantity_fulfilled})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for fulfillment update",
                    operation="update_fulfillment",
                )
            logger.info(
                "db.fulfillment_updated",
                table=self.TABLE,
                item_id=id,
                quantity_fulfilled=quantity_fulfilled,
            )
            return OrderItem.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="update_fulfillment",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update fulfillment for {self.TABLE}: {exc}",
                operation="update_fulfillment",
            ) from exc
