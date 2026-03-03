"""Unified post-payment webhook handler.

Provides a single entry point for processing gateway callbacks with:
- Idempotency via ``payment_repo.get_by_gateway_transaction_id``
- Automatic status transitions on the payments table
- Audit logging with full payload
- Structured logging with PII masking

Usage::

    from app.payments.webhook_handlers import handle_gateway_callback

    result = await handle_gateway_callback("jazzcash", raw_body, headers, parsed_payload)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from loguru import logger

from app.core.constants import ActorType, GatewayPaymentStatus
from app.core.exceptions import PaymentSignatureError
from app.db.models.audit import AuditLogCreate
from app.db.models.payment import PaymentUpdate
from app.db.repositories import audit_repo, payment_repo
from app.payments.base import PaymentCallbackResult
from app.payments.factory import get_gateway


async def handle_gateway_callback(
    gateway_name: str,
    raw_body: bytes,
    headers: dict[str, str],
    parsed_payload: dict[str, Any],
) -> PaymentCallbackResult:
    """Process an incoming payment gateway webhook callback.

    This is the unified entry point that all gateway-specific API
    routes call.  Handles:

    1. Signature verification.
    2. Callback processing via the gateway.
    3. Idempotency check (skip if already processed).
    4. Payment record update in the database.
    5. Audit log entry.

    Args:
        gateway_name: Which gateway sent the callback.
        raw_body: Raw request body bytes (for signature verification).
        headers: HTTP request headers.
        parsed_payload: Parsed JSON/form payload.

    Returns:
        PaymentCallbackResult from the gateway.

    Raises:
        PaymentSignatureError: If signature verification fails.
        PaymentGatewayError: If callback processing fails.
    """
    gateway = get_gateway(gateway_name)

    # ── Step 1: Verify webhook signature ────────────────────────────
    is_valid = await gateway.verify_webhook_signature(raw_body, headers)
    if not is_valid:
        logger.warning(
            "payment.webhook.signature_failed",
            gateway=gateway_name,
            body_preview=raw_body[:200].decode("utf-8", errors="replace"),
        )

        # Audit the failed verification
        await _audit_payment_event(
            action="payment.signature_failed",
            gateway=gateway_name,
            metadata={
                "headers_subset": {
                    k: v
                    for k, v in headers.items()
                    if k.lower().startswith(("x-", "content-"))
                },
                "body_preview": raw_body[:500].decode("utf-8", errors="replace"),
            },
        )

        raise PaymentSignatureError(
            f"Webhook signature verification failed for {gateway_name}",
            operation="verify_webhook_signature",
            details={"gateway": gateway_name},
        )

    # ── Step 2: Process the callback through the gateway ────────────
    result = await gateway.process_callback(parsed_payload)

    # ── Step 3: Idempotency check ───────────────────────────────────
    if result.gateway_transaction_id:
        existing = await payment_repo.get_by_gateway_transaction_id(
            result.gateway_transaction_id
        )
        if existing and existing.status == GatewayPaymentStatus.COMPLETED:
            logger.info(
                "payment.webhook.duplicate_ignored",
                gateway=gateway_name,
                gateway_txn_id=result.gateway_transaction_id,
            )
            await _audit_payment_event(
                action="payment.duplicate_callback",
                gateway=gateway_name,
                entity_type="payment",
                entity_id=existing.id,
                metadata={
                    "gateway_txn_id": result.gateway_transaction_id,
                },
            )
            # Return success without re-processing
            return result

        # ── Step 4: Update payment record ───────────────────────────
        if existing:
            await _update_payment_from_result(existing.id, result, gateway_name)

    # ── Step 5: Audit log ───────────────────────────────────────────
    await _audit_payment_event(
        action=(
            "payment.completed"
            if result.is_successful
            else "payment.failed"
        ),
        gateway=gateway_name,
        metadata={
            "gateway_txn_id": result.gateway_transaction_id,
            "amount_paisas": result.amount_paisas,
            "is_successful": result.is_successful,
            "failure_reason": result.failure_reason,
        },
    )

    logger.info(
        "payment.webhook.processed",
        gateway=gateway_name,
        is_successful=result.is_successful,
        gateway_txn_id=result.gateway_transaction_id,
        amount_paisas=result.amount_paisas,
    )

    return result


async def _update_payment_from_result(
    payment_id: UUID,
    result: PaymentCallbackResult,
    gateway_name: str,
) -> None:
    """Update a payment record based on callback result.

    Args:
        payment_id: UUID of the payment record.
        result: Gateway callback result.
        gateway_name: Which gateway processed this.
    """
    now = datetime.now(tz=timezone.utc)

    if result.is_successful:
        update = PaymentUpdate(
            status=GatewayPaymentStatus.COMPLETED,
            gateway_transaction_id=result.gateway_transaction_id,
            paid_at=now,
            gateway_response=result.raw_payload,
        )
    else:
        update = PaymentUpdate(
            status=GatewayPaymentStatus.FAILED,
            gateway_transaction_id=result.gateway_transaction_id,
            failure_reason=result.failure_reason,
            gateway_response=result.raw_payload,
        )

    try:
        await payment_repo.update(str(payment_id), update)
        logger.info(
            "payment.webhook.record_updated",
            payment_id=str(payment_id),
            new_status=update.status.value if update.status else "unknown",
        )
    except Exception as exc:
        logger.error(
            "payment.webhook.record_update_failed",
            payment_id=str(payment_id),
            error=str(exc),
        )


async def _audit_payment_event(
    action: str,
    gateway: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Write a payment event to the audit log.

    Args:
        action: Machine-readable event name.
        gateway: Gateway name.
        entity_type: Type of entity affected (e.g. "payment").
        entity_id: UUID of the entity.
        metadata: Additional event data.
    """
    audit_metadata = {"gateway": gateway}
    if metadata:
        audit_metadata.update(metadata)

    try:
        await audit_repo.create(
            AuditLogCreate(
                actor_type=ActorType.SYSTEM,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=audit_metadata,
            )
        )
    except Exception as exc:
        # Audit log failure must never break payment flow
        logger.error(
            "payment.webhook.audit_log_failed",
            action=action,
            error=str(exc),
        )
