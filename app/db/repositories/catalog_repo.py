"""Catalog repository — all database operations for the catalog table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.catalog import CatalogItem, CatalogItemCreate, CatalogItemUpdate


class CatalogRepository:
    """Repository for catalog table operations.

    All read operations require ``distributor_id`` for tenant isolation.
    """

    TABLE = "catalog"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(
        self, id: str, *, distributor_id: str
    ) -> Optional[CatalogItem]:
        """Fetch a single catalog item by primary key within a tenant.

        Args:
            id: UUID string of the catalog item.
            distributor_id: Tenant scope — required.

        Returns:
            CatalogItem if found, None otherwise.

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
                return CatalogItem.model_validate(result.data)
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
    ) -> CatalogItem:
        """Fetch a single catalog item or raise NotFoundError.

        Args:
            id: UUID string of the catalog item.
            distributor_id: Tenant scope — required.

        Returns:
            CatalogItem entity.

        Raises:
            NotFoundError: If no catalog item matches the given id + tenant.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id, distributor_id=distributor_id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: CatalogItemCreate) -> CatalogItem:
        """Insert a new catalog item row.

        Args:
            data: Validated creation payload (includes distributor_id).

        Returns:
            The newly created CatalogItem.

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
                medicine_name=data.medicine_name,
            )
            return CatalogItem.model_validate(result.data[0])
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
        self, id: str, data: CatalogItemUpdate, *, distributor_id: str
    ) -> CatalogItem:
        """Update an existing catalog item.

        Args:
            id: UUID string of the catalog item to update.
            data: Validated update payload (only non-None fields written).
            distributor_id: Tenant scope — required.

        Returns:
            The updated CatalogItem.

        Raises:
            NotFoundError: If the catalog item does not exist.
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
            return CatalogItem.model_validate(result.data[0])
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

    async def get_active_catalog(
        self, distributor_id: str
    ) -> list[CatalogItem]:
        """Fetch all active, non-deleted catalog items for a distributor.

        Args:
            distributor_id: Tenant scope.

        Returns:
            List of active CatalogItem entities (may be empty).

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
                .eq("is_deleted", False)
                .order("medicine_name")
                .execute()
            )
            return [CatalogItem.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_active_catalog",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch active {self.TABLE}: {exc}",
                operation="get_active_catalog",
            ) from exc

    async def search_medicines(
        self,
        distributor_id: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[CatalogItem]:
        """Search medicines by name, generic name, brand, or keywords.

        Performs a case-insensitive LIKE search across
        ``medicine_name``, ``generic_name``, ``brand_name``, and the
        text representation of ``search_keywords``.

        Args:
            distributor_id: Tenant scope.
            query: Partial search string.
            limit: Maximum results to return (default 10).

        Returns:
            List of matching CatalogItem entities.

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
                .eq("is_deleted", False)
                .or_(
                    f"medicine_name.ilike.{pattern},"
                    f"generic_name.ilike.{pattern},"
                    f"brand_name.ilike.{pattern},"
                    f"search_keywords.cs.{{{query}}}"
                )
                .limit(limit)
                .execute()
            )
            return [CatalogItem.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="search_medicines",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to search {self.TABLE}: {exc}",
                operation="search_medicines",
            ) from exc

    async def get_by_sku(
        self, distributor_id: str, sku: str
    ) -> Optional[CatalogItem]:
        """Look up a catalog item by SKU within a tenant.

        Args:
            distributor_id: Tenant scope.
            sku: Stock keeping unit code.

        Returns:
            CatalogItem if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("sku", sku)
                .eq("is_deleted", False)
                .maybe_single()
                .execute()
            )
            if result.data:
                return CatalogItem.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_sku",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by SKU: {exc}",
                operation="get_by_sku",
            ) from exc

    async def update_stock(
        self, id: str, distributor_id: str, quantity: int
    ) -> CatalogItem:
        """Set the absolute stock quantity and derive ``is_in_stock``.

        Args:
            id: UUID string of the catalog item.
            distributor_id: Tenant scope.
            quantity: New absolute stock quantity.

        Returns:
            The updated CatalogItem.

        Raises:
            NotFoundError: If the catalog item does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update(
                    {
                        "stock_quantity": quantity,
                        "is_in_stock": quantity > 0,
                    }
                )
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for stock update",
                    operation="update_stock",
                )
            logger.info(
                "db.stock_updated",
                table=self.TABLE,
                item_id=id,
                new_quantity=quantity,
            )
            return CatalogItem.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="update_stock",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update stock for {self.TABLE}: {exc}",
                operation="update_stock",
            ) from exc

    async def batch_update_in_stock_flags(
        self,
        distributor_id: str,
        items_in_stock: list[str],
        items_out_of_stock: list[str],
    ) -> None:
        """Batch-update ``is_in_stock`` flags for multiple items.

        Issues at most two queries regardless of item count.

        Args:
            distributor_id: Tenant scope.
            items_in_stock: Item IDs that should be marked in-stock.
            items_out_of_stock: Item IDs that should be marked out-of-stock.

        Raises:
            DatabaseError: On update failure.
        """
        client = get_db_client()
        try:
            if items_in_stock:
                await (
                    client.table(self.TABLE)
                    .update({"is_in_stock": True})
                    .eq("distributor_id", distributor_id)
                    .in_("id", items_in_stock)
                    .execute()
                )
            if items_out_of_stock:
                await (
                    client.table(self.TABLE)
                    .update({"is_in_stock": False})
                    .eq("distributor_id", distributor_id)
                    .in_("id", items_out_of_stock)
                    .execute()
                )
            logger.info(
                "db.batch_in_stock_updated",
                table=self.TABLE,
                distributor_id=distributor_id,
                in_stock_count=len(items_in_stock),
                out_of_stock_count=len(items_out_of_stock),
            )
        except Exception as exc:
            logger.error(
                "db.batch_update_failed",
                table=self.TABLE,
                operation="batch_update_in_stock_flags",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to batch-update in-stock flags: {exc}",
                operation="batch_update_in_stock_flags",
            ) from exc

    async def reserve_stock(
        self, id: str, distributor_id: str, quantity: int
    ) -> CatalogItem:
        """Increment reserved quantity for a pending order.

        Reads the current ``reserved_quantity`` and adds ``quantity`` to
        it.  The caller (order service) is responsible for validating
        that sufficient unreserved stock exists before calling this.

        Args:
            id: UUID string of the catalog item.
            distributor_id: Tenant scope.
            quantity: Number of units to reserve.

        Returns:
            The updated CatalogItem.

        Raises:
            NotFoundError: If the catalog item does not exist.
            DatabaseError: On query / update failure.
        """
        try:
            item = await self.get_by_id_or_raise(
                id, distributor_id=distributor_id
            )
            client = get_db_client()
            new_reserved = item.reserved_quantity + quantity
            result = (
                await client.table(self.TABLE)
                .update({"reserved_quantity": new_reserved})
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for reservation",
                    operation="reserve_stock",
                )
            logger.info(
                "db.stock_reserved",
                table=self.TABLE,
                item_id=id,
                reserved=quantity,
                new_reserved_total=new_reserved,
            )
            return CatalogItem.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="reserve_stock",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to reserve stock for {self.TABLE}: {exc}",
                operation="reserve_stock",
            ) from exc

    async def release_reserved_stock(
        self, id: str, distributor_id: str, quantity: int
    ) -> CatalogItem:
        """Decrement reserved quantity when an order is cancelled or fulfilled.

        Ensures ``reserved_quantity`` never goes below zero.

        Args:
            id: UUID string of the catalog item.
            distributor_id: Tenant scope.
            quantity: Number of reserved units to release.

        Returns:
            The updated CatalogItem.

        Raises:
            NotFoundError: If the catalog item does not exist.
            DatabaseError: On query / update failure.
        """
        try:
            item = await self.get_by_id_or_raise(
                id, distributor_id=distributor_id
            )
            client = get_db_client()
            new_reserved = max(0, item.reserved_quantity - quantity)
            result = (
                await client.table(self.TABLE)
                .update({"reserved_quantity": new_reserved})
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for release",
                    operation="release_reserved_stock",
                )
            logger.info(
                "db.stock_released",
                table=self.TABLE,
                item_id=id,
                released=quantity,
                new_reserved_total=new_reserved,
            )
            return CatalogItem.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="release_reserved_stock",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to release reserved stock for {self.TABLE}: {exc}",
                operation="release_reserved_stock",
            ) from exc

    async def soft_delete(self, id: str, distributor_id: str) -> bool:
        """Soft-delete a catalog item by setting is_deleted and deleted_at.

        Args:
            id: UUID string of the catalog item.
            distributor_id: Tenant scope.

        Returns:
            True if the row was found and updated.

        Raises:
            NotFoundError: If the catalog item does not exist or is
                already deleted.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(tz=timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .update(
                    {
                        "is_deleted": True,
                        "deleted_at": now,
                        "is_active": False,
                    }
                )
                .eq("id", id)
                .eq("distributor_id", distributor_id)
                .eq("is_deleted", False)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found or already deleted",
                    operation="soft_delete",
                )
            logger.info(
                "db.record_soft_deleted",
                table=self.TABLE,
                item_id=id,
            )
            return True
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.soft_delete_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to soft-delete {self.TABLE}: {exc}",
                operation="soft_delete",
            ) from exc

    async def upsert_by_sku_or_name(
        self,
        distributor_id: str,
        data: CatalogItemCreate,
    ) -> tuple[CatalogItem, bool]:
        """Insert or update a catalog item matched by SKU or medicine_name.

        Match priority: SKU (exact) → medicine_name (exact, case-insensitive).
        If a match is found the row is updated with any non-None fields from
        ``data``; otherwise a new row is inserted.

        Args:
            distributor_id: Tenant scope.
            data: Validated creation payload (distributor_id must match).

        Returns:
            Tuple of (CatalogItem, was_inserted).  ``was_inserted`` is True
            when a brand-new row was created, False when an existing row
            was updated.

        Raises:
            DatabaseError: On query / insert / update failure.
        """
        try:
            existing: Optional[CatalogItem] = None

            # Priority 1 — match by SKU (fastest, most reliable)
            if data.sku:
                existing = await self.get_by_sku(distributor_id, data.sku)

            # Priority 2 — match by medicine_name (case-insensitive)
            if existing is None:
                client = get_db_client()
                result = (
                    await client.table(self.TABLE)
                    .select("*")
                    .eq("distributor_id", distributor_id)
                    .ilike("medicine_name", data.medicine_name)
                    .eq("is_deleted", False)
                    .limit(1)
                    .maybe_single()
                    .execute()
                )
                if result.data:
                    existing = CatalogItem.model_validate(result.data)

            if existing is not None:
                # Build update payload from creation data
                update_fields = data.model_dump(exclude_none=True, mode="json")
                update_fields.pop("distributor_id", None)
                update_payload = CatalogItemUpdate.model_validate(update_fields)
                updated = await self.update(
                    str(existing.id),
                    update_payload,
                    distributor_id=distributor_id,
                )
                logger.info(
                    "db.catalog_upserted",
                    action="updated",
                    item_id=str(existing.id),
                    medicine_name=data.medicine_name,
                )
                return updated, False

            # No match — insert new row
            created = await self.create(data)
            logger.info(
                "db.catalog_upserted",
                action="inserted",
                medicine_name=data.medicine_name,
            )
            return created, True

        except (NotFoundError, DatabaseError):
            raise
        except Exception as exc:
            logger.error(
                "db.upsert_failed",
                table=self.TABLE,
                operation="upsert_by_sku_or_name",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to upsert {self.TABLE}: {exc}",
                operation="upsert_by_sku_or_name",
            ) from exc

    async def get_low_stock_items(
        self, distributor_id: str
    ) -> list[CatalogItem]:
        """Fetch catalog items where stock is at or below the low-stock threshold.

        Uses a PostgREST computed filter:
        ``stock_quantity <= low_stock_threshold`` via an RPC or
        raw filter.  Since Supabase PostgREST does not natively
        support cross-column comparisons in simple filters, we fetch
        all active items and filter in Python.  For distributors with
        very large catalogs this should be replaced with an RPC call.

        Args:
            distributor_id: Tenant scope.

        Returns:
            List of low-stock CatalogItem entities.

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
                .eq("is_deleted", False)
                .execute()
            )
            items = [CatalogItem.model_validate(row) for row in result.data]
            low_stock = [
                item
                for item in items
                if item.stock_quantity <= item.low_stock_threshold
            ]
            return low_stock
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_low_stock_items",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch low-stock {self.TABLE}: {exc}",
                operation="get_low_stock_items",
            ) from exc
