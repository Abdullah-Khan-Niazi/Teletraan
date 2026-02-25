"""Service registry repository — DB operations for service_registry table.

Provides CRUD and lookup for available services that Channel B can sell.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.service_registry import (
    ServiceRegistryCreate,
    ServiceRegistryEntry,
    ServiceRegistryUpdate,
)


class ServiceRegistryRepository:
    """Repository for ``service_registry`` table."""

    TABLE = "service_registry"

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    async def get_by_id(self, service_id: str) -> Optional[ServiceRegistryEntry]:
        """Fetch a single service by UUID."""
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("id", service_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return ServiceRegistryEntry(**result.data)
            return None
        except Exception as exc:
            logger.error(
                "service_registry.get_by_id.failed",
                service_id=service_id,
                error=str(exc),
            )
            raise DatabaseError(f"Failed to fetch service {service_id}") from exc

    async def get_by_id_or_raise(self, service_id: str) -> ServiceRegistryEntry:
        """Fetch a single service or raise ``NotFoundError``."""
        entry = await self.get_by_id(service_id)
        if entry is None:
            raise NotFoundError(f"Service {service_id} not found")
        return entry

    async def get_by_slug(self, slug: str) -> Optional[ServiceRegistryEntry]:
        """Fetch a service by its unique slug."""
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("slug", slug)
                .maybe_single()
                .execute()
            )
            if result.data:
                return ServiceRegistryEntry(**result.data)
            return None
        except Exception as exc:
            logger.error(
                "service_registry.get_by_slug.failed",
                slug=slug,
                error=str(exc),
            )
            raise DatabaseError(f"Failed to fetch service by slug {slug}") from exc

    async def get_available_services(self) -> list[ServiceRegistryEntry]:
        """Return all services that are currently available for sale."""
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("is_available", True)
                .order("name")
                .execute()
            )
            return [ServiceRegistryEntry(**row) for row in (result.data or [])]
        except Exception as exc:
            logger.error(
                "service_registry.get_available.failed",
                error=str(exc),
            )
            raise DatabaseError("Failed to fetch available services") from exc

    async def get_all(self) -> list[ServiceRegistryEntry]:
        """Return all services (including unavailable / coming-soon)."""
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .order("name")
                .execute()
            )
            return [ServiceRegistryEntry(**row) for row in (result.data or [])]
        except Exception as exc:
            logger.error(
                "service_registry.get_all.failed",
                error=str(exc),
            )
            raise DatabaseError("Failed to fetch all services") from exc

    async def create(self, data: ServiceRegistryCreate) -> ServiceRegistryEntry:
        """Insert a new service entry."""
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True)
            result = (
                await client.table(self.TABLE)
                .insert(payload)
                .execute()
            )
            return ServiceRegistryEntry(**result.data[0])
        except Exception as exc:
            logger.error(
                "service_registry.create.failed",
                slug=data.slug,
                error=str(exc),
            )
            raise DatabaseError(f"Failed to create service {data.slug}") from exc

    async def update(
        self, service_id: str, data: ServiceRegistryUpdate
    ) -> ServiceRegistryEntry:
        """Partial update of a service entry."""
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True)
            result = (
                await client.table(self.TABLE)
                .update(payload)
                .eq("id", service_id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(f"Service {service_id} not found")
            return ServiceRegistryEntry(**result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "service_registry.update.failed",
                service_id=service_id,
                error=str(exc),
            )
            raise DatabaseError(f"Failed to update service {service_id}") from exc
