"""Tests for API routes — health, webhook, payments.

Uses FastAPI TestClient for integration-style coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _mock_settings() -> MagicMock:
    """Return settings mock with all required fields."""
    s = MagicMock()
    s.meta_verify_token = "test-verify-token"
    s.meta_app_secret = "test-app-secret"
    s.admin_api_key = "test-admin-key"
    s.meta_api_version = "v19.0"
    s.meta_api_base_url = "https://graph.facebook.com"
    s.encryption_key = "x" * 44
    s.supabase_url = "https://test.supabase.co"
    s.supabase_service_role_key = "test-key"
    s.owner_phone_number_id = "owner_pnid"
    s.owner_whatsapp_number = "+923001234567"
    return s


def _get_app():
    """Create FastAPI app with mocked dependencies for testing."""
    with patch("app.core.config.get_settings", return_value=_mock_settings()):
        from app.api.health import router as health_router
        from app.api.webhook import router as webhook_router
        from app.api.payments import router as payments_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(health_router)
        app.include_router(webhook_router)
        app.include_router(payments_router)
        return app


# ═══════════════════════════════════════════════════════════════
# HEALTH ENDPOINT
# ═══════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_ok(self) -> None:
        with patch(
            "app.api.health.db_health_check",
            new_callable=AsyncMock,
            return_value=True,
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in ("healthy", "ok")

    def test_health_db_down(self) -> None:
        with patch(
            "app.api.health.db_health_check",
            new_callable=AsyncMock,
            return_value=False,
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code in (200, 503)


# ═══════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestWebhookVerification:
    """Test GET /api/webhook (Meta verification challenge)."""

    def test_verify_webhook_success(self) -> None:
        with patch(
            "app.api.webhook.get_settings",
            return_value=_mock_settings(),
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.get(
                "/api/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "test_challenge_123",
                    "hub.verify_token": "test-verify-token",
                },
            )
            assert resp.status_code == 200
            assert resp.text == "test_challenge_123"

    def test_verify_webhook_wrong_token(self) -> None:
        with patch(
            "app.api.webhook.get_settings",
            return_value=_mock_settings(),
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.get(
                "/api/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "test_challenge_123",
                    "hub.verify_token": "wrong-token",
                },
            )
            assert resp.status_code == 403

    def test_verify_webhook_wrong_mode(self) -> None:
        with patch(
            "app.api.webhook.get_settings",
            return_value=_mock_settings(),
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.get(
                "/api/webhook",
                params={
                    "hub.mode": "unsubscribe",
                    "hub.challenge": "test_challenge_123",
                    "hub.verify_token": "test-verify-token",
                },
            )
            assert resp.status_code == 403


class TestWebhookPost:
    """Test POST /api/webhook (message ingestion)."""

    def test_invalid_signature_returns_400(self) -> None:
        with patch(
            "app.api.webhook.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.api.webhook.verify_meta_signature",
            return_value=False,
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.post(
                "/api/webhook",
                json={"object": "whatsapp_business_account", "entry": []},
                headers={"X-Hub-Signature-256": "sha256=invalid"},
            )
            assert resp.status_code == 400

    def test_valid_signature_returns_200(self) -> None:
        mock_result = MagicMock()
        mock_result.messages = []
        mock_result.statuses = []
        with patch(
            "app.api.webhook.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.api.webhook.verify_meta_signature",
            return_value=True,
        ), patch(
            "app.api.webhook.parse_webhook_payload",
            return_value=mock_result,
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.post(
                "/api/webhook",
                json={"object": "whatsapp_business_account", "entry": []},
                headers={"X-Hub-Signature-256": "sha256=valid"},
            )
            assert resp.status_code == 200

    def test_non_whatsapp_object_returns_200(self) -> None:
        with patch(
            "app.api.webhook.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "app.api.webhook.verify_meta_signature",
            return_value=True,
        ):
            app = _get_app()
            client = TestClient(app)
            resp = client.post(
                "/api/webhook",
                json={"object": "page", "entry": []},
                headers={"X-Hub-Signature-256": "sha256=test"},
            )
            assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# PAYMENTS ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestPaymentCallbacks:
    """Test payment callback endpoints."""

    @pytest.fixture
    def _app(self) -> TestClient:
        app = _get_app()
        return TestClient(app)

    def test_jazzcash_callback(self, _app: TestClient) -> None:
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            resp = _app.post(
                "/api/payments/jazzcash/callback",
                json={"pp_TxnRefNo": "T123"},
            )
            assert resp.status_code == 200

    def test_easypaisa_callback(self, _app: TestClient) -> None:
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            resp = _app.post(
                "/api/payments/easypaisa/callback",
                json={"transactionId": "T123"},
            )
            assert resp.status_code == 200

    def test_safepay_callback(self, _app: TestClient) -> None:
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            resp = _app.post(
                "/api/payments/safepay/callback",
                json={"ref": "T123"},
            )
            assert resp.status_code == 200

    def test_nayapay_callback(self, _app: TestClient) -> None:
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            resp = _app.post(
                "/api/payments/nayapay/callback",
                json={"ref": "T123"},
            )
            assert resp.status_code == 200

    def test_dummy_callback_post(self, _app: TestClient) -> None:
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            resp = _app.post(
                "/api/payments/dummy/callback",
                json={"ref": "T123"},
            )
            assert resp.status_code == 200

    def test_dummy_callback_get(self, _app: TestClient) -> None:
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            resp = _app.get("/api/payments/dummy/callback?ref=T123")
            assert resp.status_code == 200

    def test_payment_status(self, _app: TestClient) -> None:
        mock_gateway = MagicMock()
        mock_gateway.get_gateway_name.return_value = "jazzcash"
        mock_gateway.get_gateway_metadata.return_value = {}
        mock_gateway.health_check = AsyncMock(return_value=True)
        with patch(
            "app.payments.factory.get_available_gateways",
            return_value=["jazzcash", "easypaisa"],
        ), patch(
            "app.payments.factory.get_gateway",
            return_value=mock_gateway,
        ):
            resp = _app.get("/api/payments/status")
            assert resp.status_code == 200

    def test_callback_error_returns_200(self, _app: TestClient) -> None:
        """Payment callbacks always return 200 even on error."""
        with patch(
            "app.api.payments.handle_gateway_callback",
            new_callable=AsyncMock,
            side_effect=Exception("Internal error"),
        ):
            resp = _app.post(
                "/api/payments/jazzcash/callback",
                json={"pp_TxnRefNo": "T123"},
            )
            assert resp.status_code == 200
