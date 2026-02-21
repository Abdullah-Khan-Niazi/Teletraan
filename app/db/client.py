"""Supabase async client singleton for TELETRAAN.

Call ``init_client()`` once during FastAPI lifespan startup.  All
repository code accesses the client via ``get_db_client()``.

The ``health_check()`` coroutine is used by the ``/health`` endpoint.
"""

from __future__ import annotations

from loguru import logger
from supabase import AsyncClient, acreate_client

from app.core.config import get_settings
from app.core.exceptions import DatabaseError

_client: AsyncClient | None = None


async def init_client() -> None:
    """Initialise the Supabase async client.

    Must be called exactly once during application startup
    (inside the FastAPI lifespan context manager).

    Raises:
        DatabaseError: If the client cannot be created or the
            initial connectivity check fails.
    """
    global _client

    if _client is not None:
        logger.warning("db.client_already_initialised")
        return

    settings = get_settings()
    try:
        _client = await acreate_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )
        logger.info("db.client_initialised", url=settings.supabase_url)
    except Exception as exc:
        logger.critical("db.client_init_failed", error=str(exc))
        raise DatabaseError(
            f"Failed to initialise Supabase client: {exc}",
            operation="init_client",
        ) from exc


def get_db_client() -> AsyncClient:
    """Return the initialised Supabase async client.

    Returns:
        The singleton ``AsyncClient`` instance.

    Raises:
        DatabaseError: If called before ``init_client()``.
    """
    if _client is None:
        raise DatabaseError(
            "Supabase client not initialised — call init_client() first.",
            operation="get_db_client",
        )
    return _client


async def health_check() -> bool:
    """Verify that the database is reachable.

    Performs a lightweight read against a system-level query.
    Never raises — returns ``False`` on any failure so the health
    endpoint can report degraded status without crashing.

    Returns:
        ``True`` if the DB responded, ``False`` otherwise.
    """
    try:
        client = get_db_client()
        # A minimal query — read 0 rows from subscription_plans
        await client.table("subscription_plans").select("id").limit(1).execute()
        return True
    except Exception as exc:
        logger.error("db.health_check_failed", error=str(exc))
        return False


async def close_client() -> None:
    """Tear down the Supabase client on shutdown.

    Called during FastAPI lifespan shutdown.
    """
    global _client
    if _client is not None:
        # supabase-py AsyncClient does not expose a close() method,
        # but we clear the reference so get_db_client() fails fast
        # if anything tries to use it after shutdown.
        _client = None
        logger.info("db.client_closed")
