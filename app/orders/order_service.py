"""Order service — persist confirmed orders, manage lifecycle.

Bridges the in-memory ``OrderContext`` (from the conversation) to
the ``orders`` + ``order_items`` + ``order_status_history`` tables.

Responsibilities:
- Convert OrderContext → OrderCreate + OrderItemCreate payloads
- Generate unique order numbers (``{prefix}-{timestamp}-{rand}``)
- Insert order + items in one DB round-trip
- Record status changes in ``order_status_history``
- Update customer order stats (count, last order date)
- Stock reservation at confirmation, release on cancellation
- Lifecycle mutations: dispatch, deliver, cancel, return
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from app.core.constants import (
    OrderSource,
    OrderStatus,
    PaymentStatus,
    StatusChangeActor,
)
from app.core.exceptions import DatabaseError, NotFoundError, ValidationError
from app.db.models.order import (
    Order,
    OrderCreate,
    OrderItem,
    OrderItemCreate,
    OrderStatusHistory,
    OrderStatusHistoryCreate,
    OrderUpdate,
)
from app.db.models.order_context import OrderContext
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.customer_repo import CustomerRepository
from app.db.repositories.order_item_repo import OrderItemRepository
from app.db.repositories.order_repo import OrderRepository


# ═══════════════════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════════════════


class OrderService:
    """High-level order lifecycle service.

    Coordinates order creation, status transitions, stock changes,
    and customer stat updates.

    Args:
        order_repo: Order repository instance.
        order_item_repo: Order item repository instance.
        customer_repo: Customer repository instance.
        catalog_repo: Catalog repository for stock operations.
    """

    def __init__(
        self,
        order_repo: OrderRepository | None = None,
        order_item_repo: OrderItemRepository | None = None,
        customer_repo: CustomerRepository | None = None,
        catalog_repo: CatalogRepository | None = None,
    ) -> None:
        self._order_repo = order_repo or OrderRepository()
        self._order_item_repo = order_item_repo or OrderItemRepository()
        self._customer_repo = customer_repo or CustomerRepository()
        self._catalog_repo = catalog_repo or CatalogRepository()

    # ── Create order from context ─────────────────────────────────

    async def create_order_from_context(
        self,
        context: OrderContext,
        *,
        distributor_id: str,
        customer_id: str,
        source: OrderSource = OrderSource.WHATSAPP,
    ) -> tuple[Order, list[OrderItem]]:
        """Convert a confirmed OrderContext into a persisted order.

        Steps:
        1. Generate unique order number
        2. Insert order row
        3. Batch-insert order items
        4. Record initial status history
        5. Reserve stock for items with catalog IDs
        6. Update customer order stats

        Args:
            context: The confirmed order context.
            distributor_id: Tenant scope.
            customer_id: Customer UUID.
            source: Where the order originated.

        Returns:
            Tuple of (created Order, list of OrderItems).

        Raises:
            ValidationError: If context has no active items.
            DatabaseError: On persistence failure.
        """
        active_items = [i for i in context.items if not i.cancelled]
        if not active_items:
            raise ValidationError(
                "Cannot create order with no active items",
                field="items",
            )

        snap = context.pricing_snapshot
        order_number = _generate_order_number()

        # Build order payload
        order_create = OrderCreate(
            order_number=order_number,
            distributor_id=UUID(distributor_id),
            customer_id=UUID(customer_id),
            status=OrderStatus.PENDING,
            subtotal_paisas=snap.subtotal_paisas,
            discount_paisas=(
                snap.item_discounts_paisas + snap.order_discount_paisas
            ),
            delivery_charges_paisas=snap.delivery_charges_paisas,
            total_paisas=snap.total_paisas,
            payment_status=PaymentStatus.UNPAID,
            delivery_address=context.delivery.address,
            delivery_zone_id=(
                context.delivery.zone_id
                if context.delivery.zone_id
                else None
            ),
            notes=context.customer_notes,
            source=source,
            order_context_snapshot=context.model_dump(mode="json"),
        )

        # Insert order
        order = await self._order_repo.create(order_create)
        logger.info(
            "order_service.order_created",
            order_id=str(order.id),
            order_number=order_number,
            total=snap.total_paisas,
        )

        # Build item payloads
        item_creates = []
        for item in active_items:
            item_creates.append(OrderItemCreate(
                order_id=order.id,
                distributor_id=UUID(distributor_id),
                catalog_id=item.catalog_id,
                medicine_name_raw=item.medicine_name_raw,
                medicine_name=item.medicine_name_display or item.medicine_name_matched,
                unit=item.unit,
                quantity_ordered=item.quantity_requested,
                price_per_unit_paisas=item.price_per_unit_paisas,
                line_total_paisas=item.line_total_paisas,
                discount_paisas=item.discount_applied_paisas,
                bonus_units_given=item.bonus_units,
                is_out_of_stock_order=item.is_out_of_stock,
                is_unlisted_item=item.is_unlisted,
                input_method=item.input_method,
                fuzzy_match_score=item.fuzzy_match_score,
            ))

        # Batch insert items
        order_items = await self._order_item_repo.create_batch(item_creates)

        # Record status history
        await self._record_status_change(
            order_id=str(order.id),
            distributor_id=distributor_id,
            from_status=None,
            to_status=OrderStatus.PENDING.value,
            changed_by=StatusChangeActor.SYSTEM,
            notes="Order created from WhatsApp conversation",
        )

        # Reserve stock for items with catalog IDs
        for item in active_items:
            if item.catalog_id and not item.is_out_of_stock:
                try:
                    await self._catalog_repo.reserve_stock(
                        str(item.catalog_id),
                        item.quantity_requested,
                        distributor_id=distributor_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "order_service.stock_reserve_failed",
                        catalog_id=str(item.catalog_id),
                        error=str(exc),
                    )

        # Update customer order stats
        try:
            await self._customer_repo.update_order_stats(
                customer_id,
                distributor_id=distributor_id,
            )
        except Exception as exc:
            logger.warning(
                "order_service.customer_stats_update_failed",
                customer_id=customer_id,
                error=str(exc),
            )

        return order, order_items

    # ── Status transitions ────────────────────────────────────────

    async def confirm_order(
        self,
        order_id: str,
        distributor_id: str,
        *,
        changed_by: StatusChangeActor = StatusChangeActor.SYSTEM,
        notes: str | None = None,
    ) -> Order:
        """Move order to CONFIRMED status.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.
            changed_by: Who triggered the change.
            notes: Optional status change notes.

        Returns:
            Updated Order.
        """
        return await self._transition_status(
            order_id, distributor_id,
            allowed_from={OrderStatus.PENDING},
            new_status=OrderStatus.CONFIRMED,
            changed_by=changed_by,
            notes=notes or "Order confirmed",
        )

    async def dispatch_order(
        self,
        order_id: str,
        distributor_id: str,
        *,
        changed_by: StatusChangeActor = StatusChangeActor.DISTRIBUTOR,
        notes: str | None = None,
    ) -> Order:
        """Move order to DISPATCHED status.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.
            changed_by: Who triggered the change.
            notes: Optional notes.

        Returns:
            Updated Order.
        """
        return await self._transition_status(
            order_id, distributor_id,
            allowed_from={OrderStatus.CONFIRMED, OrderStatus.PROCESSING},
            new_status=OrderStatus.DISPATCHED,
            changed_by=changed_by,
            notes=notes or "Order dispatched",
            extra_update=OrderUpdate(
                dispatched_at=datetime.now(tz=timezone.utc),
            ),
        )

    async def deliver_order(
        self,
        order_id: str,
        distributor_id: str,
        *,
        changed_by: StatusChangeActor = StatusChangeActor.DISTRIBUTOR,
        notes: str | None = None,
    ) -> Order:
        """Move order to DELIVERED status and deduct stock.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.
            changed_by: Who triggered the change.
            notes: Optional notes.

        Returns:
            Updated Order.
        """
        order = await self._transition_status(
            order_id, distributor_id,
            allowed_from={OrderStatus.DISPATCHED},
            new_status=OrderStatus.DELIVERED,
            changed_by=changed_by,
            notes=notes or "Order delivered",
            extra_update=OrderUpdate(
                delivered_at=datetime.now(tz=timezone.utc),
            ),
        )

        # Release reserved stock and deduct actual stock
        _, items = await self._order_repo.get_order_with_items(
            order_id, distributor_id,
        )

        for item in items:
            if item.catalog_id:
                try:
                    await self._catalog_repo.release_reserved_stock(
                        str(item.catalog_id),
                        item.quantity_ordered,
                        distributor_id=distributor_id,
                    )
                    await self._catalog_repo.update_stock(
                        str(item.catalog_id),
                        -item.quantity_ordered,
                        distributor_id=distributor_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "order_service.delivery_stock_update_failed",
                        catalog_id=str(item.catalog_id),
                        error=str(exc),
                    )

        return order

    async def cancel_order(
        self,
        order_id: str,
        distributor_id: str,
        *,
        changed_by: StatusChangeActor = StatusChangeActor.CUSTOMER,
        reason: str = "Customer cancelled",
    ) -> Order:
        """Cancel an order and release reserved stock.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.
            changed_by: Who triggered the change.
            reason: Cancellation reason.

        Returns:
            Updated Order.
        """
        order = await self._transition_status(
            order_id, distributor_id,
            allowed_from={
                OrderStatus.PENDING,
                OrderStatus.CONFIRMED,
                OrderStatus.PROCESSING,
            },
            new_status=OrderStatus.CANCELLED,
            changed_by=changed_by,
            notes=reason,
        )

        # Release reserved stock
        _, items = await self._order_repo.get_order_with_items(
            order_id, distributor_id,
        )
        for item in items:
            if item.catalog_id:
                try:
                    await self._catalog_repo.release_reserved_stock(
                        str(item.catalog_id),
                        item.quantity_ordered,
                        distributor_id=distributor_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "order_service.cancel_stock_release_failed",
                        catalog_id=str(item.catalog_id),
                        error=str(exc),
                    )

        return order

    # ── Read operations ───────────────────────────────────────────

    async def get_order(
        self,
        order_id: str,
        distributor_id: str,
    ) -> Order:
        """Fetch a single order.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.

        Returns:
            Order.

        Raises:
            NotFoundError: If order not found.
        """
        return await self._order_repo.get_by_id_or_raise(
            order_id, distributor_id=distributor_id,
        )

    async def get_order_with_items(
        self,
        order_id: str,
        distributor_id: str,
    ) -> tuple[Order, list[OrderItem]]:
        """Fetch an order with its items.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.

        Returns:
            Tuple of (Order, list of OrderItem).
        """
        return await self._order_repo.get_order_with_items(
            order_id, distributor_id,
        )

    async def get_customer_orders(
        self,
        customer_id: str,
        distributor_id: str,
        *,
        status: OrderStatus | None = None,
        limit: int = 20,
    ) -> list[Order]:
        """Fetch orders for a customer.

        Args:
            customer_id: Customer UUID.
            distributor_id: Tenant scope.
            status: Optional status filter.
            limit: Max results.

        Returns:
            List of Orders, newest first.
        """
        return await self._order_repo.get_customer_orders(
            customer_id,
            distributor_id=distributor_id,
            status=status.value if status else None,
            limit=limit,
        )

    async def get_recent_orders(
        self,
        distributor_id: str,
        *,
        limit: int = 50,
    ) -> list[Order]:
        """Fetch recent orders for a distributor.

        Args:
            distributor_id: Tenant scope.
            limit: Max results.

        Returns:
            List of Orders, newest first.
        """
        return await self._order_repo.get_recent_orders(
            distributor_id, limit=limit,
        )

    async def get_order_by_number(
        self,
        order_number: str,
        distributor_id: str,
    ) -> Order | None:
        """Fetch an order by its human-readable number.

        Args:
            order_number: e.g. ``ORD-20250711-AB3F``.
            distributor_id: Tenant scope.

        Returns:
            Order or None.
        """
        return await self._order_repo.get_by_order_number(
            order_number, distributor_id=distributor_id,
        )

    # ── Fulfillment ───────────────────────────────────────────────

    async def update_item_fulfillment(
        self,
        item_id: str,
        quantity_fulfilled: int,
    ) -> OrderItem:
        """Update the fulfilled quantity for a line item.

        Args:
            item_id: UUID of the order item.
            quantity_fulfilled: Number of units actually fulfilled.

        Returns:
            Updated OrderItem.
        """
        return await self._order_item_repo.update_fulfillment(
            item_id, quantity_fulfilled,
        )

    async def check_and_update_partial_fulfillment(
        self,
        order_id: str,
        distributor_id: str,
    ) -> Order:
        """Check if all items are partially fulfilled and update status.

        If any item has ``quantity_fulfilled < quantity_ordered``,
        the order is moved to ``PARTIALLY_FULFILLED``.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.

        Returns:
            Updated Order.
        """
        _, items = await self._order_repo.get_order_with_items(
            order_id, distributor_id,
        )

        partially = any(
            item.quantity_fulfilled < item.quantity_ordered
            for item in items
        )

        if partially:
            return await self._transition_status(
                order_id, distributor_id,
                allowed_from={
                    OrderStatus.DISPATCHED,
                    OrderStatus.DELIVERED,
                },
                new_status=OrderStatus.PARTIALLY_FULFILLED,
                changed_by=StatusChangeActor.SYSTEM,
                notes="Some items partially fulfilled",
            )

        order = await self._order_repo.get_by_id_or_raise(
            order_id, distributor_id=distributor_id,
        )
        return order

    # ── Internal helpers ──────────────────────────────────────────

    async def _transition_status(
        self,
        order_id: str,
        distributor_id: str,
        *,
        allowed_from: set[OrderStatus],
        new_status: OrderStatus,
        changed_by: StatusChangeActor,
        notes: str | None = None,
        extra_update: OrderUpdate | None = None,
    ) -> Order:
        """Validate and execute an order status transition.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.
            allowed_from: Set of valid source statuses.
            new_status: Target status.
            changed_by: Actor performing the change.
            notes: Transition notes.
            extra_update: Additional fields to update.

        Returns:
            Updated Order.

        Raises:
            NotFoundError: If order not found.
            ValidationError: If transition is invalid.
        """
        order = await self._order_repo.get_by_id_or_raise(
            order_id, distributor_id=distributor_id,
        )

        if order.status not in allowed_from:
            raise ValidationError(
                f"Cannot transition from {order.status} to {new_status.value}. "
                f"Allowed from: {', '.join(s.value for s in allowed_from)}",
                field="status",
            )

        # Merge extra update fields if provided
        if extra_update:
            update_data = extra_update.model_copy()
            update_data.status = new_status
        else:
            update_data = OrderUpdate(status=new_status)

        updated_order = await self._order_repo.update(
            order_id, update_data, distributor_id=distributor_id,
        )

        # Record history
        await self._record_status_change(
            order_id=order_id,
            distributor_id=distributor_id,
            from_status=order.status.value,
            to_status=new_status.value,
            changed_by=changed_by,
            notes=notes,
        )

        logger.info(
            "order_service.status_changed",
            order_id=order_id,
            from_status=order.status.value,
            to_status=new_status.value,
            changed_by=changed_by.value,
        )

        return updated_order

    async def _record_status_change(
        self,
        *,
        order_id: str,
        distributor_id: str,
        from_status: str | None,
        to_status: str,
        changed_by: StatusChangeActor,
        notes: str | None = None,
    ) -> None:
        """Insert a row into ``order_status_history``.

        Failures are logged but not raised — status history is
        supplementary to the main order update.

        Args:
            order_id: UUID of the order.
            distributor_id: Tenant scope.
            from_status: Previous status string.
            to_status: New status string.
            changed_by: Actor.
            notes: Optional notes.
        """
        try:
            from app.db.client import get_db_client

            history = OrderStatusHistoryCreate(
                order_id=UUID(order_id),
                distributor_id=UUID(distributor_id),
                from_status=from_status,
                to_status=to_status,
                changed_by=changed_by,
                notes=notes,
            )

            client = get_db_client()
            await client.table("order_status_history").insert(
                history.model_dump(exclude_none=True, mode="json"),
            ).execute()

            logger.debug(
                "order_service.status_history_recorded",
                order_id=order_id,
                to_status=to_status,
            )
        except Exception as exc:
            logger.warning(
                "order_service.status_history_insert_failed",
                order_id=order_id,
                error=str(exc),
            )


# ═══════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


def _generate_order_number() -> str:
    """Generate a unique human-readable order number.

    Format: ``ORD-YYYYMMDD-XXXX`` where XXXX is a random hex suffix.

    Returns:
        Order number string.
    """
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(2).upper()
    return f"ORD-{today}-{suffix}"
