"""Tests for real payment gateways – coverage boost.

Covers EasyPaisa, JazzCash, NayaPay, SafePay gateways and PaymentService
uncovered branches.

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides: object) -> MagicMock:
    """Create a minimal mock settings object for gateways."""
    s = MagicMock()
    # Shared
    s.payment_callback_base_url = "https://cb.example.com"
    s.payment_link_expiry_minutes = 30
    s.app_env = "development"
    # EasyPaisa
    s.easypaisa_store_id = "EP-STORE"
    s.easypaisa_hash_key = "ep-hash-secret"
    s.easypaisa_api_url = "https://ep.example.com"
    # JazzCash
    s.jazzcash_merchant_id = "JC-MERCH"
    s.jazzcash_password = "jc-pass"
    s.jazzcash_integrity_salt = "jc-salt"
    s.jazzcash_api_url = "https://jc.example.com"
    # NayaPay
    s.nayapay_merchant_id = "NP-MERCH"
    s.nayapay_api_key = "np-key"
    s.nayapay_secret = "np-secret"
    s.nayapay_api_url = "https://np.example.com"
    # SafePay
    s.safepay_api_key = "sp-key"
    s.safepay_secret_key = "sp-secret"
    s.safepay_api_url = "https://sp.example.com"
    s.safepay_webhook_secret = "sp-webhook"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _httpx_ctx(response: MagicMock | None = None) -> tuple[MagicMock, AsyncMock, MagicMock]:
    """Build mock httpx.AsyncClient context manager.

    Returns (ctx_manager, client, response).
    """
    resp = response or MagicMock()
    resp.status_code = getattr(resp, "status_code", 200)
    resp.raise_for_status = MagicMock()
    resp.is_redirect = False

    client = AsyncMock()
    client.post.return_value = resp
    client.get.return_value = resp
    client.delete.return_value = resp

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)

    return ctx, client, resp


# ═══════════════════════════════════════════════════════════════════════════
# EasyPaisa
# ═══════════════════════════════════════════════════════════════════════════


class TestEasyPaisaGateway:
    """EasyPaisaGateway unit tests."""

    EP = "app.payments.gateways.easypaisa"

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    async def test_get_credentials_missing(self, gs: MagicMock) -> None:
        gs.return_value = _settings(easypaisa_store_id="")
        from app.payments.gateways.easypaisa import EasyPaisaGateway
        from app.core.exceptions import PaymentGatewayError

        gw = EasyPaisaGateway()
        with pytest.raises(PaymentGatewayError):
            gw._get_credentials()

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_generate_link_json_response(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.is_redirect = False
        resp.json.return_value = {
            "paymentUrl": "https://ep.example.com/pay/99",
            "transactionRefNumber": "EP-TXN-99",
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.generate_payment_link(100_000, "REF-1", "Desc", "+923001234567")
        assert result.link_url == "https://ep.example.com/pay/99"
        assert result.gateway_order_id == "EP-TXN-99"

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_generate_link_non_json_fallback(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.is_redirect = False
        resp.json.side_effect = ValueError("not json")
        resp.url = "https://ep.example.com/easypay/Index.jsf"
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.generate_payment_link(50_000, "REF-2", "Desc", "+923001234567")
        assert result.gateway_order_id == "REF-2"

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_generate_link_http_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        client = AsyncMock()
        client.post.side_effect = httpx.HTTPError("connection refused")
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway
        from app.core.exceptions import PaymentGatewayError

        gw = EasyPaisaGateway()
        with pytest.raises(PaymentGatewayError, match="API request failed"):
            await gw.generate_payment_link(100_000, "REF-E", "Desc", "+923001234567")

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    async def test_verify_webhook_valid(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        # Compute expected hash: SHA256(amount + order_id + store_id + hash_key)
        store_id, hash_key = "EP-STORE", "ep-hash-secret"
        amount, ref = "1000.00", "REF-V"
        raw = f"{amount}{ref}{store_id}{hash_key}"
        expected = hashlib.sha256(raw.encode()).hexdigest()

        body = json.dumps({
            "hash": expected,
            "amount": amount,
            "orderRefNum": ref,
        }).encode()

        ok = await gw.verify_webhook_signature(body, {})
        assert ok is True

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    async def test_verify_webhook_missing_hash(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        body = json.dumps({"amount": "100"}).encode()
        ok = await gw.verify_webhook_signature(body, {})
        assert ok is False

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    async def test_verify_webhook_bad_hash(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        body = json.dumps({
            "hash": "bad-hash",
            "amount": "100",
            "orderRefNum": "REF",
        }).encode()
        ok = await gw.verify_webhook_signature(body, {})
        assert ok is False

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    async def test_verify_webhook_url_encoded(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        store_id, hash_key = "EP-STORE", "ep-hash-secret"
        raw = f"500.00ORDER-1{store_id}{hash_key}"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        body = f"merchantHashedReq={expected}&amount=500.00&orderRefNum=ORDER-1".encode()
        ok = await gw.verify_webhook_signature(body, {})
        assert ok is True

    async def test_process_callback_success(self) -> None:
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.process_callback({
            "responseCode": "0000",
            "transactionAmount": "500.00",
            "transactionRefNumber": "EP-TXN-1",
        })
        assert result.is_successful is True
        assert result.amount_paisas == 50_000
        assert result.gateway_transaction_id == "EP-TXN-1"
        assert result.failure_reason is None

    async def test_process_callback_failure(self) -> None:
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.process_callback({
            "responseCode": "9999",
            "amount": "invalid",
            "orderRefNum": "EP-FAIL",
            "responseDesc": "Transaction declined",
        })
        assert result.is_successful is False
        assert result.amount_paisas == 0
        assert result.failure_reason == "Transaction declined"

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_get_payment_status_completed(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "responseCode": "0000",
            "transactionAmount": "200.50",
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.get_payment_status("EP-TXN-S")
        assert result.status == "completed"
        assert result.amount_paisas == 20_050
        assert result.paid_at is not None

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_get_payment_status_pending(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"responseCode": "0002"}
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        result = await gw.get_payment_status("EP-TXN-P")
        assert result.status == "pending"
        assert result.paid_at is None

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_get_payment_status_http_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        client = AsyncMock()
        client.post.side_effect = httpx.HTTPError("timeout")
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway
        from app.core.exceptions import PaymentGatewayError

        gw = EasyPaisaGateway()
        with pytest.raises(PaymentGatewayError, match="status query failed"):
            await gw.get_payment_status("EP-TXN-X")

    async def test_cancel_always_false(self) -> None:
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        gw = EasyPaisaGateway()
        assert await gw.cancel_payment("EP-TXN") is False

    def test_gateway_name(self) -> None:
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        assert EasyPaisaGateway().get_gateway_name() == "easypaisa"

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    def test_gateway_metadata(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.easypaisa import EasyPaisaGateway

        meta = EasyPaisaGateway().get_gateway_metadata()
        assert meta["auth_method"] == "SHA256"
        assert meta["supports_cancellation"] is False

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_health_check_ok(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway

        assert await EasyPaisaGateway().health_check() is True

    @patch(f"app.payments.gateways.easypaisa.get_settings")
    @patch("app.payments.gateways.easypaisa.httpx.AsyncClient")
    async def test_health_check_fail(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("down"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.easypaisa import EasyPaisaGateway

        assert await EasyPaisaGateway().health_check() is False


# ═══════════════════════════════════════════════════════════════════════════
# JazzCash
# ═══════════════════════════════════════════════════════════════════════════


class TestJazzCashGateway:
    """JazzCashGateway unit tests."""

    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_get_credentials_missing(self, gs: MagicMock) -> None:
        gs.return_value = _settings(jazzcash_merchant_id="")
        from app.payments.gateways.jazzcash import JazzCashGateway
        from app.core.exceptions import PaymentGatewayError

        with pytest.raises(PaymentGatewayError):
            JazzCashGateway()._get_credentials()

    @patch("app.payments.gateways.jazzcash.get_settings")
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    async def test_generate_link_success(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "pp_ResponseCode": "000",
            "pp_TxnRefNo": "JC-REF-1",
            "pp_PaymentURL": "https://jc.example.com/pay/1",
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.generate_payment_link(200_000, "REF-JC", "Test", "+923001234567")
        assert "jc.example.com" in result.link_url or "pay" in result.link_url

    @patch("app.payments.gateways.jazzcash.get_settings")
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    async def test_generate_link_api_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "pp_ResponseCode": "999",
            "pp_ResponseMessage": "Invalid merchant",
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.jazzcash import JazzCashGateway
        from app.core.exceptions import PaymentGatewayError

        gw = JazzCashGateway()
        with pytest.raises(PaymentGatewayError):
            await gw.generate_payment_link(100_000, "REF-JCE", "Test", "+923001234567")

    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_verify_webhook_valid(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        salt = "jc-salt"
        params = {"pp_Amount": "100000", "pp_TxnRefNo": "REF-1"}

        # Compute expected integrity hash
        sorted_items = sorted(params.items())
        message_parts = [v for _, v in sorted_items if v]
        message = salt + "&" + "&".join(message_parts)
        computed = hmac.new(salt.encode(), message.encode(), hashlib.sha256).hexdigest()

        body_dict = {**params, "pp_SecureHash": computed}
        body = json.dumps(body_dict).encode()
        ok = await gw.verify_webhook_signature(body, {})
        assert ok is True

    @patch("app.payments.gateways.jazzcash.get_settings")
    async def test_verify_webhook_missing_hash(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        body = json.dumps({"pp_Amount": "100"}).encode()
        assert await gw.verify_webhook_signature(body, {}) is False

    async def test_process_callback_success(self) -> None:
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.process_callback({
            "pp_ResponseCode": "000",
            "pp_Amount": "100000",
            "pp_TxnRefNo": "JC-TXN-1",
        })
        assert result.is_successful is True
        assert result.amount_paisas == 100_000

    async def test_process_callback_failure(self) -> None:
        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.process_callback({
            "pp_ResponseCode": "124",
            "pp_ResponseMessage": "Insufficient balance",
            "pp_TxnRefNo": "JC-FAIL",
        })
        assert result.is_successful is False

    @patch("app.payments.gateways.jazzcash.get_settings")
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    async def test_get_payment_status_completed(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "pp_ResponseCode": "000",
            "pp_Amount": "200000",
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.jazzcash import JazzCashGateway

        gw = JazzCashGateway()
        result = await gw.get_payment_status("JC-TXN-S")
        assert result.status == "completed"
        assert result.amount_paisas == 200_000

    @patch("app.payments.gateways.jazzcash.get_settings")
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    async def test_get_payment_status_pending(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"pp_ResponseCode": "124"}
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.jazzcash import JazzCashGateway

        result = await JazzCashGateway().get_payment_status("JC-TXN-P")
        assert result.status == "pending"

    async def test_cancel_always_false(self) -> None:
        from app.payments.gateways.jazzcash import JazzCashGateway

        assert await JazzCashGateway().cancel_payment("JC-TXN") is False

    def test_gateway_name(self) -> None:
        from app.payments.gateways.jazzcash import JazzCashGateway

        assert JazzCashGateway().get_gateway_name() == "jazzcash"

    @patch("app.payments.gateways.jazzcash.get_settings")
    def test_gateway_metadata(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.jazzcash import JazzCashGateway

        meta = JazzCashGateway().get_gateway_metadata()
        assert meta["auth_method"] == "HMAC-SHA256"

    @patch("app.payments.gateways.jazzcash.get_settings")
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    async def test_health_check_ok(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.jazzcash import JazzCashGateway

        assert await JazzCashGateway().health_check() is True

    @patch("app.payments.gateways.jazzcash.get_settings")
    @patch("app.payments.gateways.jazzcash.httpx.AsyncClient")
    async def test_health_check_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("fail"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.jazzcash import JazzCashGateway

        assert await JazzCashGateway().health_check() is False


# ═══════════════════════════════════════════════════════════════════════════
# NayaPay
# ═══════════════════════════════════════════════════════════════════════════


class TestNayaPayGateway:
    """NayaPayGateway unit tests."""

    @patch("app.payments.gateways.nayapay.get_settings")
    async def test_get_credentials_missing(self, gs: MagicMock) -> None:
        gs.return_value = _settings(nayapay_api_key="")
        from app.payments.gateways.nayapay import NayaPayGateway
        from app.core.exceptions import PaymentGatewayError

        with pytest.raises(PaymentGatewayError):
            NayaPayGateway()._get_credentials()

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_generate_link_success(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "data": {
                "paymentId": "NP-PAY-1",
                "paymentUrl": "https://np.example.com/pay/1",
            },
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway

        gw = NayaPayGateway()
        result = await gw.generate_payment_link(300_000, "REF-NP", "Test", "+923001234567")
        assert result.gateway_order_id == "NP-PAY-1"
        assert "np.example.com" in result.link_url

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_generate_link_http_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        client = AsyncMock()
        client.post.side_effect = httpx.HTTPError("timeout")
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway
        from app.core.exceptions import PaymentGatewayError

        with pytest.raises(PaymentGatewayError):
            await NayaPayGateway().generate_payment_link(100_000, "REF-E", "X", "+923001234567")

    @patch("app.payments.gateways.nayapay.get_settings")
    async def test_verify_webhook_valid(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.nayapay import NayaPayGateway

        gw = NayaPayGateway()
        body = b'{"status":"completed"}'
        sig = hmac.new(b"np-secret", body, hashlib.sha256).hexdigest()

        ok = await gw.verify_webhook_signature(body, {"X-Signature": sig})
        assert ok is True

    @patch("app.payments.gateways.nayapay.get_settings")
    async def test_verify_webhook_missing_sig(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.nayapay import NayaPayGateway

        ok = await NayaPayGateway().verify_webhook_signature(b"body", {})
        assert ok is False

    async def test_process_callback_success(self) -> None:
        from app.payments.gateways.nayapay import NayaPayGateway

        result = await NayaPayGateway().process_callback({
            "status": "completed",
            "amount": 1500.00,
            "paymentId": "NP-TXN-1",
        })
        assert result.is_successful is True
        assert result.amount_paisas == 150_000

    async def test_process_callback_failure(self) -> None:
        from app.payments.gateways.nayapay import NayaPayGateway

        result = await NayaPayGateway().process_callback({
            "status": "failed",
            "amount": 0,
            "transactionId": "NP-FAIL",
            "failureReason": "Declined",
        })
        assert result.is_successful is False

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_get_payment_status(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "data": {
                "status": "completed",
                "amount": 500.00,
                "completedAt": datetime.now(tz=timezone.utc).isoformat(),
            },
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway

        result = await NayaPayGateway().get_payment_status("NP-TXN-S")
        assert result.status == "completed"
        assert result.amount_paisas == 50_000

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_get_payment_status_pending(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"data": {"status": "pending", "amount": 100}}
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway

        result = await NayaPayGateway().get_payment_status("NP-P")
        assert result.status == "pending"

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_cancel_payment_success(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway

        assert await NayaPayGateway().cancel_payment("NP-C") is True

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_cancel_payment_failure(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 400
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway

        assert await NayaPayGateway().cancel_payment("NP-CF") is False

    def test_gateway_name(self) -> None:
        from app.payments.gateways.nayapay import NayaPayGateway

        assert NayaPayGateway().get_gateway_name() == "nayapay"

    @patch("app.payments.gateways.nayapay.get_settings")
    def test_gateway_metadata(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.nayapay import NayaPayGateway

        meta = NayaPayGateway().get_gateway_metadata()
        assert meta["supports_cancellation"] is True

    @patch("app.payments.gateways.nayapay.get_settings")
    @patch("app.payments.gateways.nayapay.httpx.AsyncClient")
    async def test_health_check(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.nayapay import NayaPayGateway

        assert await NayaPayGateway().health_check() is True


# ═══════════════════════════════════════════════════════════════════════════
# SafePay
# ═══════════════════════════════════════════════════════════════════════════


class TestSafePayGateway:
    """SafePayGateway unit tests."""

    @patch("app.payments.gateways.safepay.get_settings")
    async def test_get_credentials_missing(self, gs: MagicMock) -> None:
        gs.return_value = _settings(safepay_api_key="")
        from app.payments.gateways.safepay import SafePayGateway
        from app.core.exceptions import PaymentGatewayError

        with pytest.raises(PaymentGatewayError):
            SafePayGateway()._get_credentials()

    @patch("app.payments.gateways.safepay.get_settings")
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    async def test_generate_link_success(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "data": {
                "tracker": {"token": "SP-TOKEN-1"},
                "checkout_url": "https://sp.example.com/checkout/1",
            },
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.safepay import SafePayGateway

        gw = SafePayGateway()
        result = await gw.generate_payment_link(400_000, "REF-SP", "Test", "+923001234567")
        assert result.gateway_order_id == "SP-TOKEN-1"
        assert "sp.example.com" in result.link_url

    @patch("app.payments.gateways.safepay.get_settings")
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    async def test_generate_link_http_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        client = AsyncMock()
        client.post.side_effect = httpx.HTTPError("fail")
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.safepay import SafePayGateway
        from app.core.exceptions import PaymentGatewayError

        with pytest.raises(PaymentGatewayError):
            await SafePayGateway().generate_payment_link(100_000, "REF-E", "X", "+923001234567")

    @patch("app.payments.gateways.safepay.get_settings")
    async def test_verify_webhook_valid(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.safepay import SafePayGateway

        body = b'{"type":"payment.completed"}'
        sig = "sha256=" + hmac.new(b"sp-webhook", body, hashlib.sha256).hexdigest()
        ok = await SafePayGateway().verify_webhook_signature(body, {"X-Safepay-Signature": sig})
        assert ok is True

    @patch("app.payments.gateways.safepay.get_settings")
    async def test_verify_webhook_invalid(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.safepay import SafePayGateway

        ok = await SafePayGateway().verify_webhook_signature(
            b"body", {"X-Safepay-Signature": "sha256=bad"}
        )
        assert ok is False

    @patch("app.payments.gateways.safepay.get_settings")
    async def test_verify_webhook_missing_sig(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.safepay import SafePayGateway

        ok = await SafePayGateway().verify_webhook_signature(b"body", {})
        assert ok is False

    async def test_process_callback_success(self) -> None:
        from app.payments.gateways.safepay import SafePayGateway

        result = await SafePayGateway().process_callback({
            "type": "payment.completed",
            "data": {
                "amount": 500_000,
                "tracker": {"token": "SP-TXN-1"},
            },
        })
        assert result.is_successful is True
        assert result.amount_paisas == 500_000

    async def test_process_callback_failure(self) -> None:
        from app.payments.gateways.safepay import SafePayGateway

        result = await SafePayGateway().process_callback({
            "type": "payment.failed",
            "data": {"amount": 0, "reference_code": "SP-FAIL"},
        })
        assert result.is_successful is False

    @patch("app.payments.gateways.safepay.get_settings")
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    async def test_get_payment_status(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "data": {
                "state": "tracker:received",
                "amount": 300_000,
            },
        }
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.safepay import SafePayGateway

        result = await SafePayGateway().get_payment_status("SP-TXN-S")
        assert result.status == "completed"
        assert result.amount_paisas == 300_000

    @patch("app.payments.gateways.safepay.get_settings")
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    async def test_cancel_payment_success(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.safepay import SafePayGateway

        assert await SafePayGateway().cancel_payment("SP-C") is True

    @patch("app.payments.gateways.safepay.get_settings")
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    async def test_cancel_payment_http_error(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        ctx = MagicMock()
        client = AsyncMock()
        client.delete.side_effect = httpx.HTTPError("fail")
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)
        hx.return_value = ctx

        from app.payments.gateways.safepay import SafePayGateway

        assert await SafePayGateway().cancel_payment("SP-CF") is False

    def test_gateway_name(self) -> None:
        from app.payments.gateways.safepay import SafePayGateway

        assert SafePayGateway().get_gateway_name() == "safepay"

    @patch("app.payments.gateways.safepay.get_settings")
    def test_gateway_metadata(self, gs: MagicMock) -> None:
        gs.return_value = _settings()
        from app.payments.gateways.safepay import SafePayGateway

        meta = SafePayGateway().get_gateway_metadata()
        assert meta["supports_refunds"] is True

    @patch("app.payments.gateways.safepay.get_settings")
    @patch("app.payments.gateways.safepay.httpx.AsyncClient")
    async def test_health_check(self, hx: MagicMock, gs: MagicMock) -> None:
        gs.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        ctx, _, _ = _httpx_ctx(resp)
        hx.return_value = ctx

        from app.payments.gateways.safepay import SafePayGateway

        assert await SafePayGateway().health_check() is True


# ═══════════════════════════════════════════════════════════════════════════
# Payment Service uncovered branches
# ═══════════════════════════════════════════════════════════════════════════


class TestPaymentServiceBranches:
    """Cover payment_service.py uncovered branches."""

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    @patch("app.payments.service.get_gateway")
    async def test_initiate_invalid_gateway_fallback(
        self,
        mock_gw: MagicMock,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L87-88: invalid gateway name falls back to MANUAL."""
        from app.payments.service import payment_service
        from app.payments.base import PaymentLinkResponse
        from app.core.constants import PaymentType

        mock_link = PaymentLinkResponse(
            link_url="https://pay.example.com",
            gateway_order_id="GW-1",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
            metadata={},
        )
        gw_instance = AsyncMock()
        gw_instance.generate_payment_link.return_value = mock_link
        mock_gw.return_value = gw_instance

        mock_pr.create = AsyncMock(return_value=MagicMock(id="PAY-1"))
        mock_ar.create = AsyncMock(return_value=None)

        payment, link = await payment_service.initiate_payment(
            amount_paisas=100_000,
            payment_type=PaymentType.ORDER_PAYMENT,
            payer_phone="+923001234567",
            description="Test",
            distributor_id="00000000-0000-0000-0000-000000000001",
            order_id="00000000-0000-0000-0000-000000000002",
            gateway_name="totally_invalid_gateway",
        )
        assert link.link_url == "https://pay.example.com"

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    @patch("app.payments.service.get_gateway")
    async def test_check_status_poll_gateway(
        self,
        mock_gw: MagicMock,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L171-189, 211-216: poll_gateway branch."""
        from app.payments.service import payment_service
        from app.payments.base import PaymentStatusResult

        mock_payment = MagicMock()
        mock_payment.id = "PAY-2"
        mock_payment.status = "pending"
        mock_payment.gateway = MagicMock()
        mock_payment.gateway.value = "dummy"
        mock_payment.gateway_transaction_id = "GW-TXN-2"
        mock_payment.distributor_id = "dist-1"
        mock_pr.get_by_id = AsyncMock(return_value=mock_payment)
        mock_pr.update = AsyncMock(return_value=mock_payment)
        mock_ar.create = AsyncMock(return_value=None)

        gw_instance = AsyncMock()
        gw_instance.get_payment_status.return_value = PaymentStatusResult(
            status="completed",
            gateway_transaction_id="GW-TXN-2",
            amount_paisas=100_000,
            paid_at=datetime.now(tz=timezone.utc),
            raw_response={},
        )
        mock_gw.return_value = gw_instance

        result = await payment_service.check_status("PAY-2", poll_gateway=True)
        assert result is not None

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    async def test_check_status_not_found(
        self,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L208: payment not found raises."""
        from app.payments.service import payment_service
        from app.core.exceptions import PaymentGatewayError

        mock_pr.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(PaymentGatewayError):
            await payment_service.check_status("PAY-MISSING")

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    @patch("app.payments.service.get_gateway")
    async def test_cancel_payment_not_found(
        self,
        mock_gw: MagicMock,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L269: payment not found returns False."""
        from app.payments.service import payment_service

        mock_pr.get_by_id = AsyncMock(return_value=None)
        assert await payment_service.cancel_payment("PAY-NONE") is False

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    @patch("app.payments.service.get_gateway")
    async def test_cancel_payment_not_pending(
        self,
        mock_gw: MagicMock,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L275: non-pending payment returns False."""
        from app.payments.service import payment_service

        mock_payment = MagicMock()
        mock_payment.status = MagicMock()
        mock_payment.status.value = "completed"
        mock_payment.status.__eq__ = lambda self, other: self.value == other
        mock_pr.get_by_id = AsyncMock(return_value=mock_payment)

        assert await payment_service.cancel_payment("PAY-DONE") is False

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    async def test_confirm_bank_transfer_not_found(
        self,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L331-332: payment not found raises."""
        from app.payments.service import payment_service
        from app.core.exceptions import PaymentGatewayError

        mock_pr.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(PaymentGatewayError):
            await payment_service.confirm_bank_transfer("PAY-NONE", "admin")

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    async def test_confirm_bank_transfer_wrong_gateway(
        self,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L368-369: non-bank_transfer gateway raises."""
        from app.payments.service import payment_service
        from app.core.exceptions import PaymentGatewayError
        from app.core.constants import GatewayType

        mock_payment = MagicMock()
        mock_payment.id = "PAY-3"
        mock_payment.gateway = GatewayType.JAZZCASH
        mock_payment.status = "pending"
        mock_pr.get_by_id = AsyncMock(return_value=mock_payment)

        with pytest.raises(PaymentGatewayError):
            await payment_service.confirm_bank_transfer("PAY-3", "admin")

    @patch("app.payments.service.audit_repo")
    @patch("app.payments.service.payment_repo")
    async def test_confirm_bank_transfer_success(
        self,
        mock_pr: MagicMock,
        mock_ar: MagicMock,
    ) -> None:
        """L385-396: happy path bank transfer confirmation."""
        from app.payments.service import payment_service
        from app.core.constants import GatewayType

        mock_payment = MagicMock()
        mock_payment.id = "PAY-4"
        mock_payment.gateway = GatewayType.BANK_TRANSFER
        mock_payment.status = "pending"
        mock_payment.distributor_id = "dist-1"
        mock_payment.metadata = {}
        mock_pr.get_by_id = AsyncMock(return_value=mock_payment)
        mock_pr.update = AsyncMock(return_value=mock_payment)
        mock_ar.create = AsyncMock(return_value=None)

        result = await payment_service.confirm_bank_transfer(
            "PAY-4", "admin-user", screenshot_path="/uploads/proof.jpg"
        )
        assert result is not None
        mock_pr.update.assert_called_once()
