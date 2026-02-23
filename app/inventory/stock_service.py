"""Stock management service — level checks, low-stock detection, and alerts.

Provides stock-level intelligence on top of the catalog:

- **Stock availability checks** at order time.
- **is_in_stock flag maintenance** after catalog mutations.
- **Low-stock detection** with WhatsApp alerts to the distributor owner.
- **Batch stock refresh** post-sync to derive is_in_stock flags.

All alerts use ``WhatsAppNotifier.notify_owner()`` with the
``OWNER_LOW_STOCK`` template.
"""

from __future__ import annotations

from loguru import logger

from app.db.models.catalog import CatalogItem
from app.db.repositories import catalog_repo, distributor_repo
from app.notifications.whatsapp_notifier import whatsapp_notifier


# ═══════════════════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════════════════


class StockService:
    """Business-layer service for stock-level operations.

    Wraps the catalog repository with stock intelligence: availability
    checks, is_in_stock maintenance, low-stock detection, and owner
    alerts via WhatsApp.
    """

    # ── Stock Availability ──────────────────────────────────────────

    async def check_availability(
        self,
        distributor_id: str,
        item_id: str,
        requested_quantity: int,
    ) -> tuple[bool, int]:
        """Check whether sufficient stock is available for an order line.

        Available stock = stock_quantity − reserved_quantity.

        Args:
            distributor_id: Tenant UUID string.
            item_id: Catalog item UUID string.
            requested_quantity: Units the customer wants.

        Returns:
            Tuple of (is_available, available_quantity).
            ``is_available`` is True when available >= requested.

        Raises:
            NotFoundError: If the catalog item does not exist.
            DatabaseError: On query failure.
        """
        item = await catalog_repo.get_by_id_or_raise(
            item_id, distributor_id=distributor_id
        )
        available = max(0, item.stock_quantity - item.reserved_quantity)
        is_available = available >= requested_quantity

        logger.debug(
            "stock.availability_checked",
            item_id=item_id,
            requested=requested_quantity,
            available=available,
            is_available=is_available,
        )
        return is_available, available

    async def can_fulfil_order(
        self,
        distributor_id: str,
        item_id: str,
        quantity: int,
    ) -> bool:
        """Quick boolean check: can this order line be fulfilled?

        Also considers ``allow_order_when_out_of_stock`` — if True,
        the order is always allowed regardless of stock level.

        Args:
            distributor_id: Tenant UUID string.
            item_id: Catalog item UUID string.
            quantity: Units requested.

        Returns:
            True if the order line can proceed.

        Raises:
            NotFoundError: If the catalog item does not exist.
            DatabaseError: On query failure.
        """
        item = await catalog_repo.get_by_id_or_raise(
            item_id, distributor_id=distributor_id
        )
        if item.allow_order_when_out_of_stock:
            return True

        available = max(0, item.stock_quantity - item.reserved_quantity)
        return available >= quantity

    # ── is_in_stock Maintenance ─────────────────────────────────────

    async def refresh_in_stock_flags(
        self, distributor_id: str
    ) -> tuple[int, int]:
        """Recalculate and persist ``is_in_stock`` for every active item.

        Intended to run after an inventory sync to ensure the boolean
        flag accurately reflects the current stock_quantity.

        Args:
            distributor_id: Tenant UUID string.

        Returns:
            Tuple of (items_set_in_stock, items_set_out_of_stock).

        Raises:
            DatabaseError: On query failure.
        """
        items = await catalog_repo.get_active_catalog(distributor_id)

        set_in_stock = 0
        set_out_of_stock = 0

        for item in items:
            should_be_in_stock = item.stock_quantity > 0
            if item.is_in_stock != should_be_in_stock:
                await catalog_repo.update_stock(
                    str(item.id),
                    distributor_id,
                    item.stock_quantity,
                )
                if should_be_in_stock:
                    set_in_stock += 1
                else:
                    set_out_of_stock += 1

        logger.info(
            "stock.in_stock_flags_refreshed",
            distributor_id=distributor_id,
            set_in_stock=set_in_stock,
            set_out_of_stock=set_out_of_stock,
        )
        return set_in_stock, set_out_of_stock

    # ── Low-Stock Detection ─────────────────────────────────────────

    async def get_low_stock_items(
        self, distributor_id: str
    ) -> list[CatalogItem]:
        """Fetch all items at or below their low-stock threshold.

        Args:
            distributor_id: Tenant UUID string.

        Returns:
            List of low-stock CatalogItem entities.

        Raises:
            DatabaseError: On query failure.
        """
        return await catalog_repo.get_low_stock_items(distributor_id)

    async def detect_and_alert_low_stock(
        self, distributor_id: str
    ) -> int:
        """Detect low-stock items and send a WhatsApp alert for each.

        Sends one ``OWNER_LOW_STOCK`` message per low-stock item to the
        system owner.  Returns the number of alerts sent.

        Args:
            distributor_id: Tenant UUID string.

        Returns:
            Number of low-stock alerts dispatched.
        """
        low_stock_items = await self.get_low_stock_items(distributor_id)
        if not low_stock_items:
            logger.debug(
                "stock.no_low_stock_items",
                distributor_id=distributor_id,
            )
            return 0

        alerts_sent = 0
        for item in low_stock_items:
            try:
                await whatsapp_notifier.notify_owner(
                    template_key="OWNER_LOW_STOCK",
                    template_kwargs={
                        "medicine_name": item.medicine_name,
                        "quantity": item.stock_quantity,
                        "unit": item.unit or "units",
                        "threshold": item.low_stock_threshold,
                    },
                    distributor_id=distributor_id,
                    notification_type="low_stock_alert",
                )
                alerts_sent += 1
            except Exception as exc:
                logger.error(
                    "stock.low_stock_alert_failed",
                    item_id=str(item.id),
                    medicine_name=item.medicine_name,
                    error=str(exc),
                )
                # Continue sending alerts for other items
                continue

        logger.info(
            "stock.low_stock_alerts_sent",
            distributor_id=distributor_id,
            low_stock_count=len(low_stock_items),
            alerts_sent=alerts_sent,
        )
        return alerts_sent

    # ── Post-Sync Pipeline ──────────────────────────────────────────

    async def post_sync_stock_check(
        self, distributor_id: str
    ) -> dict[str, int]:
        """Full post-sync stock maintenance pipeline.

        Called after a successful inventory sync:
        1. Refresh ``is_in_stock`` flags.
        2. Detect low-stock items and send alerts.

        Args:
            distributor_id: Tenant UUID string.

        Returns:
            Dict with keys: set_in_stock, set_out_of_stock, alerts_sent.
        """
        logger.info(
            "stock.post_sync_check.start",
            distributor_id=distributor_id,
        )

        in_stock, out_of_stock = await self.refresh_in_stock_flags(
            distributor_id
        )
        alerts_sent = await self.detect_and_alert_low_stock(
            distributor_id
        )

        logger.info(
            "stock.post_sync_check.complete",
            distributor_id=distributor_id,
            set_in_stock=in_stock,
            set_out_of_stock=out_of_stock,
            alerts_sent=alerts_sent,
        )

        return {
            "set_in_stock": in_stock,
            "set_out_of_stock": out_of_stock,
            "alerts_sent": alerts_sent,
        }

    # ── Summary ─────────────────────────────────────────────────────

    async def get_stock_summary(
        self, distributor_id: str
    ) -> dict[str, int]:
        """Get a quick stock summary for a distributor.

        Args:
            distributor_id: Tenant UUID string.

        Returns:
            Dict with keys: total_items, in_stock, out_of_stock,
            low_stock, total_stock_units.

        Raises:
            DatabaseError: On query failure.
        """
        all_items = await catalog_repo.get_active_catalog(distributor_id)
        low_items = [
            i for i in all_items
            if i.stock_quantity <= i.low_stock_threshold
        ]

        in_stock = sum(1 for i in all_items if i.is_in_stock)
        out_of_stock = len(all_items) - in_stock
        total_stock_units = sum(i.stock_quantity for i in all_items)

        return {
            "total_items": len(all_items),
            "in_stock": in_stock,
            "out_of_stock": out_of_stock,
            "low_stock": len(low_items),
            "total_stock_units": total_stock_units,
        }


# ── Module-level singleton ──────────────────────────────────────────

stock_service = StockService()
