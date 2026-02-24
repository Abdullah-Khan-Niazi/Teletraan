"""Integration tests for Phase 8 — payment gateways.

Covers:
- Dummy gateway full lifecycle (auto-confirm, failure simulation, expiry)
- All 5 production gateways with mocked HTTP responses
- Gateway factory (selection, caching, production guard)
- Webhook handler (signature verification, idempotency, DB updates)
- Payment service (initiate, check, cancel, bank confirm, expiry)
- API callback endpoints

All DB, HTTP, and WhatsApp calls are mocked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.constants import (
    ActorType,
    GatewayPaymentStatus,
    GatewayType,
    PaymentType,
)
from app.db.models.payment import Payment, PaymentCreate, PaymentUpdate
from app.payments.base import (
    PaymentCallbackResult,
    PaymentGateway,
    PaymentLinkResponse,
    PaymentStatusResult,
)
from app.payments.gateways.bank_transfer import (
    BankTransferGateway,
    clear_bank_transfers,
)
from app.payments.gateways.dummy_gateway import DummyGateway, clear_dummy_payments


# ── Fixtures ────────────────────────────────────────────────────────

_NOW = datetime.now(tz=timezone.utc)
_DIST_ID = str(uuid4())
_PAYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_PHONE = "+923001234567"


def _make_payment(**overrides: Any) -> Payment:
    """Create a Payment with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": _PAYMENT_ID,
        "transaction_reference": "TXN-TEST12345678",
        "payment_type": PaymentType.ORDER_PAYMENT,
        "distributor_id": UUID(_DIST_ID),
        "order_id": None,
        "customer_id": None,
        "gateway": GatewayType.DUMMY,
        "gateway_transaction_id": "DUMMY-ABC123",
        "gateway_order_id": "DUMMY-ABC123",
        "amount_paisas": 150000,
        "currency": "PKR",
        "status": GatewayPaymentStatus.PENDING,
        "payment_link": "http://localhost:8000/api/payments/dummy/callback?order_id=DUMMY-ABC123",
        "payment_link_expires_at": _NOW + timedelta(minutes=15),
        "paid_at": None,
        "gateway_response": {},
        "failure_reason": None,
        "refund_amount_paisas": 0,
        "refunded_at": None,
        "screenshot_storage_path": None,
        "manual_confirmed_at": None,
        "metadata": {},
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return Payment(**defaults)


def _mock_settings(**overrides: Any) -> MagicMock:
    """Create a mock settings object."""
    settings = MagicMock()
    settings.app_env = overrides.get("app_env", "development")
    settings.active_payment_gateway = overrides.get("active_payment_gateway", "dummy")
    settings.payment_callback_base_url = overrides.get(
        "payment_callback_base_url", "http://localhost:8000"
    )
    settings.payment_link_expiry_minutes = overrides.get("payment_link_expiry_minutes", 60)
    settings.dummy_gateway_auto_confirm = overrides.get("dummy_gateway_auto_confirm", False)
    settings.dummy_gateway_confirm_delay_seconds = overrides.get(
        "dummy_gateway_confirm_delay_seconds", 10
    )
    # JazzCash
    settings.jazzcash_merchant_id = overrides.get("jazzcash_merchant_id", "MC12345")
    settings.jazzcash_password = overrides.get("jazzcash_password", "pass123")
    settings.jazzcash_integrity_salt = overrides.get("jazzcash_integrity_salt", "salt123")
    settings.jazzcash_api_url = overrides.get("jazzcash_api_url", "https://sandbox.jazzcash.com.pk")
    # EasyPaisa
    settings.easypaisa_store_id = overrides.get("easypaisa_store_id", "STORE001")
    settings.easypaisa_hash_key = overrides.get("easypaisa_hash_key", "hashkey123")
    settings.easypaisa_api_url = overrides.get("easypaisa_api_url", "https://easypay.easypaisa.com.pk")
    # SafePay
    settings.safepay_api_key = overrides.get("safepay_api_key", "sp_key_123")
    settings.safepay_secret_key = overrides.get("safepay_secret_key", "sp_secret_123")
    settings.safepay_api_url = overrides.get("safepay_api_url", "https://api.getsafepay.com")
    settings.safepay_webhook_secret = overrides.get("safepay_webhook_secret", "sp_webhook_secret")
    # NayaPay
    settings.nayapay_merchant_id = overrides.get("nayapay_merchant_id", "NP_MERCHANT")
    settings.nayapay_api_key = overrides.get("nayapay_api_key", "np_key_123")
    settings.nayapay_secret = overrides.get("nayapay_secret", "np_secret_123")
    settings.nayapay_api_url = overrides.get("nayapay_api_url", "https://api.nayapay.com")
    # Bank Transfer
    settings.bank_account_name = overrides.get("bank_account_name", "TELETRAAN")
    settings.bank_account_number = overrides.get("bank_account_number", "1234567890")
    settings.bank_iban = overrides.get("bank_iban", "PK36SCBL0000001234567890")
    settings.bank_name = overrides.get("bank_name", "Standard Chartered")
    settings.bank_branch = overrides.get("bank_branch", "Lahore Main")
    return settings


