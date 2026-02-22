"""Catalog service — business layer over catalog repository.

Provides:
- TTL-cached catalog access per distributor (avoids DB roundtrips)
- Medicine lookup by name (fuzzy) and by ID
- Category aggregation and filtering
- Stock availability checks
- Catalog statistics
"""

from __future__ import annotations

import asyncio
from typing import Optional, Sequence

from cachetools import TTLCache
from loguru import logger

from app.core.constants import FUZZY_MATCH_HIGH_CONFIDENCE, FUZZY_MATCH_THRESHOLD
from app.db.models.catalog import CatalogItem, CatalogItemCreate, CatalogItemUpdate
from app.db.repositories.catalog_repo import CatalogRepository
from app.inventory.fuzzy_matcher import (
    FuzzyMatchResponse,
    fuzzy_match_medicine,
)


# ═══════════════════════════════════════════════════════════════════
# TTL CACHE CONFIG
# ═══════════════════════════════════════════════════════════════════

# Cache active catalogs per distributor for 5 minutes
_CATALOG_CACHE: TTLCache[str, list[CatalogItem]] = TTLCache(
    maxsize=200,
    ttl=300,
)

# Lock to prevent thundering herd on cache miss
_CACHE_LOCK = asyncio.Lock()


# ═══════════════════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════════════════


