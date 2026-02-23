"""Payment gateway callback API routes.

Each supported gateway gets its own ``POST /api/payments/{gateway}/callback``
endpoint.  All endpoints follow the same pattern:

1. Read raw body bytes for signature verification.
2. Parse payload (JSON or form-encoded).
3. Delegate to ``handle_gateway_callback()``.
4. Always return HTTP 200 to the gateway (errors logged, not returned).

The dummy callback endpoint also supports GET for easy browser testing.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger

from app.payments.webhook_handlers import handle_gateway_callback

router = APIRouter(prefix="/api/payments", tags=["payments"])


# ── Helper ──────────────────────────────────────────────────────────


async def _parse_payload(request: Request) -> tuple[bytes, dict[str, Any]]:
    """Read raw body and parse it as JSON or form-encoded.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Tuple of (raw_bytes, parsed_dict).
    """
    raw_body = await request.body()

    try:
        parsed = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Try form-encoded
        try:
            qs = parse_qs(raw_body.decode("utf-8"))
            parsed = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
        except Exception:
            parsed = {}

    return raw_body, parsed


def _headers_dict(request: Request) -> dict[str, str]:
    """Extract headers as a plain dict.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Dict of header name → value.
    """
    return dict(request.headers)


# ── Gateway callback endpoints ──────────────────────────────────────


@router.post("/jazzcash/callback")
async def jazzcash_callback(request: Request) -> Response:
    """JazzCash payment callback endpoint.

    JazzCash sends form-encoded or JSON POST to this URL after
    a payment attempt completes.
    """
    raw_body, parsed = await _parse_payload(request)
    headers = _headers_dict(request)

    try:
        result = await handle_gateway_callback(
            "jazzcash", raw_body, headers, parsed
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "processed": result.is_successful,
            },
        )
    except Exception as exc:
        logger.error(
            "api.payments.jazzcash.callback_error",
            error=str(exc),
        )
        # Always return 200 to gateway to prevent retries
        return JSONResponse(
            status_code=200,
            content={"status": "error", "processed": False},
        )


@router.post("/easypaisa/callback")
async def easypaisa_callback(request: Request) -> Response:
    """EasyPaisa payment callback endpoint.

    EasyPaisa posts form-encoded data on payment completion.
    """
    raw_body, parsed = await _parse_payload(request)
    headers = _headers_dict(request)

    try:
        result = await handle_gateway_callback(
            "easypaisa", raw_body, headers, parsed
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "processed": result.is_successful,
            },
        )
    except Exception as exc:
        logger.error(
            "api.payments.easypaisa.callback_error",
            error=str(exc),
        )
        return JSONResponse(
            status_code=200,
            content={"status": "error", "processed": False},
        )


@router.post("/safepay/callback")
async def safepay_callback(request: Request) -> Response:
    """SafePay webhook callback endpoint.

    SafePay sends JSON webhooks with HMAC-SHA256 signature in
    ``X-Safepay-Signature`` header.
    """
    raw_body, parsed = await _parse_payload(request)
    headers = _headers_dict(request)

    try:
        result = await handle_gateway_callback(
            "safepay", raw_body, headers, parsed
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "processed": result.is_successful,
            },
        )
    except Exception as exc:
        logger.error(
            "api.payments.safepay.callback_error",
            error=str(exc),
        )
        return JSONResponse(
            status_code=200,
            content={"status": "error", "processed": False},
        )


@router.post("/nayapay/callback")
async def nayapay_callback(request: Request) -> Response:
    """NayaPay webhook callback endpoint.

    NayaPay sends JSON webhooks with HMAC-SHA256 signature in
    ``X-Signature`` header.
    """
    raw_body, parsed = await _parse_payload(request)
    headers = _headers_dict(request)

    try:
        result = await handle_gateway_callback(
            "nayapay", raw_body, headers, parsed
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "processed": result.is_successful,
            },
        )
    except Exception as exc:
        logger.error(
            "api.payments.nayapay.callback_error",
            error=str(exc),
        )
        return JSONResponse(
            status_code=200,
            content={"status": "error", "processed": False},
        )


@router.post("/dummy/callback")
async def dummy_callback(request: Request) -> Response:
    """Dummy gateway callback endpoint (dev/test only).

    Accepts both GET query params and POST body.
    """
    raw_body, parsed = await _parse_payload(request)
    headers = _headers_dict(request)

    # Merge query params into parsed dict (for GET-style test calls)
    for key, value in request.query_params.items():
        if key not in parsed:
            parsed[key] = value

    try:
        result = await handle_gateway_callback(
            "dummy", raw_body, headers, parsed
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "processed": result.is_successful,
                "gateway_transaction_id": result.gateway_transaction_id,
            },
        )
    except Exception as exc:
        logger.error(
            "api.payments.dummy.callback_error",
            error=str(exc),
        )
        return JSONResponse(
            status_code=200,
            content={"status": "error", "processed": False},
        )


@router.get("/dummy/callback")
async def dummy_callback_get(request: Request) -> Response:
    """Dummy gateway GET callback — for easy browser-based testing.

    Reads ``order_id`` and ``ref`` from query parameters.
    """
    parsed = dict(request.query_params)

    try:
        result = await handle_gateway_callback(
            "dummy", b"", _headers_dict(request), parsed
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "processed": result.is_successful,
                "gateway_transaction_id": result.gateway_transaction_id,
            },
        )
    except Exception as exc:
        logger.error(
            "api.payments.dummy.get_callback_error",
            error=str(exc),
        )
        return JSONResponse(
            status_code=200,
            content={"status": "error", "processed": False},
        )


# ── Health / status ─────────────────────────────────────────────────


@router.get("/status")
async def payment_status() -> JSONResponse:
    """Return active payment gateway info.

    Useful for health checks and dashboard display.
    """
    from app.payments.factory import get_available_gateways, get_gateway

    try:
        gateway = get_gateway()
        metadata = gateway.get_gateway_metadata()
        healthy = await gateway.health_check()

        return JSONResponse(
            status_code=200,
            content={
                "active_gateway": gateway.get_gateway_name(),
                "available_gateways": get_available_gateways(),
                "healthy": healthy,
                "metadata": metadata,
            },
        )
    except Exception as exc:
        return JSONResponse(
            status_code=200,
            content={
                "active_gateway": "unknown",
                "error": str(exc),
                "healthy": False,
            },
        )
