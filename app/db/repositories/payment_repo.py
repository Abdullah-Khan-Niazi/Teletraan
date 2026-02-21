"""Payment repository — all database operations for the payments table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.payment import Payment, PaymentCreate, PaymentUpdate


class PaymentRepository:
    """Repository for payments table operations.

    Payments are linked to orders and/or distributors.  Distributor-
    scoped queries accept ``distributor_id`` for tenant isolation.
    """

    TABLE = "payments"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(self, id: str) -> Optional[Payment]:
        """Fetch a single payment by primary key.

        Args:
            id: UUID string of the payment.

        Returns:
            Payment if found, None otherwise.

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
                return Payment.model_validate(result.data)
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

    async def get_by_id_or_raise(self, id: str) -> Payment:
        """Fetch a single payment or raise NotFoundError.

        Args:
            id: UUID string of the payment.

        Returns:
            Payment entity.

        Raises:
            NotFoundError: If no payment matches the given id.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: PaymentCreate) -> Payment:
        """Insert a new payment row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created Payment.

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
                transaction_reference=data.transaction_reference,
            )
            return Payment.model_validate(result.data[0])
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

    async def update(self, id: str, data: PaymentUpdate) -> Payment:
        """Update an existing payment.

        Args:
            id: UUID string of the payment to update.
            data: Validated update payload (only non-None fields written).

        Returns:
            The updated Payment.

        Raises:
            NotFoundError: If the payment does not exist.
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
            return Payment.model_validate(result.data[0])
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

    async def get_by_transaction_reference(
        self, reference: str
    ) -> Optional[Payment]:
        """Look up a payment by its unique transaction reference.

        Args:
            reference: The transaction reference string.

        Returns:
            Payment if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("transaction_reference", reference)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Payment.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_transaction_reference",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by transaction_reference: {exc}",
                operation="get_by_transaction_reference",
            ) from exc

    async def get_by_gateway_transaction_id(
        self, gateway_txn_id: str
    ) -> Optional[Payment]:
        """Look up a payment by the gateway's own transaction ID.

        Args:
            gateway_txn_id: The ID returned by the payment gateway.

        Returns:
            Payment if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("gateway_transaction_id", gateway_txn_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Payment.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_gateway_transaction_id",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by gateway_transaction_id: {exc}",
                operation="get_by_gateway_transaction_id",
            ) from exc

    async def get_order_payments(self, order_id: str) -> list[Payment]:
        """Fetch all payments associated with an order.

        Args:
            order_id: UUID string of the order.

        Returns:
            List of Payment entities ordered by created_at DESC.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("order_id", order_id)
                .order("created_at", desc=True)
                .execute()
            )
            return [Payment.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_order_payments",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for order: {exc}",
                operation="get_order_payments",
            ) from exc

    async def get_distributor_payments(
        self,
        distributor_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Payment]:
        """Fetch payments for a distributor, optionally filtered by status.

        Args:
            distributor_id: Tenant scope.
            status: Optional status filter.
            limit: Maximum rows to return (default 50).

        Returns:
            List of Payment entities ordered by created_at DESC.

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
            if status is not None:
                query = query.eq("status", status)
            result = (
                await query
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [Payment.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_distributor_payments",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} for distributor: {exc}",
                operation="get_distributor_payments",
            ) from exc

    async def get_pending_expired(self) -> list[Payment]:
        """Fetch payments that are pending but whose link has expired.

        Returns:
            List of Payment entities with ``status='pending'`` and
            ``payment_link_expires_at`` in the past.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("status", "pending")
                .lt("payment_link_expires_at", now)
                .execute()
            )
            return [Payment.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_pending_expired",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch expired pending {self.TABLE}: {exc}",
                operation="get_pending_expired",
            ) from exc
