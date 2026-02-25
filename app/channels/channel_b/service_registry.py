"""Channel B — Dynamic Service Registry with caching and handler routing.

Loads available services from ``service_registry`` table, caches them with
a configurable TTL, and routes incoming prospects to the correct sales
flow handler based on each service's ``sales_flow_handler`` field.

Usage::

    from app.channels.channel_b.service_registry import service_registry

    services = await service_registry.get_services()
    handler  = service_registry.get_handler(service)
"""

from __future__ import annotations

import importlib
import time
from typing import Any, Callable, Optional

from loguru import logger

from app.db.models.service_registry import ServiceRegistryEntry
from app.db.repositories.service_registry_repo import ServiceRegistryRepository


# Default cache TTL: 5 minutes (services change infrequently)
_DEFAULT_CACHE_TTL_SECONDS: int = 300

# Registry of handler functions keyed by ``sales_flow_handler`` slug.
# Filled lazily on first lookup.
_HANDLER_REGISTRY: dict[str, Callable[..., Any]] = {}

# Maps handler slug → Python dotted path for lazy import
_HANDLER_PATHS: dict[str, str] = {
    "teletraan_sales": "app.channels.channel_b.sales_flow.handle_sales_step",
}


class ServiceRegistry:
    """In-memory cache of available services with handler routing.

    The registry is populated from DB on first call (or after TTL expiry)
    and maps each service's ``sales_flow_handler`` identifier to a
    concrete Python function.
    """

    def __init__(self, *, cache_ttl: int = _DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._repo = ServiceRegistryRepository()
        self._cache: list[ServiceRegistryEntry] = []
        self._cache_by_id: dict[str, ServiceRegistryEntry] = {}
        self._cache_by_slug: dict[str, ServiceRegistryEntry] = {}
        self._cache_ts: float = 0.0
        self._cache_ttl: int = cache_ttl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_services(self, *, force_refresh: bool = False) -> list[ServiceRegistryEntry]:
        """Return list of available services (cached)."""
        if force_refresh or self._is_stale():
            await self._refresh()
        return self._cache

    async def get_service_by_id(self, service_id: str) -> Optional[ServiceRegistryEntry]:
        """Look up a service by UUID from cache (fallback to DB)."""
        if self._is_stale():
            await self._refresh()
        entry = self._cache_by_id.get(service_id)
        if entry is not None:
            return entry
        # Cache miss — try DB directly (may be newly inserted)
        return await self._repo.get_by_id(service_id)

    async def get_service_by_slug(self, slug: str) -> Optional[ServiceRegistryEntry]:
        """Look up a service by slug from cache (fallback to DB)."""
        if self._is_stale():
            await self._refresh()
        entry = self._cache_by_slug.get(slug)
        if entry is not None:
            return entry
        return await self._repo.get_by_slug(slug)

    def get_handler(self, service: ServiceRegistryEntry) -> Optional[Callable[..., Any]]:
        """Resolve a Python handler function for the given service.

        Returns ``None`` if no handler is configured or not found.
        """
        handler_slug = service.sales_flow_handler
        if not handler_slug:
            logger.warning(
                "service_registry.no_handler_configured",
                service_slug=service.slug,
            )
            return None

        # Check runtime registry first
        if handler_slug in _HANDLER_REGISTRY:
            return _HANDLER_REGISTRY[handler_slug]

        # Lazy-load from _HANDLER_PATHS
        dotted_path = _HANDLER_PATHS.get(handler_slug)
        if not dotted_path:
            logger.error(
                "service_registry.handler_path_unknown",
                handler_slug=handler_slug,
                service_slug=service.slug,
            )
            return None

        return self._import_handler(handler_slug, dotted_path)

    def register_handler(self, slug: str, handler: Callable[..., Any]) -> None:
        """Manually register a handler function (useful for tests)."""
        _HANDLER_REGISTRY[slug] = handler
        logger.debug(
            "service_registry.handler_registered",
            slug=slug,
        )

    async def get_default_service(self) -> Optional[ServiceRegistryEntry]:
        """Return the first available service (used when only one exists)."""
        services = await self.get_services()
        if services:
            return services[0]
        return None

    # ------------------------------------------------------------------
    # Formatting helpers (messages for prospects)
    # ------------------------------------------------------------------

    def format_service_list(self, services: list[ServiceRegistryEntry]) -> str:
        """Format services into a numbered list for WhatsApp message."""
        lines: list[str] = []
        for idx, svc in enumerate(services, 1):
            label = svc.short_description or svc.name
            price = svc.format_pricing()
            coming = " 🔜 (Coming Soon)" if svc.is_coming_soon else ""
            lines.append(f"{idx}. *{svc.name}*{coming}\n   {label}\n   {price}")
        return "\n\n".join(lines)

    def format_service_detail(self, service: ServiceRegistryEntry) -> str:
        """Format a single service's full detail for WhatsApp."""
        parts = [
            f"📦 *{service.name}*",
            "",
            service.description or service.short_description or "",
            "",
            f"💰 {service.format_pricing()}",
        ]
        if service.target_business_types:
            biz = ", ".join(service.target_business_types)
            parts.append(f"🏢 Best for: {biz}")
        if service.demo_video_url:
            parts.append(f"🎥 Demo: {service.demo_video_url}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_stale(self) -> bool:
        """True if cache is empty or older than TTL."""
        if not self._cache:
            return True
        return (time.monotonic() - self._cache_ts) > self._cache_ttl

    async def _refresh(self) -> None:
        """Reload available services from DB and rebuild indexes."""
        try:
            services = await self._repo.get_available_services()
            self._cache = services
            self._cache_by_id = {str(s.id): s for s in services}
            self._cache_by_slug = {s.slug: s for s in services}
            self._cache_ts = time.monotonic()
            logger.info(
                "service_registry.cache_refreshed",
                count=len(services),
            )
        except Exception as exc:
            logger.error(
                "service_registry.refresh_failed",
                error=str(exc),
            )
            # Keep stale cache if refresh fails — better than empty

    @staticmethod
    def _import_handler(slug: str, dotted_path: str) -> Optional[Callable[..., Any]]:
        """Import a handler function by dotted path and cache it."""
        try:
            module_path, func_name = dotted_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler = getattr(module, func_name)
            _HANDLER_REGISTRY[slug] = handler
            logger.debug(
                "service_registry.handler_loaded",
                slug=slug,
                path=dotted_path,
            )
            return handler
        except (ImportError, AttributeError) as exc:
            logger.error(
                "service_registry.handler_import_failed",
                slug=slug,
                path=dotted_path,
                error=str(exc),
            )
            return None


# Module-level singleton
service_registry = ServiceRegistry()
