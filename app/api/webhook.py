"""Meta WhatsApp webhook endpoints.

GET  /api/webhook  — Meta verification challenge.
POST /api/webhook  — Incoming messages and status updates.

Critical rules (from Meta docs):
    1. HMAC-SHA256 signature verified BEFORE any processing.
    2. POST always returns 200 — even on internal errors — to prevent
       Meta from endlessly retrying the same webhook.
    3. Processing happens asynchronously via ``BackgroundTasks`` to stay
       within the 5-second response window.
    4. Messages are deduplicated by ``message.id`` (TTLCache).
"""

from __future__ import annotations

from cachetools import TTLCache
from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger

from app.core.config import get_settings
from app.core.security import verify_meta_signature
from app.whatsapp.parser import (
    IncomingMessageType,
    ParsedMessage,
    ParsedStatusUpdate,
    parse_webhook_payload,
)

router = APIRouter(prefix="/api", tags=["webhook"])

# ── Deduplication cache ──────────────────────────────────────────────
# TTLCache: max 10 000 entries, 24-hour TTL. Survives short restarts.
# For multi-worker deployments, replace with Redis or Supabase check.

_seen_messages: TTLCache[str, bool] = TTLCache(maxsize=10_000, ttl=86_400)


def _is_duplicate(message_id: str) -> bool:
    """Return True if this message ID was already processed."""
    if message_id in _seen_messages:
        logger.info("webhook.duplicate_skipped", message_id=message_id)
        return True
    _seen_messages[message_id] = True
    return False


# ── GET — Webhook verification ───────────────────────────────────────


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
) -> Response:
    """Handle Meta webhook verification challenge.

    Meta sends a GET request with ``hub.mode``, ``hub.verify_token``, and
    ``hub.challenge``.  If the token matches, return the challenge as
    plain text.

    Returns:
        PlainTextResponse with the challenge string, or 403.
    """
    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("webhook.verification_success")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning(
        "webhook.verification_failed",
        hub_mode=hub_mode,
        token_match=False,
    )
    return JSONResponse(
        status_code=403,
        content={"error": "Verification token mismatch."},
    )


# ── POST — Incoming events ──────────────────────────────────────────


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Receive and process incoming WhatsApp webhook events.

    Processing pipeline:
        1. Read raw body bytes.
        2. Verify HMAC-SHA256 signature against ``META_APP_SECRET``.
        3. Parse JSON into structured dataclasses.
        4. Deduplicate messages by ID.
        5. Spawn background tasks for async processing.
        6. Return 200 immediately.

    Returns:
        HTTP 200 with ``{"status": "ok"}`` — always, even on error.
    """
    settings = get_settings()

    # ── Step 1: raw bytes (needed before JSON parse for HMAC) ────
    raw_body = await request.body()

    # ── Step 2: HMAC signature verification ──────────────────────
    signature = request.headers.get("x-hub-signature-256", "")
    if not verify_meta_signature(raw_body, signature, settings.meta_app_secret):
        logger.warning(
            "webhook.signature_invalid",
            content_length=len(raw_body),
        )
        # Meta docs say return 200 even on failure to avoid retries.
        # However, industry practice is to reject with 400 for security.
        # We return 400 here to protect against forged payloads.
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid signature."},
        )

    # ── Step 3: parse JSON ───────────────────────────────────────
    try:
        payload = await request.json()
    except Exception as exc:
        logger.error("webhook.json_parse_error", error=str(exc))
        return JSONResponse(
            status_code=200,
            content={"status": "ok"},
        )

    # ── Step 4: parse into typed objects ─────────────────────────
    result = parse_webhook_payload(payload)

    # ── Step 5: schedule processing ──────────────────────────────
    for message in result.messages:
        if _is_duplicate(message.message_id):
            continue
        background_tasks.add_task(_process_message, message)

    for status_update in result.statuses:
        background_tasks.add_task(_process_status_update, status_update)

    # ── Step 6: return 200 immediately ───────────────────────────
    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
    )


# ── Background processing ───────────────────────────────────────────


async def _process_message(message: ParsedMessage) -> None:
    """Process a single incoming WhatsApp message.

    This runs as a FastAPI background task. Errors are logged but never
    propagated — we already returned 200 to Meta.

    The orchestrator (Phase 3) will replace the stub logic below.
    Currently logs the message and performs basic routing.
    """
    with logger.contextualize(
        message_id=message.message_id,
        phone_number_id=message.phone_number_id,
        from_suffix=message.from_number[-4:] if message.from_number else "????",
    ):
        try:
            logger.info(
                "webhook.message_received",
                message_type=message.message_type.value,
                sender_name=message.sender_name,
            )

            # ── Route by message type ────────────────────────────
            if message.message_type == IncomingMessageType.REACTION:
                logger.debug("webhook.reaction_ignored")
                return

            if message.message_type in (
                IncomingMessageType.STICKER,
                IncomingMessageType.LOCATION,
                IncomingMessageType.CONTACTS,
            ):
                logger.info(
                    "webhook.unsupported_type_received",
                    message_type=message.message_type.value,
                )
                # Orchestrator will send guidance message in Phase 3
                return

            # For text, audio, image, button/list replies — the full
            # orchestrator pipeline will handle these in Phase 3.
            # For now, log that we received and parsed them correctly.
            logger.info(
                "webhook.message_ready_for_orchestrator",
                message_type=message.message_type.value,
                has_text=message.text is not None,
                has_media=message.media is not None,
                has_interactive=message.interactive_reply is not None,
            )

        except Exception as exc:
            logger.exception(
                "webhook.message_processing_error",
                error=str(exc),
            )


async def _process_status_update(status: ParsedStatusUpdate) -> None:
    """Process a delivery status update.

    Updates notification delivery status in the database.
    The full implementation (Phase 3+) will update notifications_log.

    This runs as a FastAPI background task.
    """
    try:
        logger.info(
            "webhook.status_update",
            message_id=status.message_id,
            status=status.status.value,
            recipient_suffix=status.recipient_id[-4:] if status.recipient_id else "????",
        )

        if status.status.value == "failed" and status.errors:
            logger.warning(
                "webhook.message_delivery_failed",
                message_id=status.message_id,
                errors=status.errors,
            )

        # Full notification_repo.update_delivery_status() call
        # will be wired in Phase 3 when orchestrator is built.

    except Exception as exc:
        logger.exception(
            "webhook.status_processing_error",
            error=str(exc),
        )
