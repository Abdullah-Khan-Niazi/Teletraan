"""Delivery zone repository — all database operations for delivery_zones table."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.delivery_zone import DeliveryZone, DeliveryZoneCreate


class DeliveryZoneRepository:
    """Repository for delivery_zones table operations.

    All read operations require ``distributor_id`` for tenant isolation.
    """

    TABLE = "delivery_zones"

    async def get_by_id(
        self,
        id: str,
        *,
        distributor_id: str,
    ) -> Optional[DeliveryZone]:
        """Fetch a delivery zone by primary key within a tenant.

        Args:
            id: UUID string of the delivery zone.
            distributor_id: Tenant scope.

        Returns:
            DeliveryZone if found, None otherwise.

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
                return DeliveryZone.model_validate(result.data)
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

    async def get_active_zones(
        self,
        distributor_id: str,
    ) -> list[DeliveryZone]:
        """Fetch all active delivery zones for a distributor.

        Args:
            distributor_id: Tenant scope.

        Returns:
            List of active DeliveryZone entities.

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
                .order("name")
                .execute()
            )
            return [DeliveryZone.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_active_zones",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_active_zones",
            ) from exc

    async def find_zone_for_area(
        self,
        distributor_id: str,
        area: str,
    ) -> Optional[DeliveryZone]:
        """Find the delivery zone containing a given area/locality.

        Searches the ``areas`` text array for a case-insensitive
        match.  Falls back to Python filtering since PostgREST
        array contains is exact-case by default.

        Args:
            distributor_id: Tenant scope.
            area: Area or locality name to search for.

        Returns:
            Matching DeliveryZone or None.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            zones = await self.get_active_zones(distributor_id)
            area_lower = area.lower()
            for zone in zones:
                if any(a.lower() == area_lower for a in zone.areas):
                    return zone
            # Partial match fallback
            for zone in zones:
                if any(area_lower in a.lower() for a in zone.areas):
                    return zone
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="find_zone_for_area",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to find zone for area: {exc}",
                operation="find_zone_for_area",
            ) from exc

    async def create(self, data: DeliveryZoneCreate) -> DeliveryZone:
        """Insert a new delivery zone.

        Args:
            data: Validated creation payload.

        Returns:
            The created DeliveryZone.

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
                zone_name=data.name,
            )
            return DeliveryZone.model_validate(result.data[0])
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