class CatalogService:
    """Business-layer service for catalog operations.

    Wraps CatalogRepository with caching, fuzzy matching, and
    category aggregation.

    Args:
        repo: Optional CatalogRepository instance. A default is
            created if not provided.
    """

    def __init__(self, repo: CatalogRepository | None = None) -> None:
        self._repo = repo or CatalogRepository()

    # ── Cached catalog access ─────────────────────────────────────

    async def get_active_catalog(
        self,
        distributor_id: str,
        *,
        force_refresh: bool = False,
    ) -> list[CatalogItem]:
        """Get the full active catalog for a distributor.

        Results are TTL-cached for 5 minutes.  Pass
        ``force_refresh=True`` after catalog mutations.

        Args:
            distributor_id: Tenant scope.
            force_refresh: If True, bypass cache.

        Returns:
            List of active CatalogItem entities.
        """
        if not force_refresh and distributor_id in _CATALOG_CACHE:
            logger.debug(
                "catalog.cache_hit",
                distributor_id=distributor_id,
            )
            return _CATALOG_CACHE[distributor_id]

        async with _CACHE_LOCK:
            # Double-check after acquiring lock
            if not force_refresh and distributor_id in _CATALOG_CACHE:
                return _CATALOG_CACHE[distributor_id]

            logger.debug(
                "catalog.cache_miss",
                distributor_id=distributor_id,
            )
            catalog = await self._repo.get_active_catalog(distributor_id)
            _CATALOG_CACHE[distributor_id] = catalog
            logger.info(
                "catalog.cached",
                distributor_id=distributor_id,
                item_count=len(catalog),
            )
            return catalog

    def invalidate_cache(self, distributor_id: str) -> None:
        """Remove a distributor's catalog from cache.

        Call after any create/update/delete mutation.

        Args:
            distributor_id: Tenant scope.
        """
        _CATALOG_CACHE.pop(distributor_id, None)
        logger.debug("catalog.cache_invalidated", distributor_id=distributor_id)

    def invalidate_all_caches(self) -> None:
        """Clear the entire catalog cache.

        Useful after bulk imports or schema changes.
        """
        _CATALOG_CACHE.clear()
        logger.info("catalog.cache_cleared")

    # ── Fuzzy medicine lookup ─────────────────────────────────────

    async def find_medicine(
        self,
        distributor_id: str,
        query: str,
        *,
        threshold: float = FUZZY_MATCH_THRESHOLD,
        high_confidence: float = FUZZY_MATCH_HIGH_CONFIDENCE,
        max_results: int = 10,
    ) -> FuzzyMatchResponse:
        """Search for a medicine by name using fuzzy matching.

        Loads the cached catalog and runs RapidFuzz matching.

        Args:
            distributor_id: Tenant scope.
            query: Customer's medicine name text.
            threshold: Minimum score for inclusion.
            high_confidence: Score for auto-selection.
            max_results: Maximum results returned.

        Returns:
            FuzzyMatchResponse with ranked matches.
        """
        catalog = await self.get_active_catalog(distributor_id)
        return fuzzy_match_medicine(
            query,
            catalog,
            threshold=threshold,
            high_confidence=high_confidence,
            max_results=max_results,
        )

    async def get_item_by_id(
        self,
        distributor_id: str,
        item_id: str,
    ) -> Optional[CatalogItem]:
        """Get a specific catalog item by ID.

        Checks the cache first before hitting the DB.

        Args:
            distributor_id: Tenant scope.
            item_id: UUID string of the catalog item.

        Returns:
            CatalogItem if found, None otherwise.
        """
        # Try cache first
        if distributor_id in _CATALOG_CACHE:
            for item in _CATALOG_CACHE[distributor_id]:
                if str(item.id) == item_id:
                    return item

        # Fall back to DB
        return await self._repo.get_by_id(
            item_id, distributor_id=distributor_id
        )

    async def get_item_by_id_or_raise(
        self,
        distributor_id: str,
        item_id: str,
    ) -> CatalogItem:
        """Get a specific catalog item or raise NotFoundError.

        Args:
            distributor_id: Tenant scope.
            item_id: UUID string.

        Returns:
            CatalogItem entity.

        Raises:
            NotFoundError: If item not found.
        """
        return await self._repo.get_by_id_or_raise(
            item_id, distributor_id=distributor_id
        )

    # ── Category operations ───────────────────────────────────────

    async def get_categories(
        self,
        distributor_id: str,
    ) -> list[str]:
        """Get distinct categories from the active catalog.

        Args:
            distributor_id: Tenant scope.

        Returns:
            Sorted list of unique category names.
        """
        catalog = await self.get_active_catalog(distributor_id)
        categories = sorted(
            {
                item.category
                for item in catalog
                if item.category
            }
        )
        return categories

    async def get_items_by_category(
        self,
        distributor_id: str,
        category: str,
        *,
        in_stock_only: bool = False,
    ) -> list[CatalogItem]:
        """Get catalog items filtered by category.

        Args:
            distributor_id: Tenant scope.
            category: Category name to filter by.
            in_stock_only: If True, exclude out-of-stock items that
                don't allow ordering when OOS.

        Returns:
            List of matching CatalogItem entities.
        """
        catalog = await self.get_active_catalog(distributor_id)
        items = [
            item
            for item in catalog
            if item.category and item.category.lower() == category.lower()
        ]
        if in_stock_only:
            items = [
                item
                for item in items
                if item.is_in_stock or item.allow_order_when_out_of_stock
            ]
        return items

    # ── Stock checks ──────────────────────────────────────────────

    async def check_stock_availability(
        self,
        distributor_id: str,
        item_id: str,
        quantity: int,
    ) -> tuple[bool, int]:
        """Check if sufficient stock is available for an order.

        Accounts for already-reserved quantity.

        Args:
            distributor_id: Tenant scope.
            item_id: UUID string of the catalog item.
            quantity: Desired order quantity.

        Returns:
            Tuple of (is_available, available_quantity) where
            available_quantity = stock - reserved.
        """
        item = await self.get_item_by_id(distributor_id, item_id)
        if not item:
            return False, 0

        if item.allow_order_when_out_of_stock:
            return True, quantity

        available = max(0, item.stock_quantity - item.reserved_quantity)
        return available >= quantity, available

    async def get_low_stock_items(
        self,
        distributor_id: str,
    ) -> list[CatalogItem]:
        """Get items at or below low-stock threshold.

        Args:
            distributor_id: Tenant scope.

        Returns:
            List of low-stock CatalogItem entities.
        """
        return await self._repo.get_low_stock_items(distributor_id)

    # ── CRUD wrappers (with cache invalidation) ──────────────────

    async def create_item(
        self,
        data: CatalogItemCreate,
    ) -> CatalogItem:
        """Create a new catalog item and invalidate the cache.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created CatalogItem.
        """
        item = await self._repo.create(data)
        self.invalidate_cache(str(data.distributor_id))
        logger.info(
            "catalog.item_created",
            medicine_name=data.medicine_name,
            distributor_id=str(data.distributor_id),
        )
        return item

    async def update_item(
        self,
        item_id: str,
        data: CatalogItemUpdate,
        *,
        distributor_id: str,
    ) -> CatalogItem:
        """Update a catalog item and invalidate the cache.

        Args:
            item_id: UUID string.
            data: Validated update payload.
            distributor_id: Tenant scope.

        Returns:
            The updated CatalogItem.
        """
        item = await self._repo.update(
            item_id, data, distributor_id=distributor_id
        )
        self.invalidate_cache(distributor_id)
        return item

    async def delete_item(
        self,
        item_id: str,
        *,
        distributor_id: str,
    ) -> bool:
        """Soft-delete a catalog item and invalidate the cache.

        Args:
            item_id: UUID string.
            distributor_id: Tenant scope.

        Returns:
            True if deleted.
        """
        result = await self._repo.soft_delete(item_id, distributor_id)
        self.invalidate_cache(distributor_id)
        return result

    async def update_stock(
        self,
        item_id: str,
        distributor_id: str,
        quantity: int,
    ) -> CatalogItem:
        """Update stock quantity and invalidate cache.

        Args:
            item_id: UUID string.
            distributor_id: Tenant scope.
            quantity: New absolute stock quantity.

        Returns:
            The updated CatalogItem.
        """
        item = await self._repo.update_stock(
            item_id, distributor_id, quantity
        )
        self.invalidate_cache(distributor_id)
        return item

    # ── Statistics ────────────────────────────────────────────────

    async def get_catalog_stats(
        self,
        distributor_id: str,
    ) -> dict[str, int | float]:
        """Get summary statistics for a distributor's catalog.

        Args:
            distributor_id: Tenant scope.

        Returns:
            Dict with keys: total_items, in_stock_count,
            out_of_stock_count, low_stock_count, category_count,
            avg_price_paisas.
        """
        catalog = await self.get_active_catalog(distributor_id)
        if not catalog:
            return {
                "total_items": 0,
                "in_stock_count": 0,
                "out_of_stock_count": 0,
                "low_stock_count": 0,
                "category_count": 0,
                "avg_price_paisas": 0,
            }

        in_stock = sum(1 for i in catalog if i.is_in_stock)
        low_stock = sum(
            1 for i in catalog
            if i.stock_quantity <= i.low_stock_threshold
        )
        categories = {i.category for i in catalog if i.category}
        avg_price = sum(i.price_per_unit_paisas for i in catalog) / len(catalog)

        return {
            "total_items": len(catalog),
            "in_stock_count": in_stock,
            "out_of_stock_count": len(catalog) - in_stock,
            "low_stock_count": low_stock,
            "category_count": len(categories),
            "avg_price_paisas": round(avg_price),
        }

    # ── Paginated listing ─────────────────────────────────────────

    async def get_paginated_catalog(
        self,
        distributor_id: str,
        *,
        page: int = 1,
        page_size: int = 10,
        category: str | None = None,
        in_stock_only: bool = False,
    ) -> tuple[list[CatalogItem], int]:
        """Get a page of catalog items with optional filters.

        Args:
            distributor_id: Tenant scope.
            page: 1-based page number.
            page_size: Items per page.
            category: Optional category filter.
            in_stock_only: Exclude OOS items that disallow ordering.

        Returns:
            Tuple of (items for this page, total matching count).
        """
        catalog = await self.get_active_catalog(distributor_id)

        # Apply filters
        filtered = catalog
        if category:
            filtered = [
                i for i in filtered
                if i.category and i.category.lower() == category.lower()
            ]
        if in_stock_only:
            filtered = [
                i for i in filtered
                if i.is_in_stock or i.allow_order_when_out_of_stock
            ]

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = filtered[start:end]

        return page_items, total
