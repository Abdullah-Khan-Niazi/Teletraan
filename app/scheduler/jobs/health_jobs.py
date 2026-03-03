"""Health check scheduler jobs — AI provider, gateway, and DB health.

Contains APScheduler jobs for:
- ``run_system_health_check`` — checks AI providers, payment gateways,
  and database connectivity, logging results.

Job functions **never raise exceptions** to the scheduler.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger


# ═══════════════════════════════════════════════════════════════════
# SYSTEM HEALTH CHECK JOB
# ═══════════════════════════════════════════════════════════════════


async def run_system_health_check() -> None:
    """Check health of AI providers, payment gateways, and database.

    Called by APScheduler periodically to surface infrastructure
    failures before they affect users.  Results are logged as
    structured events for monitoring.

    This function never raises.
    """
    logger.info("scheduler.health_check.start")

    results: dict[str, dict] = {}

    # ── AI Provider Health ──────────────────────────────────────────
    results["ai"] = await _check_ai_health()

    # ── Payment Gateway Health ──────────────────────────────────────
    results["gateways"] = await _check_gateway_health()

    # ── Database Health ─────────────────────────────────────────────
    results["database"] = await _check_database_health()

    # ── Log summary ─────────────────────────────────────────────────
    all_healthy = all(
        component.get("healthy", False)
        for component in results.values()
    )

    logger.info(
        "scheduler.health_check.complete",
        all_healthy=all_healthy,
        ai_healthy=results["ai"].get("healthy", False),
        gateways_healthy=results["gateways"].get("healthy", False),
        database_healthy=results["database"].get("healthy", False),
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


async def _check_ai_health() -> dict:
    """Check AI provider availability.

    Returns:
        Dict with ``healthy`` bool and provider details.
    """
    try:
        from app.ai.factory import get_ai_provider

        provider = get_ai_provider()
        provider_name = type(provider).__name__

        # Simple availability check — just verify the provider is
        # instantiated and can be accessed. A full health check
        # (sending a test prompt) would incur cost.
        return {
            "healthy": True,
            "provider": provider_name,
        }
    except Exception as exc:
        logger.warning(
            "scheduler.health_check.ai_unhealthy",
            error=str(exc),
        )
        return {
            "healthy": False,
            "error": str(exc),
        }


async def _check_gateway_health() -> dict:
    """Check payment gateway availability.

    Returns:
        Dict with ``healthy`` bool and per-gateway status.
    """
    try:
        from app.payments.factory import get_available_gateways, get_gateway

        available = get_available_gateways()
        gateway_status: dict[str, bool] = {}

        for name in available:
            try:
                gateway = get_gateway(name)
                is_healthy = await gateway.health_check()
                gateway_status[name] = is_healthy
            except Exception as exc:
                logger.warning(
                    "scheduler.health_check.gateway_unhealthy",
                    gateway=name,
                    error=str(exc),
                )
                gateway_status[name] = False

        all_healthy = all(gateway_status.values()) if gateway_status else True
        return {
            "healthy": all_healthy,
            "gateways": gateway_status,
        }
    except Exception as exc:
        logger.warning(
            "scheduler.health_check.gateways_check_failed",
            error=str(exc),
        )
        return {
            "healthy": False,
            "error": str(exc),
        }


async def _check_database_health() -> dict:
    """Check database connectivity.

    Performs a simple query to verify the connection is alive.

    Returns:
        Dict with ``healthy`` bool and latency info.
    """
    try:
        from app.db.client import get_db_client

        start = datetime.now(tz=timezone.utc)
        client = get_db_client()

        # Simple connectivity test — count distributors
        result = (
            await client.table("distributors")
            .select("id", count="exact")
            .limit(1)
            .execute()
        )
        end = datetime.now(tz=timezone.utc)
        latency_ms = (end - start).total_seconds() * 1000

        return {
            "healthy": True,
            "latency_ms": round(latency_ms, 2),
            "distributor_count": result.count if result.count else 0,
        }
    except Exception as exc:
        logger.warning(
            "scheduler.health_check.db_unhealthy",
            error=str(exc),
        )
        return {
            "healthy": False,
            "error": str(exc),
        }
