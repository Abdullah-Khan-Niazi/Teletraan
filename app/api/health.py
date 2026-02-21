"""Health check endpoint for TELETRAAN.

Reports overall system readiness by probing the Supabase database
connection.  Returns HTTP 200 when healthy, 503 when any dependency
is down.

Used by Render/Railway health checks and uptime monitors.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from app.db.client import health_check as db_health_check

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="System health check",
    response_description="JSON object with overall status and dependency checks.",
)
async def health() -> JSONResponse:
    """Check system health by probing all critical dependencies.

    Returns:
        JSONResponse with status 200 if all checks pass, 503 otherwise.
    """
    db_ok = await db_health_check()

    checks = {
        "database": "ok" if db_ok else "unavailable",
    }

    all_healthy = all(v == "ok" for v in checks.values())
    status = "healthy" if all_healthy else "degraded"
    status_code = 200 if all_healthy else 503

    if not all_healthy:
        logger.warning("health.degraded", checks=checks)

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "checks": checks,
        },
    )
