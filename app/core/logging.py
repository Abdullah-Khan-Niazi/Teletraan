"""Loguru structured logging configuration for TELETRAAN.

Provides:
- JSON serialisation in production for log aggregation.
- Coloured human-readable output in development.
- Automatic PII masking (phone numbers → last 4 digits only).
- Daily rotating warning-level file logger.

Call ``configure_logging()`` once at startup before any other import
that uses ``logger``.
"""

from __future__ import annotations

import re
import sys

from loguru import logger


# ── PII masking ─────────────────────────────────────────────────────

_PHONE_PATTERN = re.compile(r"\+?\d{10,15}")


def _mask_phone(match: re.Match[str]) -> str:
    """Replace all but last 4 digits of a phone number."""
    num = match.group()
    return f"****{num[-4:]}"


def mask_pii(record: dict) -> bool:  # noqa: D401 — loguru filter signature
    """Loguru filter that masks phone numbers in log messages and extras.

    Args:
        record: Loguru log record dict.

    Returns:
        Always ``True`` so the record is emitted after masking.
    """
    record["message"] = _PHONE_PATTERN.sub(_mask_phone, record["message"])

    extra: dict = record.get("extra", {})
    for key, value in extra.items():
        if isinstance(value, str):
            extra[key] = _PHONE_PATTERN.sub(_mask_phone, value)

    return True


# ── Public configuration entry-point ────────────────────────────────


def configure_logging(*, app_env: str = "development", log_level: str = "DEBUG") -> None:
    """Remove default handler and install TELETRAAN loggers.

    Args:
        app_env: One of ``development``, ``staging``, ``production``.
        log_level: Minimum log level for stdout handler.
    """
    logger.remove()  # remove default stderr handler

    if app_env == "production":
        # JSON for log aggregation (Render, Datadog, etc.)
        logger.add(
            sys.stdout,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | "
                "{name}:{line} | {message} | {extra}"
            ),
            level=log_level,
            serialize=True,
            filter=mask_pii,
            enqueue=True,
        )
    else:
        # Coloured human-readable for local development
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
                "{message} | {extra}"
            ),
            level="DEBUG",
            colorize=True,
            filter=mask_pii,
        )

    # Rotating file for WARNING+ — always enabled
    logger.add(
        "logs/teletraan_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="WARNING",
        serialize=True,
        filter=mask_pii,
        enqueue=True,
    )

    logger.info(
        "logging.configured",
        app_env=app_env,
        log_level=log_level,
    )
