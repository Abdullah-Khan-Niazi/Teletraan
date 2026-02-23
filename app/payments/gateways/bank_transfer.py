"""Bank transfer payment gateway — manual approval flow.

Bank transfer has no external API.  Instead:

1. Bot sends bank account details to the customer.
2. Customer transfers funds and sends a screenshot via WhatsApp.
3. Bot downloads and stores the screenshot.
4. Bot notifies the distributor owner with screenshot + payer details.
5. Owner sends a confirmation command.
6. Bot auto-extends subscription or confirms order.

All ``generate_payment_link`` returns are instruction text (not URLs).
Webhook verification always returns True (no real webhook).

Settings required:
- ``bank_account_name``
- ``bank_account_number``
- ``bank_iban``
- ``bank_name``
- ``bank_branch``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import PaymentGatewayError
from app.payments.base import (
    PaymentCallbackResult,
    PaymentGateway,
    PaymentLinkResponse,
    PaymentStatusResult,
)


# ── In-memory store for pending bank transfers ──────────────────────
# Maps gateway_order_id → record dict.
# In production this is backed by the payments DB table; the store
# here is only used for test / dev purposes to track link generation.
_BANK_TRANSFERS: dict[str, dict[str, Any]] = {}


class BankTransferGateway(PaymentGateway):
    """Manual bank transfer gateway.

    Does not call any external API.  ``generate_payment_link`` returns
    human-readable bank account instructions as the ``link_url``.
    Confirmation happens when the distributor owner manually approves
    via the admin command flow.
    """

    def _get_bank_details(self) -> dict[str, str]:
        """Return configured bank account details.

        Raises:
            PaymentGatewayError: If bank details are not configured.
        """
        settings = get_settings()
        name = settings.bank_account_name
        number = settings.bank_account_number
        iban = settings.bank_iban
        bank = settings.bank_name

        if not all([name, number, bank]):
            raise PaymentGatewayError(
                "Bank transfer details not configured",
                operation="get_bank_details",
            )

        return {
            "account_name": name or "",
            "account_number": number or "",
            "iban": iban or "",
            "bank_name": bank or "",
            "branch": settings.bank_branch or "",
        }

    # ── PaymentGateway implementation ───────────────────────────────

    async def generate_payment_link(
        self,
        amount_paisas: int,
        reference_id: str,
        description: str,
        payer_phone: str,
    ) -> PaymentLinkResponse:
        """Generate bank transfer instructions (not a URL).

        The ``link_url`` field contains human-readable bank details
        formatted for WhatsApp delivery.

        Args:
            amount_paisas: Payment amount in paisas.
            reference_id: Internal transaction reference.
            description: Payment description.
            payer_phone: Customer phone.

        Returns:
            PaymentLinkResponse with instructions as ``link_url``.
        """
        bank = self._get_bank_details()
        settings = get_settings()

        amount_rupees = amount_paisas / 100
        gateway_order_id = f"BANK-{uuid4().hex[:12].upper()}"

        expiry = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.payment_link_expiry_minutes
        )

        instructions = (
            f"*Bank Transfer Details*\n\n"
            f"Bank: {bank['bank_name']}\n"
            f"Account Name: {bank['account_name']}\n"
            f"Account Number: {bank['account_number']}\n"
        )
        if bank["iban"]:
            instructions += f"IBAN: {bank['iban']}\n"
        if bank["branch"]:
            instructions += f"Branch: {bank['branch']}\n"

        instructions += (
            f"\nAmount: Rs. {amount_rupees:,.2f}\n"
            f"Reference: {reference_id}\n\n"
            f"Please transfer the exact amount and send a "
            f"screenshot of the receipt."
        )

        _BANK_TRANSFERS[gateway_order_id] = {
            "reference_id": reference_id,
            "amount_paisas": amount_paisas,
            "payer_phone": payer_phone,
            "description": description,
            "status": "pending",
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": expiry,
        }

        logger.info(
            "payment.bank_transfer.instructions_generated",
            gateway_order_id=gateway_order_id,
            amount_paisas=amount_paisas,
        )

        return PaymentLinkResponse(
            link_url=instructions,
            gateway_order_id=gateway_order_id,
            expires_at=expiry,
            metadata={
                "gateway": "bank_transfer",
                "bank_name": bank["bank_name"],
                "instructions_only": True,
            },
        )

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Bank transfer has no webhook — always returns True.

        Args:
            payload_bytes: Unused.
            headers: Unused.

        Returns:
            Always True.
        """
        return True

    async def process_callback(
        self,
        payload_dict: dict[str, Any],
    ) -> PaymentCallbackResult:
        """Process a manual bank transfer confirmation.

        Called when the owner confirms receipt of the bank transfer.
        The ``payload_dict`` must contain:
        - ``order_id``: gateway_order_id (BANK-xxx)
        - ``confirmed_by``: who approved it
        - ``confirmed``: True/False

        Args:
            payload_dict: Confirmation data from owner.

        Returns:
            PaymentCallbackResult with outcome.
        """
        gateway_order_id = payload_dict.get("order_id", "")
        is_confirmed = payload_dict.get("confirmed", False)
        confirmed_by = payload_dict.get("confirmed_by", "unknown")

        record = _BANK_TRANSFERS.get(gateway_order_id)
        amount_paisas = record["amount_paisas"] if record else 0

        if record:
            record["status"] = "completed" if is_confirmed else "rejected"
            record["confirmed_by"] = confirmed_by

        if is_confirmed:
            logger.info(
                "payment.bank_transfer.confirmed",
                gateway_order_id=gateway_order_id,
                confirmed_by=confirmed_by,
            )
        else:
            logger.info(
                "payment.bank_transfer.rejected",
                gateway_order_id=gateway_order_id,
                confirmed_by=confirmed_by,
            )

        return PaymentCallbackResult(
            is_successful=is_confirmed,
            amount_paisas=amount_paisas,
            gateway_transaction_id=gateway_order_id,
            failure_reason=None if is_confirmed else "Transfer not confirmed by owner",
            raw_payload=payload_dict,
        )

    async def get_payment_status(
        self,
        gateway_transaction_id: str,
    ) -> PaymentStatusResult:
        """Look up status of a bank transfer.

        Args:
            gateway_transaction_id: The BANK-xxx order ID.

        Returns:
            PaymentStatusResult with current state.
        """
        record = _BANK_TRANSFERS.get(gateway_transaction_id)
        if record is None:
            return PaymentStatusResult(
                status="unknown",
                gateway_transaction_id=gateway_transaction_id,
                amount_paisas=0,
            )

        paid_at = None
        if record["status"] == "completed":
            paid_at = datetime.now(tz=timezone.utc)

        return PaymentStatusResult(
            status=record["status"],
            gateway_transaction_id=gateway_transaction_id,
            amount_paisas=record["amount_paisas"],
            paid_at=paid_at,
            raw_response=record,
        )

    async def cancel_payment(
        self,
        gateway_transaction_id: str,
    ) -> bool:
        """Cancel a pending bank transfer.

        Args:
            gateway_transaction_id: The BANK-xxx order ID.

        Returns:
            True if cancelled, False otherwise.
        """
        record = _BANK_TRANSFERS.get(gateway_transaction_id)
        if record is None or record["status"] != "pending":
            return False

        record["status"] = "cancelled"
        logger.info(
            "payment.bank_transfer.cancelled",
            gateway_order_id=gateway_transaction_id,
        )
        return True

    def get_gateway_name(self) -> str:
        """Return ``'bank_transfer'``."""
        return "bank_transfer"

    def get_gateway_metadata(self) -> dict[str, Any]:
        """Return bank transfer gateway capabilities."""
        return {
            "supported_currencies": ["PKR"],
            "min_amount_paisas": 100,
            "max_amount_paisas": 100_000_000,
            "supports_refunds": False,
            "supports_cancellation": True,
            "production_allowed": True,
            "auth_method": "manual_approval",
            "requires_screenshot": True,
            "is_manual": True,
        }

    async def health_check(self) -> bool:
        """Bank transfer is always healthy if details are configured.

        Returns:
            True if bank details are present.
        """
        try:
            self._get_bank_details()
            return True
        except PaymentGatewayError:
            return False


def clear_bank_transfers() -> None:
    """Clear all in-memory bank transfer records.

    Used by test fixtures to reset state between tests.
    """
    _BANK_TRANSFERS.clear()
