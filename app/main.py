"""TELETRAAN — FastAPI application factory with lifespan management.

Creates the FastAPI application instance, configures logging, database
client lifecycle, middleware (security headers, request‑ID, CORS), and
registers all API routers.

The ``app`` object at module level is the ASGI entry-point imported by
uvicorn (see ``Procfile``).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import TeletraanBaseException
from app.core.logging import configure_logging
from app.db.client import close_client, init_client
from app.scheduler.setup import create_scheduler


# ── Lifespan ────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown resources.

    Startup:
        1. Configure structured logging.
        2. Initialise Supabase async client.
        3. Start APScheduler.
        4. Log readiness.

    Shutdown:
        1. Stop APScheduler.
        2. Close Supabase client.
        3. Log clean shutdown.
    """
    settings = get_settings()
    configure_logging(app_env=settings.app_env, log_level=settings.log_level)
    logger.info(
        "app.startup",
        env=settings.app_env,
        host=settings.app_host,
        port=settings.app_port,
    )

    await init_client()
    logger.info("app.db_connected")

    scheduler = create_scheduler()
    scheduler.start()
    logger.info(
        "app.scheduler_started",
        job_count=len(scheduler.get_jobs()),
    )

    yield

    scheduler.shutdown(wait=True)
    logger.info("app.scheduler_stopped")

    await close_client()
    logger.info("app.shutdown_complete")


# ── Factory ─────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and return the fully-configured FastAPI application.

    Returns:
        FastAPI application instance with middleware and routers.
    """
    settings = get_settings()

    application = FastAPI(
        title="TELETRAAN",
        description="WhatsApp order & operations system for medicine distributors.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )

    _register_middleware(application)
    _register_routers(application)
    _register_exception_handlers(application)

    return application


# ── Middleware ───────────────────────────────────────────────────────


def _register_middleware(application: FastAPI) -> None:
    """Attach all middleware to the application.

    Order matters — middleware added last runs first on request.
    """
    # CORS — restricted to same-origin in production
    settings = get_settings()
    allow_origins = ["*"] if settings.app_env == "development" else []
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: object,
    ) -> Response:
        """Add security headers to every response."""
        response: Response = await call_next(request)  # type: ignore[misc]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    @application.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: object,
    ) -> Response:
        """Assign a UUID request-ID and inject it into loguru context."""
        request_id = str(uuid4())
        request.state.request_id = request_id
        with logger.contextualize(request_id=request_id):
            start = time.monotonic()
            response: Response = await call_next(request)  # type: ignore[misc]
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
        response.headers["X-Request-ID"] = request_id
        return response


# ── Routers ─────────────────────────────────────────────────────────


def _register_routers(application: FastAPI) -> None:
    """Mount all API routers.

    Routers are imported here to avoid circular imports and to keep the
    router list in one place.  As new phases add routers, they are
    appended to this function.
    """
    import pathlib

    from fastapi.staticfiles import StaticFiles

    from app.api.health import router as health_router
    from app.api.webhook import router as webhook_router

    application.include_router(health_router)
    application.include_router(webhook_router)

    from app.api.payments import router as payments_router

    application.include_router(payments_router)

    from app.api.admin import router as admin_router

    application.include_router(admin_router)

    # ── Dashboard static files ──────────────────────────────────────
    dashboard_dir = pathlib.Path(__file__).resolve().parent.parent / "dashboard"
    if dashboard_dir.is_dir():
        application.mount(
            "/dashboard",
            StaticFiles(directory=str(dashboard_dir), html=True),
            name="dashboard",
        )


# ── Exception Handlers ──────────────────────────────────────────────


def _register_exception_handlers(application: FastAPI) -> None:
    """Register global exception handlers for consistent error responses."""

    @application.exception_handler(TeletraanBaseException)
    async def teletraan_exception_handler(
        request: Request,
        exc: TeletraanBaseException,
    ) -> JSONResponse:
        """Return structured JSON for all known TELETRAAN exceptions."""
        logger.error(
            "exception.handled",
            exception_type=type(exc).__name__,
            message=str(exc),
            operation=getattr(exc, "operation", None),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": type(exc).__name__,
                "message": str(exc),
                "operation": getattr(exc, "operation", None),
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Catch-all for unexpected errors — log full trace, return 500."""
        logger.exception(
            "exception.unhandled",
            exception_type=type(exc).__name__,
            message=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred.",
            },
        )


# ── Application instance ────────────────────────────────────────────

app = create_app()