# ═══════════════════════════════════════════════════════════════════
# DUMMY GATEWAY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestDummyGateway:
    """Dummy gateway full lifecycle tests."""

    def setup_method(self) -> None:
        """Clean up dummy payments before each test."""
        clear_dummy_payments()

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_generate_payment_link_success(
        self, mock_settings: MagicMock
    ) -> None:
        """Normal link generation returns valid response."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        result = await gw.generate_payment_link(
            amount_paisas=150000,
            reference_id="REF-001",
            description="Test payment",
            payer_phone=_PHONE,
        )
        assert result.link_url.startswith("http://localhost:8000/api/payments/dummy/callback")
        assert result.gateway_order_id.startswith("DUMMY-")
        assert result.expires_at > _NOW
        assert result.metadata["gateway"] == "dummy"

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_generate_link_failure_simulation(
        self, mock_settings: MagicMock
    ) -> None:
        """Amount ending in 99 paisas flags will_fail."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        result = await gw.generate_payment_link(
            amount_paisas=14999,  # ends in 99
            reference_id="REF-FAIL",
            description="Fail test",
            payer_phone=_PHONE,
        )
        assert result.metadata["will_fail"] is True

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_process_callback_success(self, mock_settings: MagicMock) -> None:
        """Successful callback for normal amount."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        link = await gw.generate_payment_link(
            amount_paisas=150000,
            reference_id="REF-002",
            description="Test",
            payer_phone=_PHONE,
        )
        result = await gw.process_callback({"order_id": link.gateway_order_id})
        assert result.is_successful is True
        assert result.amount_paisas == 150000

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_process_callback_fails_for_99(self, mock_settings: MagicMock) -> None:
        """Callback fails for amount ending in 99."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        link = await gw.generate_payment_link(
            amount_paisas=14999,
            reference_id="REF-FAIL2",
            description="Fail test",
            payer_phone=_PHONE,
        )
        result = await gw.process_callback({"order_id": link.gateway_order_id})
        assert result.is_successful is False
        assert "99 paisas" in (result.failure_reason or "")

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_get_payment_status(self, mock_settings: MagicMock) -> None:
        """Status query returns correct state."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        link = await gw.generate_payment_link(
            amount_paisas=50000,
            reference_id="REF-003",
            description="Test",
            payer_phone=_PHONE,
        )
        status = await gw.get_payment_status(link.gateway_order_id)
        assert status.status == "pending"

        # Process callback
        await gw.process_callback({"order_id": link.gateway_order_id})
        status = await gw.get_payment_status(link.gateway_order_id)
        assert status.status == "completed"

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_cancel_payment(self, mock_settings: MagicMock) -> None:
        """Pending payment can be cancelled."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        link = await gw.generate_payment_link(
            amount_paisas=50000,
            reference_id="REF-004",
            description="Test",
            payer_phone=_PHONE,
        )
        assert await gw.cancel_payment(link.gateway_order_id) is True
        status = await gw.get_payment_status(link.gateway_order_id)
        assert status.status == "cancelled"

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_production_guard(self, mock_settings: MagicMock) -> None:
        """Dummy gateway raises in production."""
        mock_settings.return_value = _mock_settings(app_env="production")
        gw = DummyGateway()
        with pytest.raises(Exception, match="blocked in production"):
            await gw.generate_payment_link(
                amount_paisas=10000,
                reference_id="REF-PROD",
                description="Test",
                payer_phone=_PHONE,
            )

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_unknown_order_raises(self, mock_settings: MagicMock) -> None:
        """Process callback with unknown order_id raises."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        with pytest.raises(Exception, match="Unknown dummy payment"):
            await gw.process_callback({"order_id": "DUMMY-NONEXISTENT"})

    def test_gateway_name(self) -> None:
        """Gateway name is 'dummy'."""
        assert DummyGateway().get_gateway_name() == "dummy"

    def test_gateway_metadata(self) -> None:
        """Metadata shows production_allowed = False."""
        meta = DummyGateway().get_gateway_metadata()
        assert meta["production_allowed"] is False
        assert meta["supports_cancellation"] is True

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_health_check(self, mock_settings: MagicMock) -> None:
        """Health check returns True in dev, False in production."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        assert await gw.health_check() is True

        mock_settings.return_value = _mock_settings(app_env="production")
        assert await gw.health_check() is False

    @pytest.mark.asyncio
    @patch("app.payments.gateways.dummy_gateway.get_settings")
    async def test_verify_webhook_signature(self, mock_settings: MagicMock) -> None:
        """Dummy gateway always returns True for signature."""
        mock_settings.return_value = _mock_settings()
        gw = DummyGateway()
        assert await gw.verify_webhook_signature(b"test", {}) is True


