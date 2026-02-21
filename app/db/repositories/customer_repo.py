"""Customer repository — all database operations for the customers table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.customer import Customer, CustomerCreate, CustomerUpdate


class CustomerRepository:
    """Repository for customers table operations.

    All read operations require ``distributor_id`` for tenant isolation.
    """

    TABLE = "customers"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(
        self, id: str, *, distributor_id: str
    ) -> Optional[Customer]:
        """Fetch a single customer by primary key within a tenant.

        Args:
            id: UUID string of the customer.
            distributor_id: Tenant scope — required.

        Returns:
            Customer if found, None otherwise.

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
                return Customer.model_validate(result.data)
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
    ) -> Customer:
        """Fetch a single customer or raise NotFoundError.

        Args:
            id: UUID string of the customer.
            distributor_id: Tenant scope — required.

        Returns:
            Customer entity.

        Raises:
            NotFoundError: If no customer matches the given id + tenant.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id, distributor_id=distributor_id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: CustomerCreate) -> Customer:
        """Insert a new customer row.

        Args:
            data: Validated creation payload (must include distributor_id).

        Returns:
            The newly created Customer.

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
            )
            return Customer.model_validate(result.data[0])
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
        self, id: str, data: CustomerUpdate, *, distributor_id: str
    ) -> Customer:
        """Update an existing customer.

        Args:
            id: UUID string of the customer to update.
            data: Validated update payload (only non-None fields written).
            distributor_id: Tenant scope — required.

        Returns:
            The updated Customer.

        Raises:
            NotFoundError: If the customer does not exist within the tenant.
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
            return Customer.model_validate(result.data[0])
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
        self, distributor_id: str, whatsapp_number: str
    ) -> Optional[Customer]:
        """Look up a customer by distributor + WhatsApp number.

        This is the main identification path when a retailer sends a
        message — we match the sender's phone to a known customer
        within the distributor's tenant.

        Args:
            distributor_id: Tenant scope.
            whatsapp_number: E.164 formatted phone number.

        Returns:
            Customer if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("whatsapp_number", whatsapp_number)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Customer.model_validate(result.data)
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

    async def get_active_customers(
        self,
        distributor_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Customer]:
        """Fetch paginated active customers for a distributor.

        Args:
            distributor_id: Tenant scope.
            limit: Maximum rows to return (default 100).
            offset: Number of rows to skip (default 0).

        Returns:
            List of active Customer entities (may be empty).

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("is_active", True)
                .eq("is_blocked", False)
                .order("name")
                .range(offset, offset + limit - 1)
                .execute()
            )
            return [Customer.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_active_customers",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch active {self.TABLE}: {exc}",
                operation="get_active_customers",
            ) from exc

    async def search_by_name(
        self,
        distributor_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[Customer]:
        """Search customers by name or shop_name using case-insensitive LIKE.

        Args:
            distributor_id: Tenant scope.
            query: Partial name to search for.
            limit: Maximum results to return (default 20).

        Returns:
            List of matching Customer entities.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            pattern = f"%{query}%"
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("is_active", True)
                .or_(f"name.ilike.{pattern},shop_name.ilike.{pattern}")
                .limit(limit)
                .execute()
            )
            return [Customer.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="search_by_name",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to search {self.TABLE} by name: {exc}",
                operation="search_by_name",
            ) from exc

    async def update_order_stats(
        self,
        id: str,
        distributor_id: str,
        total_paisas: int,
    ) -> None:
        """Increment order count and lifetime spend after a confirmed order.

        Uses a read-then-write pattern to safely increment counters
        and update ``last_order_at`` to the current UTC timestamp.

        Args:
            id: UUID string of the customer.
            distributor_id: Tenant scope.
            total_paisas: Order total in paisas to add to lifetime spend.

        Raises:
            NotFoundError: If the customer does not exist within the tenant.
            DatabaseError: On query / update failure.
        """
        try:
            customer = await self.get_by_id_or_raise(
                id, distributor_id=distributor_id
            )
            client = get_db_client()
            now = datetime.now(tz=timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .update(
                    {
                        "total_orders": customer.total_orders + 1,
                        "total_spend_paisas": (
                            customer.total_spend_paisas + total_paisas
                        ),
                        "last_order_at": now,
                    }
                )
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for stats update",
                    operation="update_order_stats",
                )
            logger.info(
                "db.order_stats_updated",
                table=self.TABLE,
                customer_id=id,
                new_total_orders=customer.total_orders + 1,
            )
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="update_order_stats",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update order stats for {self.TABLE}: {exc}",
                operation="update_order_stats",
            ) from exc

    async def block_customer(
        self, id: str, distributor_id: str, reason: str
    ) -> Customer:
        """Block a customer with a recorded reason and timestamp.

        Args:
            id: UUID string of the customer.
            distributor_id: Tenant scope.
            reason: Human-readable reason for blocking.

        Returns:
            The updated (blocked) Customer.

        Raises:
            NotFoundError: If the customer does not exist within the tenant.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(tz=timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .update(
                    {
                        "is_blocked": True,
                        "blocked_reason": reason,
                        "blocked_at": now,
                    }
                )
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for blocking",
                    operation="block_customer",
                )
            logger.info(
                "db.customer_blocked",
                table=self.TABLE,
                customer_id=id,
                reason=reason,
            )
            return Customer.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="block_customer",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to block {self.TABLE}: {exc}",
                operation="block_customer",
            ) from exc

    async def unblock_customer(
        self, id: str, distributor_id: str
    ) -> Customer:
        """Remove the block from a customer.

        Clears ``is_blocked``, ``blocked_reason``, and ``blocked_at``.

        Args:
            id: UUID string of the customer.
            distributor_id: Tenant scope.

        Returns:
            The updated (unblocked) Customer.

        Raises:
            NotFoundError: If the customer does not exist within the tenant.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update(
                    {
                        "is_blocked": False,
                        "blocked_reason": None,
                        "blocked_at": None,
                    }
                )
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for unblocking",
                    operation="unblock_customer",
                )
            logger.info(
                "db.customer_unblocked",
                table=self.TABLE,
                customer_id=id,
            )
            return Customer.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="unblock_customer",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to unblock {self.TABLE}: {exc}",
                operation="unblock_customer",
            ) from exc
