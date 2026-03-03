"""High-level payment service — bridge between channel handlers and gateways.

Channel handlers call this service to:
- Initiate a payment (create DB record + generate link)
- Check payment status
- Cancel a pending payment
- Confirm a manual bank transfer

This layer handles DB record creation and gateway delegation,
while ``webhook_handlers.py`` handles the callback side.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from loguru import logger

from app.core.constants import (
    ActorType,
    GatewayPaymentStatus,
    GatewayType,
    PaymentType,
)
from app.core.exceptions import PaymentGatewayError
from app.db.models.audit import AuditLogCreate
from app.db.models.payment import Payment, PaymentCreate, PaymentUpdate
from app.db.repositories import audit_repo, payment_repo
from app.payments.base import PaymentLinkResponse
from app.payments.factory import get_gateway


class PaymentService:
    """Orchestrates payment initiation and lifecycle management.

    This service creates payment records in the database, delegates
    link generation to the appropriate gateway, and provides status
    queries.
    """

    async def initiate_payment(
        self,
        amount_paisas: int,
        payment_type: PaymentType,
        payer_phone: str,
        description: str,
        *,
        distributor_id: Optional[str] = None,
        order_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        gateway_name: Optional[str] = None,
        distributor_preferred_gateway: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[Payment, PaymentLinkResponse]:
        """Create a payment record and generate a payment link.

        Args:
            amount_paisas: Amount to charge in paisas.
            payment_type: What the payment is for.
            payer_phone: Customer phone (E.164).
            description: Human-readable description.
            distributor_id: FK to distributors.
            order_id: FK to orders.
            customer_id: FK to customers.
            gateway_name: Explicit gateway override.
            distributor_preferred_gateway: Per-distributor preference.
            metadata: Additional metadata to store.

        Returns:
            Tuple of (Payment record, PaymentLinkResponse from gateway).

        Raises:
            PaymentGatewayError: If link generation fails.
        """
        # Resolve gateway
        gateway = get_gateway(
            gateway_name,
            distributor_preferred=distributor_preferred_gateway,
        )
        gw_name = gateway.get_gateway_name()

        # Map gateway name to GatewayType enum
        try:
            gw_type = GatewayType(gw_name)
        except ValueError:
            gw_type = GatewayType.MANUAL

        # Generate a unique transaction reference
        transaction_reference = f"TXN-{uuid4().hex[:16].upper()}"

        # Generate payment link via gateway
        link_response = await gateway.generate_payment_link(
            amount_paisas=amount_paisas,
            reference_id=transaction_reference,
            description=description,
            payer_phone=payer_phone,
        )

        # Create payment record in DB
        payment_data = PaymentCreate(
            transaction_reference=transaction_reference,
            payment_type=payment_type,
            distributor_id=distributor_id,
            order_id=order_id,
            customer_id=customer_id,
            gateway=gw_type,
            gateway_transaction_id=link_response.gateway_order_id,
            gateway_order_id=link_response.gateway_order_id,
            amount_paisas=amount_paisas,
            status=GatewayPaymentStatus.PENDING,
            payment_link=link_response.link_url,
            payment_link_expires_at=link_response.expires_at,
            metadata=metadata or {},
        )

        payment = await payment_repo.create(payment_data)

        logger.info(
            "payment.service.initiated",
            payment_id=str(payment.id),
            gateway=gw_name,
            amount_paisas=amount_paisas,
            phone_suffix=payer_phone[-4:],
        )

        # Audit log
        await self._audit(
            action="payment.initiated",
            entity_type="payment",
            entity_id=payment.id,
            distributor_id=distributor_id,
            metadata={
                "gateway": gw_name,
                "amount_paisas": amount_paisas,
                "payment_type": payment_type.value,
                "transaction_reference": transaction_reference,
            },
        )

        return payment, link_response

    async def check_status(
        self,
        payment_id: str,
        *,
        poll_gateway: bool = False,
    ) -> Payment:
        """Check the status of a payment.

        Args:
            payment_id: UUID of the payment record.
            poll_gateway: If True, also query the gateway for
                fresh status (in addition to DB).

        Returns:
            Updated Payment record.

        Raises:
            PaymentGatewayError: If the payment is not found.
        """
        payment = await payment_repo.get_by_id(payment_id)
        if payment is None:
            raise PaymentGatewayError(
                f"Payment not found: {payment_id}",
                operation="check_status",
            )

        if poll_gateway and payment.gateway_transaction_id:
            try:
                gateway = get_gateway(payment.gateway.value)
                gw_status = await gateway.get_payment_status(
                    payment.gateway_transaction_id
                )

                # Update DB if gateway reports a different status
                new_status = _map_gateway_status(gw_status.status)
                if new_status and new_status != payment.status:
                    update = PaymentUpdate(status=new_status)
                    if new_status == GatewayPaymentStatus.COMPLETED:
                        update.paid_at = gw_status.paid_at or datetime.now(
                            tz=timezone.utc
                        )
                    payment = await payment_repo.update(
                        str(payment.id), update
                    )
            except Exception as exc:
                logger.warning(
                    "payment.service.poll_failed",
                    payment_id=payment_id,
                    error=str(exc),
                )

        return payment

    async def cancel_payment(self, payment_id: str) -> bool:
        """Cancel a pending payment.

        Args:
            payment_id: UUID of the payment record.

        Returns:
            True if cancellation succeeded.
        """
        payment = await payment_repo.get_by_id(payment_id)
        if payment is None:
            return False

        if payment.status != GatewayPaymentStatus.PENDING:
            logger.info(
                "payment.service.cancel_not_pending",
                payment_id=payment_id,
                current_status=payment.status.value,
            )
            return False

        cancelled = True
        if payment.gateway_transaction_id:
            try:
                gateway = get_gateway(payment.gateway.value)
                cancelled = await gateway.cancel_payment(
                    payment.gateway_transaction_id
                )
            except Exception as exc:
                logger.warning(
                    "payment.service.gateway_cancel_failed",
                    payment_id=payment_id,
                    error=str(exc),
                )
                cancelled = False

        if not cancelled:
            logger.warning(
                "payment.service.cancel_skipped_db",
                payment_id=payment_id,
                reason="gateway cancellation failed or rejected",
            )
            return False

        # Only mark cancelled in DB after gateway confirms cancellation
        await payment_repo.update(
            str(payment.id),
            PaymentUpdate(status=GatewayPaymentStatus.CANCELLED),
        )

        logger.info(
            "payment.service.cancelled",
            payment_id=payment_id,
            gateway_cancelled=cancelled,
        )

        return True

    async def confirm_bank_transfer(
        self,
        payment_id: str,
        confirmed_by: str,
        screenshot_path: Optional[str] = None,
    ) -> Payment:
        """Manually confirm a bank transfer payment.

        Called when the distributor owner confirms receipt.

        Args:
            payment_id: UUID of the payment record.
            confirmed_by: Identifier of who confirmed.
            screenshot_path: Path to the uploaded screenshot.

        Returns:
            Updated Payment record.

        Raises:
            PaymentGatewayError: If the payment is not found or
                is not a bank transfer.
        """
        payment = await payment_repo.get_by_id(payment_id)
        if payment is None:
            raise PaymentGatewayError(
                f"Payment not found: {payment_id}",
                operation="confirm_bank_transfer",
            )

        if payment.gateway != GatewayType.BANK_TRANSFER:
            raise PaymentGatewayError(
                f"Payment {payment_id} is not a bank transfer",
                operation="confirm_bank_transfer",
            )

        now = datetime.now(tz=timezone.utc)

        update = PaymentUpdate(
            status=GatewayPaymentStatus.COMPLETED,
            paid_at=now,
            manual_confirmed_at=now,
            screenshot_storage_path=screenshot_path,
            metadata={"confirmed_by": confirmed_by},
        )

        payment = await payment_repo.update(str(payment.id), update)

        logger.info(
            "payment.service.bank_transfer_confirmed",
            payment_id=payment_id,
            confirmed_by=confirmed_by,
        )

        await self._audit(
            action="payment.bank_transfer_confirmed",
            entity_type="payment",
            entity_id=payment.id,
            metadata={
                "confirmed_by": confirmed_by,
                "screenshot_path": screenshot_path,
            },
        )

        return payment

    async def expire_stale_payments(self) -> int:
        """Expire all pending payments past their link expiry.

        Called by the scheduler to clean up abandoned payments.

        Returns:
            Count of payments expired.
        """
        stale = await payment_repo.get_pending_expired()
        count = 0

        for payment in stale:
            try:
                await payment_repo.update(
                    str(payment.id),
                    PaymentUpdate(
                        status=GatewayPaymentStatus.EXPIRED,
                        failure_reason="Payment link expired",
                    ),
                )
                count += 1
            except Exception as exc:
                logger.error(
                    "payment.service.expire_failed",
                    payment_id=str(payment.id),
                    error=str(exc),
                )

        if count > 0:
            logger.info(
                "payment.service.expired_stale",
                count=count,
            )

        return count

    # ── Internal helpers ────────────────────────────────────────────

    async def _audit(
        self,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
        distributor_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write to audit log — never raises."""
        try:
            await audit_repo.create(
                AuditLogCreate(
                    actor_type=ActorType.SYSTEM,
                    action=action,
                    distributor_id=distributor_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    metadata=metadata or {},
                )
            )
        except Exception as exc:
            logger.error(
                "payment.service.audit_failed",
                action=action,
                error=str(exc),
            )


def _map_gateway_status(status_str: str) -> Optional[GatewayPaymentStatus]:
    """Map a gateway status string to GatewayPaymentStatus enum.

    Args:
        status_str: Raw status from gateway.

    Returns:
        Mapped enum value or None if unknown.
    """
    mapping = {
        "completed": GatewayPaymentStatus.COMPLETED,
        "paid": GatewayPaymentStatus.COMPLETED,
        "success": GatewayPaymentStatus.COMPLETED,
        "pending": GatewayPaymentStatus.PENDING,
        "created": GatewayPaymentStatus.PENDING,
        "failed": GatewayPaymentStatus.FAILED,
        "expired": GatewayPaymentStatus.EXPIRED,
        "cancelled": GatewayPaymentStatus.CANCELLED,
        "refunded": GatewayPaymentStatus.REFUNDED,
    }
    return mapping.get(status_str.lower())


# ── Module singleton ────────────────────────────────────────────────
payment_service = PaymentService()