# ═══════════════════════════════════════════════════════════════════
# BANK TRANSFER GATEWAY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestBankTransferGateway:
    """Bank transfer manual flow tests."""

    def setup_method(self) -> None:
        """Clean up bank transfer records."""
        clear_bank_transfers()

    @pytest.mark.asyncio
    @patch("app.payments.gateways.bank_transfer.get_settings")
    async def test_generate_instructions(self, mock_settings: MagicMock) -> None:
        """Link generation returns human-readable bank details."""
        mock_settings.return_value = _mock_settings()
        gw = BankTransferGateway()
        result = await gw.generate_payment_link(
            amount_paisas=250000,
            reference_id="REF-BT-001",
            description="Order payment",
            payer_phone=_PHONE,
        )
        assert "Standard Chartered" in result.link_url
        assert "TELETRAAN" in result.link_url
        assert "2,500.00" in result.link_url
        assert result.gateway_order_id.startswith("BANK-")
        assert result.metadata["instructions_only"] is True

    @pytest.mark.asyncio
    @patch("app.payments.gateways.bank_transfer.get_settings")
    async def test_confirm_transfer(self, mock_settings: MagicMock) -> None:
        """Owner confirmation marks payment as successful."""
        mock_settings.return_value = _mock_settings()
        gw = BankTransferGateway()
        link = await gw.generate_payment_link(
            amount_paisas=100000,
            reference_id="REF-BT-002",
            description="Test",
            payer_phone=_PHONE,
        )
        result = await gw.process_callback({
            "order_id": link.gateway_order_id,
            "confirmed": True,
            "confirmed_by": "owner",
        })
        assert result.is_successful is True
        assert result.amount_paisas == 100000

    @pytest.mark.asyncio
    @patch("app.payments.gateways.bank_transfer.get_settings")
    async def test_reject_transfer(self, mock_settings: MagicMock) -> None:
        """Owner rejection marks payment as failed."""
        mock_settings.return_value = _mock_settings()
        gw = BankTransferGateway()
        link = await gw.generate_payment_link(
            amount_paisas=100000,
            reference_id="REF-BT-003",
            description="Test",
            payer_phone=_PHONE,
        )
        result = await gw.process_callback({
            "order_id": link.gateway_order_id,
            "confirmed": False,
            "confirmed_by": "owner",
        })
        assert result.is_successful is False

    @pytest.mark.asyncio
    @patch("app.payments.gateways.bank_transfer.get_settings")
    async def test_cancel_bank_transfer(self, mock_settings: MagicMock) -> None:
        """Pending bank transfer can be cancelled."""
        mock_settings.return_value = _mock_settings()
        gw = BankTransferGateway()
        link = await gw.generate_payment_link(
            amount_paisas=100000,
            reference_id="REF-BT-004",
            description="Test",
            payer_phone=_PHONE,
        )
        assert await gw.cancel_payment(link.gateway_order_id) is True

    @pytest.mark.asyncio
    async def test_verify_signature_always_true(self) -> None:
        """Bank transfer signature is always valid."""
        gw = BankTransferGateway()
        assert await gw.verify_webhook_signature(b"anything", {}) is True

    def test_gateway_metadata(self) -> None:
        """Metadata shows manual flow characteristics."""
        meta = BankTransferGateway().get_gateway_metadata()
        assert meta["is_manual"] is True
        assert meta["requires_screenshot"] is True

    @pytest.mark.asyncio
    @patch("app.payments.gateways.bank_transfer.get_settings")
    async def test_missing_bank_details_raises(self, mock_settings: MagicMock) -> None:
        """Missing bank details raises PaymentGatewayError."""
        mock_settings.return_value = _mock_settings(bank_account_name=None, bank_name=None)
        gw = BankTransferGateway()
        with pytest.raises(Exception, match="not configured"):
            await gw.generate_payment_link(
                amount_paisas=10000,
                reference_id="REF-FAIL",
                description="Test",
                payer_phone=_PHONE,
            )


# ═══════════════════════════════════════════════════════════════════
# JAZZCASH GATEWAY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestJazzCashGateway:
    """JazzCash gateway with mocked HTTP."""

    @pytest.mark.asyncio
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_generate_link(
        self, mock_settings: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        """Successful JazzCash link generation."""
        mock_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "pp_ResponseCode": "000",
            "pp_TxnRefNo": "JC-REF-001",
            "pp_PaymentURL": "https://jazzcash.com.pk/pay/JC-REF-001",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.generate_payment_link(
            amount_paisas=100000,
            reference_id="REF-JC-001",
            description="Order",
            payer_phone=_PHONE,
        )
        assert result.gateway_order_id == "JC-REF-001"
        assert "jazzcash" in result.link_url

    @pytest.mark.asyncio
    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_process_callback_success(self, mock_settings: MagicMock) -> None:
        """Successful JazzCash callback processing."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.process_callback({
            "pp_ResponseCode": "000",
            "pp_Amount": "150000",
            "pp_TxnRefNo": "JC-TXN-001",
            "pp_ResponseMessage": "Successful",
        })
        assert result.is_successful is True
        assert result.amount_paisas == 150000

    @pytest.mark.asyncio
    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_process_callback_failure(self, mock_settings: MagicMock) -> None:
        """Failed JazzCash callback."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.process_callback({
            "pp_ResponseCode": "124",
            "pp_Amount": "150000",
            "pp_TxnRefNo": "JC-TXN-002",
            "pp_ResponseMessage": "Insufficient funds",
        })
        assert result.is_successful is False
        assert result.failure_reason == "Insufficient funds"

    @pytest.mark.asyncio
    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_integrity_hash(self, mock_settings: MagicMock) -> None:
        """HMAC-SHA256 integrity hash computation."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        params = {"b_key": "b_val", "a_key": "a_val"}
        h = gw._compute_integrity_hash(params, "salt123")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    @patch("app.payments.gateways.jazzcash.get_settings")
    def test_cancel_not_supported(self, mock_settings: MagicMock) -> None:
        """JazzCash doesn't support cancellation."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        assert gw.get_gateway_metadata()["supports_cancellation"] is False

    def test_gateway_name(self) -> None:
        """Gateway name is 'jazzcash'."""
        from app.payments.gateways.jazzcash import JazzCashGateway

        assert JazzCashGateway().get_gateway_name() == "jazzcash"


# ═══════════════════════════════════════════════════════════════════
# EASYPAISA GATEWAY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestEasyPaisaGateway:
    """EasyPaisa gateway with mocked HTTP."""

    @pytest.mark.asyncio
    @patch("app.payments.gateways.easypaisa.get_settings")
    async def test_process_callback_success(self, mock_settings: MagicMock) -> None:
        """Successful EasyPaisa callback."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.process_callback({
            "responseCode": "0000",
            "transactionAmount": "1500.00",
            "transactionRefNumber": "EP-TXN-001",
            "orderRefNum": "REF-EP-001",
        })
        assert result.is_successful is True
        assert result.amount_paisas == 150000

    @pytest.mark.asyncio
    @patch("app.payments.gateways.easypaisa.get_settings")
    async def test_process_callback_failure(self, mock_settings: MagicMock) -> None:
        """Failed EasyPaisa callback."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.process_callback({
            "responseCode": "9999",
            "transactionAmount": "500.00",
            "transactionRefNumber": "EP-TXN-002",
            "responseDesc": "Transaction declined",
        })
        assert result.is_successful is False
        assert result.failure_reason == "Transaction declined"

    @pytest.mark.asyncio
    @patch("app.payments.gateways.easypaisa.get_settings")
    async def test_sha256_hash(self, mock_settings: MagicMock) -> None:
        """SHA256 hash computation."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        h = gw._compute_hash("STORE001", "1500.00", "REF-001", "hashkey123")
        expected = hashlib.sha256(
            "1500.00REF-001STORE001hashkey123".encode()
        ).hexdigest()
        assert h == expected

    def test_gateway_name(self) -> None:
        """Gateway name is 'easypaisa'."""
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        assert EasyPaisaGateway().get_gateway_name() == "easypaisa"


# ═══════════════════════════════════════════════════════════════════
# SAFEPAY GATEWAY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSafePayGateway:
    """SafePay gateway with mocked HTTP."""

    @pytest.mark.asyncio
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    @patch("app.payments.gateways.safepay.get_settings")
    async def test_generate_link(
        self, mock_settings: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        """Successful SafePay checkout session creation."""
        mock_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "tracker": {"token": "SP-TOKEN-001"},
                "checkout_url": "https://api.getsafepay.com/checkout/pay?token=SP-TOKEN-001",
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from app.payments.gateways.safepay import SafePayGateway

        gw = SafePayGateway()
        result = await gw.generate_payment_link(
            amount_paisas=200000,
            reference_id="REF-SP-001",
            description="Order",
            payer_phone=_PHONE,
        )
        assert result.gateway_order_id == "SP-TOKEN-001"
        assert "safepay" in result.link_url.lower() or "checkout" in result.link_url.lower()

    @pytest.mark.asyncio
    @patch("app.payments.gateways.safepay.get_settings")
    async def test_verify_webhook_signature(self, mock_settings: MagicMock) -> None:
        """HMAC-SHA256 signature verification."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.safepay import SafePayGateway

        gw = SafePayGateway()
        payload = b'{"type":"payment:created","data":{"amount":200000}}'
        secret = "sp_webhook_secret"
        signature = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        is_valid = await gw.verify_webhook_signature(
            payload, {"x-safepay-signature": signature}
        )
        assert is_valid is True

    @pytest.mark.asyncio
    @patch("app.payments.gateways.safepay.get_settings")
    async def test_verify_invalid_signature(self, mock_settings: MagicMock) -> None:
        """Invalid signature returns False."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.safepay import SafePayGateway

        gw = SafePayGateway()
        is_valid = await gw.verify_webhook_signature(
            b"payload", {"x-safepay-signature": "sha256=invalidhash"}
        )
        assert is_valid is False

    @pytest.mark.asyncio
    @patch("app.payments.gateways.safepay.get_settings")
    async def test_process_callback(self, mock_settings: MagicMock) -> None:
        """SafePay callback processing."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.safepay import SafePayGateway

        gw = SafePayGateway()
        result = await gw.process_callback({
            "type": "payment:created",
            "data": {
                "amount": 200000,
                "tracker": {"token": "SP-TOKEN-002"},
            },
        })
        assert result.is_successful is True
        assert result.amount_paisas == 200000

    def test_gateway_name(self) -> None:
        """Gateway name is 'safepay'."""
        from app.payments.gateways.safepay import SafePayGateway

        assert SafePayGateway().get_gateway_name() == "safepay"


# ═══════════════════════════════════════════════════════════════════
# NAYAPAY GATEWAY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestNayaPayGateway:
    """NayaPay gateway with mocked HTTP."""

    @pytest.mark.asyncio
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    @patch("app.payments.gateways.nayapay.get_settings")
    async def test_generate_link(
        self, mock_settings: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        """Successful NayaPay payment creation."""
        mock_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "paymentId": "NP-PAY-001",
                "paymentUrl": "https://nayapay.com/pay/NP-PAY-001",
                "qrCodeUrl": "https://nayapay.com/qr/NP-PAY-001",
                "deepLink": "nayapay://pay/NP-PAY-001",
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from app.payments.gateways.nayapay import NayaPayGateway

        gw = NayaPayGateway()
        result = await gw.generate_payment_link(
            amount_paisas=300000,
            reference_id="REF-NP-001",
            description="Subscription",
            payer_phone=_PHONE,
        )
        assert result.gateway_order_id == "NP-PAY-001"
        assert result.metadata["qr_code_url"] is not None

    @pytest.mark.asyncio
    @patch("app.payments.gateways.nayapay.get_settings")
    async def test_verify_webhook_signature(self, mock_settings: MagicMock) -> None:
        """HMAC-SHA256 signature verification for NayaPay."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.nayapay import NayaPayGateway

        gw = NayaPayGateway()
        payload = b'{"status":"completed","paymentId":"NP-001"}'
        secret = "np_secret_123"
        signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        is_valid = await gw.verify_webhook_signature(
            payload, {"x-signature": signature}
        )
        assert is_valid is True

    @pytest.mark.asyncio
    @patch("app.payments.gateways.nayapay.get_settings")
    async def test_process_callback_success(self, mock_settings: MagicMock) -> None:
        """Successful NayaPay callback."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.nayapay import NayaPayGateway

        gw = NayaPayGateway()
        result = await gw.process_callback({
            "status": "completed",
            "paymentId": "NP-PAY-002",
            "amount": 3000.00,
        })
        assert result.is_successful is True
        assert result.amount_paisas == 300000

    def test_gateway_name(self) -> None:
        """Gateway name is 'nayapay'."""
        from app.payments.gateways.nayapay import NayaPayGateway

        assert NayaPayGateway().get_gateway_name() == "nayapay"

    @patch("app.payments.gateways.nayapay.get_settings")
    def test_gateway_metadata(self, mock_settings: MagicMock) -> None:
        """NayaPay supports QR codes."""
        mock_settings.return_value = _mock_settings()
        from app.payments.gateways.nayapay import NayaPayGateway

        meta = NayaPayGateway().get_gateway_metadata()
        assert meta["supports_qr"] is True


# ═══════════════════════════════════════════════════════════════════
# FACTORY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestGatewayFactory:
    """Factory selection and caching tests."""

    def setup_method(self) -> None:
        """Clear factory cache."""
        from app.payments.factory import clear_gateway_cache

        clear_gateway_cache()

    @patch("app.payments.factory.get_settings")
    def test_default_gateway(self, mock_settings: MagicMock) -> None:
        """Default gateway from settings."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_gateway

        gw = get_gateway()
        assert gw.get_gateway_name() == "dummy"

    @patch("app.payments.factory.get_settings")
    def test_explicit_gateway(self, mock_settings: MagicMock) -> None:
        """Explicit gateway name override."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_gateway

        gw = get_gateway("jazzcash")
        assert gw.get_gateway_name() == "jazzcash"

    @patch("app.payments.factory.get_settings")
    def test_distributor_preferred(self, mock_settings: MagicMock) -> None:
        """Per-distributor gateway preference."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_gateway

        gw = get_gateway(distributor_preferred="safepay")
        assert gw.get_gateway_name() == "safepay"

    @patch("app.payments.factory.get_settings")
    def test_explicit_overrides_distributor(self, mock_settings: MagicMock) -> None:
        """Explicit name overrides distributor preference."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_gateway

        gw = get_gateway("nayapay", distributor_preferred="safepay")
        assert gw.get_gateway_name() == "nayapay"

    @patch("app.payments.factory.get_settings")
    def test_production_blocks_dummy(self, mock_settings: MagicMock) -> None:
        """Dummy gateway blocked in production."""
        mock_settings.return_value = _mock_settings(app_env="production")
        from app.payments.factory import get_gateway

        with pytest.raises(Exception, match="blocked in production"):
            get_gateway("dummy")

    @patch("app.payments.factory.get_settings")
    def test_unknown_gateway_raises(self, mock_settings: MagicMock) -> None:
        """Unknown gateway name raises."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_gateway

        with pytest.raises(Exception, match="Unknown payment gateway"):
            get_gateway("nonexistent")

    @patch("app.payments.factory.get_settings")
    def test_singleton_cache(self, mock_settings: MagicMock) -> None:
        """Same gateway name returns same instance."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_gateway

        gw1 = get_gateway("dummy")
        gw2 = get_gateway("dummy")
        assert gw1 is gw2

    @patch("app.payments.factory.get_settings")
    def test_available_gateways_production(self, mock_settings: MagicMock) -> None:
        """Available gateways excludes dummy in production."""
        mock_settings.return_value = _mock_settings(app_env="production")
        from app.payments.factory import get_available_gateways

        available = get_available_gateways()
        assert "dummy" not in available
        assert "jazzcash" in available

    @patch("app.payments.factory.get_settings")
    def test_available_gateways_dev(self, mock_settings: MagicMock) -> None:
        """Available gateways includes dummy in dev."""
        mock_settings.return_value = _mock_settings()
        from app.payments.factory import get_available_gateways

        available = get_available_gateways()
        assert "dummy" in available


# ═══════════════════════════════════════════════════════════════════
# WEBHOOK HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════


class TestWebhookHandler:
    """Webhook handler idempotency and lifecycle tests."""

    @pytest.mark.asyncio
    @patch("app.payments.webhook_handlers.audit_repo")
    @patch("app.payments.webhook_handlers.payment_repo")
    @patch("app.payments.webhook_handlers.get_gateway")
    async def test_successful_callback(
        self,
        mock_get_gateway: MagicMock,
        mock_payment_repo: MagicMock,
        mock_audit_repo: MagicMock,
    ) -> None:
        """Successful callback updates payment and creates audit."""
        mock_gw = AsyncMock(spec=PaymentGateway)
        mock_gw.verify_webhook_signature = AsyncMock(return_value=True)
        mock_gw.process_callback = AsyncMock(
            return_value=PaymentCallbackResult(
                is_successful=True,
                amount_paisas=150000,
                gateway_transaction_id="GW-TXN-001",
                raw_payload={"test": True},
            )
        )
        mock_get_gateway.return_value = mock_gw

        mock_payment_repo.get_by_gateway_transaction_id = AsyncMock(
            return_value=_make_payment()
        )
        mock_payment_repo.update = AsyncMock(return_value=_make_payment())
        mock_audit_repo.create = AsyncMock()

        from app.payments.webhook_handlers import handle_gateway_callback

        result = await handle_gateway_callback(
            "dummy", b"body", {"x-header": "val"}, {"test": True}
        )
        assert result.is_successful is True
        mock_payment_repo.update.assert_called_once()
        assert mock_audit_repo.create.call_count >= 1

    @pytest.mark.asyncio
    @patch("app.payments.webhook_handlers.audit_repo")
    @patch("app.payments.webhook_handlers.payment_repo")
    @patch("app.payments.webhook_handlers.get_gateway")
    async def test_duplicate_callback_ignored(
        self,
        mock_get_gateway: MagicMock,
        mock_payment_repo: MagicMock,
        mock_audit_repo: MagicMock,
    ) -> None:
        """Already completed payment skips re-processing."""
        mock_gw = AsyncMock(spec=PaymentGateway)
        mock_gw.verify_webhook_signature = AsyncMock(return_value=True)
        mock_gw.process_callback = AsyncMock(
            return_value=PaymentCallbackResult(
                is_successful=True,
                amount_paisas=150000,
                gateway_transaction_id="GW-TXN-DUPE",
                raw_payload={},
            )
        )
        mock_get_gateway.return_value = mock_gw

        # Existing payment already completed
        mock_payment_repo.get_by_gateway_transaction_id = AsyncMock(
            return_value=_make_payment(status=GatewayPaymentStatus.COMPLETED)
        )
        mock_audit_repo.create = AsyncMock()

        from app.payments.webhook_handlers import handle_gateway_callback

        result = await handle_gateway_callback("dummy", b"body", {}, {})
        assert result.is_successful is True
        # update should NOT be called for duplicate
        mock_payment_repo.update.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.payments.webhook_handlers.audit_repo")
    @patch("app.payments.webhook_handlers.payment_repo")
    @patch("app.payments.webhook_handlers.get_gateway")
    async def test_signature_failure(
        self,
        mock_get_gateway: MagicMock,
        mock_payment_repo: MagicMock,
        mock_audit_repo: MagicMock,
    ) -> None:
        """Failed signature returns failure result."""
        mock_gw = AsyncMock(spec=PaymentGateway)
        mock_gw.verify_webhook_signature = AsyncMock(return_value=False)
        mock_get_gateway.return_value = mock_gw
        mock_audit_repo.create = AsyncMock()

        from app.payments.webhook_handlers import handle_gateway_callback

        result = await handle_gateway_callback("jazzcash", b"body", {}, {})
        assert result.is_successful is False
        assert "signature" in (result.failure_reason or "").lower()


# ═══════════════════════════════════════════════════════════════════
# PAYMENT SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestPaymentService:
    """Payment service high-level tests."""

    def setup_method(self) -> None:
        """Clear caches."""
        clear_dummy_payments()
        from app.payments.factory import clear_gateway_cache

        clear_gateway_cache()

    @pytest.mark.asyncio
    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    @patch("app.payments.service.get_gateway")
    async def test_initiate_payment(
        self,
        mock_get_gateway: MagicMock,
        mock_payment_repo: MagicMock,
        mock_audit_repo: MagicMock,
    ) -> None:
        """Payment initiation creates DB record and returns link."""
        mock_gw = AsyncMock(spec=PaymentGateway)
        mock_gw.get_gateway_name = MagicMock(return_value="dummy")
        mock_gw.generate_payment_link = AsyncMock(
            return_value=PaymentLinkResponse(
                link_url="http://localhost/pay",
                gateway_order_id="GW-ORDER-001",
                expires_at=_NOW + timedelta(hours=1),
                metadata={"gateway": "dummy"},
            )
        )
        mock_get_gateway.return_value = mock_gw

        mock_payment_repo.create = AsyncMock(return_value=_make_payment())
        mock_audit_repo.create = AsyncMock()

        from app.payments.service import PaymentService

        svc = PaymentService()
        payment, link = await svc.initiate_payment(
            amount_paisas=150000,
            payment_type=PaymentType.ORDER_PAYMENT,
            payer_phone=_PHONE,
            description="Order #100",
            distributor_id=_DIST_ID,
        )
        assert payment.id == _PAYMENT_ID
        assert link.gateway_order_id == "GW-ORDER-001"
        mock_payment_repo.create.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.payments.service.payment_repo")
    async def test_check_status(self, mock_payment_repo: MagicMock) -> None:
        """Status check returns payment record."""
        mock_payment_repo.get_by_id = AsyncMock(return_value=_make_payment())

        from app.payments.service import PaymentService

        svc = PaymentService()
        payment = await svc.check_status(str(_PAYMENT_ID))
        assert payment.status == GatewayPaymentStatus.PENDING

    @pytest.mark.asyncio
    @patch("app.payments.service.payment_repo")
    async def test_cancel_payment(self, mock_payment_repo: MagicMock) -> None:
        """Pending payment can be cancelled."""
        mock_payment_repo.get_by_id = AsyncMock(return_value=_make_payment())
        mock_payment_repo.update = AsyncMock(
            return_value=_make_payment(status=GatewayPaymentStatus.CANCELLED)
        )

        from app.payments.service import PaymentService

        svc = PaymentService()
        result = await svc.cancel_payment(str(_PAYMENT_ID))
        assert result is True

    @pytest.mark.asyncio
    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    async def test_confirm_bank_transfer(
        self,
        mock_payment_repo: MagicMock,
        mock_audit_repo: MagicMock,
    ) -> None:
        """Bank transfer confirmation updates status."""
        mock_payment_repo.get_by_id = AsyncMock(
            return_value=_make_payment(gateway=GatewayType.BANK_TRANSFER)
        )
        mock_payment_repo.update = AsyncMock(
            return_value=_make_payment(
                gateway=GatewayType.BANK_TRANSFER,
                status=GatewayPaymentStatus.COMPLETED,
            )
        )
        mock_audit_repo.create = AsyncMock()

        from app.payments.service import PaymentService

        svc = PaymentService()
        payment = await svc.confirm_bank_transfer(
            str(_PAYMENT_ID), confirmed_by="owner-123"
        )
        assert payment.status == GatewayPaymentStatus.COMPLETED

    @pytest.mark.asyncio
    @patch("app.payments.service.payment_repo")
    async def test_expire_stale_payments(
        self, mock_payment_repo: MagicMock
    ) -> None:
        """Expired payments get status updated."""
        stale = [
            _make_payment(id=UUID(f"{'1' * 8}-{'1' * 4}-{'1' * 4}-{'1' * 4}-{'1' * 12}")),
            _make_payment(id=UUID(f"{'2' * 8}-{'2' * 4}-{'2' * 4}-{'2' * 4}-{'2' * 12}")),
        ]
        mock_payment_repo.get_pending_expired = AsyncMock(return_value=stale)
        mock_payment_repo.update = AsyncMock(return_value=_make_payment())

        from app.payments.service import PaymentService

        svc = PaymentService()
        count = await svc.expire_stale_payments()
        assert count == 2
        assert mock_payment_repo.update.call_count == 2

    @pytest.mark.asyncio
    @patch("app.payments.service.payment_repo")
    async def test_check_status_not_found(self, mock_payment_repo: MagicMock) -> None:
        """Non-existent payment raises."""
        mock_payment_repo.get_by_id = AsyncMock(return_value=None)

        from app.payments.service import PaymentService

        svc = PaymentService()
        with pytest.raises(Exception, match="not found"):
            await svc.check_status("nonexistent-id")
