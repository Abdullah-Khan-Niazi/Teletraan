"""Tests for main.py, core/logging.py, db/client.py, and session_expiry.py.

These modules were at 0% or low coverage. Tests exercise the key code
paths via mocking to avoid needing a real Supabase connection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════
# LOGGING — mask_pii + configure_logging
# ═══════════════════════════════════════════════════════════════


class TestMaskPii:
    """Test PII masking filter for loguru."""

    def test_masks_phone_in_message(self) -> None:
        from app.core.logging import mask_pii

        record: dict = {
            "message": "Processing +923001234567 order",
            "extra": {},
        }
        result = mask_pii(record)
        assert result is True
        assert "+923001234567" not in record["message"]
        assert "****4567" in record["message"]

    def test_masks_phone_in_extras(self) -> None:
        from app.core.logging import mask_pii

        record: dict = {
            "message": "Order placed",
            "extra": {"phone": "+923001234567"},
        }
        mask_pii(record)
        assert "****4567" in record["extra"]["phone"]

    def test_ignores_non_string_extras(self) -> None:
        from app.core.logging import mask_pii

        record: dict = {
            "message": "OK",
            "extra": {"count": 42},
        }
        result = mask_pii(record)
        assert result is True
        assert record["extra"]["count"] == 42

    def test_masks_multiple_numbers(self) -> None:
        from app.core.logging import mask_pii

        record: dict = {
            "message": "From +923001234567 to +923009876543",
            "extra": {},
        }
        mask_pii(record)
        assert "****4567" in record["message"]
        assert "****6543" in record["message"]
        assert "+9230" not in record["message"]


class TestConfigureLogging:
    """Test configure_logging function."""

    def test_configure_development(self) -> None:
        from app.core.logging import configure_logging

        # Should not raise
        configure_logging(app_env="development", log_level="DEBUG")

    def test_configure_production(self) -> None:
        from app.core.logging import configure_logging

        configure_logging(app_env="production", log_level="INFO")

    def test_configure_default(self) -> None:
        from app.core.logging import configure_logging

        configure_logging()


# ═══════════════════════════════════════════════════════════════
# DB CLIENT
# ═══════════════════════════════════════════════════════════════


class TestDbClient:
    """Test Supabase client singleton lifecycle."""

    def test_get_db_client_before_init_raises(self) -> None:
        """get_db_client raises DatabaseError if not initialised."""
        import app.db.client as mod
        from app.core.exceptions import DatabaseError

        # Save state and force None
        original = mod._client
        mod._client = None
        try:
            with pytest.raises(DatabaseError):
                mod.get_db_client()
        finally:
            mod._client = original

    @pytest.mark.asyncio
    async def test_init_client_success(self) -> None:
        """init_client sets the global client."""
        import app.db.client as mod

        original = mod._client
        mod._client = None
        mock_client = MagicMock()
        mock_settings = MagicMock()
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.supabase_service_key = "test-key"

        try:
            with patch(
                "app.db.client.acreate_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ), patch(
                "app.db.client.get_settings",
                return_value=mock_settings,
            ):
                await mod.init_client()
                assert mod._client is mock_client
        finally:
            mod._client = original

    @pytest.mark.asyncio
    async def test_init_client_double_call_warns(self) -> None:
        """Double init_client call logs warning and returns."""
        import app.db.client as mod

        original = mod._client
        mod._client = MagicMock()  # pretend already initialized

        try:
            # Should not raise; should return early
            await mod.init_client()
        finally:
            mod._client = original

    @pytest.mark.asyncio
    async def test_init_client_failure_raises(self) -> None:
        """init_client raises DatabaseError on failure."""
        import app.db.client as mod
        from app.core.exceptions import DatabaseError

        original = mod._client
        mod._client = None
        mock_settings = MagicMock()
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.supabase_service_key = "test-key"

        try:
            with patch(
                "app.db.client.acreate_client",
                new_callable=AsyncMock,
                side_effect=Exception("connection refused"),
            ), patch(
                "app.db.client.get_settings",
                return_value=mock_settings,
            ):
                with pytest.raises(DatabaseError):
                    await mod.init_client()
        finally:
            mod._client = original

    @pytest.mark.asyncio
    async def test_close_client(self) -> None:
        """close_client clears the global."""
        import app.db.client as mod

        original = mod._client
        mod._client = MagicMock()

        try:
            await mod.close_client()
            assert mod._client is None
        finally:
            mod._client = original

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """health_check returns True when DB is reachable."""
        import app.db.client as mod

        original = mod._client
        mock_client = MagicMock()
        # Chain the query
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.limit.return_value = mock_client
        mock_client.execute = AsyncMock(return_value=MagicMock(data=[]))
        mod._client = mock_client

        try:
            result = await mod.health_check()
            assert result is True
        finally:
            mod._client = original

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        """health_check returns False when DB is unreachable."""
        import app.db.client as mod

        original = mod._client
        mod._client = None  # Not initialized → DatabaseError

        try:
            result = await mod.health_check()
            assert result is False
        finally:
            mod._client = original


# ═══════════════════════════════════════════════════════════════
# MAIN APP — creation, middleware, exception handlers
# ═══════════════════════════════════════════════════════════════


import os


# Env vars needed for Settings validation when importing app.main
_MAIN_ENV = {
    "META_APP_ID": "test-app-id",
    "META_APP_SECRET": "test-app-secret",
    "META_VERIFY_TOKEN": "test-verify-token",
    "OWNER_PHONE_NUMBER_ID": "owner-pnid",
    "OWNER_WHATSAPP_NUMBER": "+923001234567",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy.key",
    "ENCRYPTION_KEY": "dGVzdGtleTEyMzQ1Njc4OTAxMjM0NTY3ODkwYWJjZA==",
    "APP_ENV": "development",
    "APP_SECRET_KEY": "test-secret-key-for-testing-only",
    "ADMIN_API_KEY": "test-admin-api-key",
    "GEMINI_API_KEY": "test-gemini-key",
}


class TestMainApp:
    """Test main app components."""

    def _ensure_main_imported(self):
        """Import app.main with required env vars."""
        from cryptography.fernet import Fernet

        env = {**_MAIN_ENV, "ENCRYPTION_KEY": Fernet.generate_key().decode()}
        for k, v in env.items():
            os.environ.setdefault(k, v)
        # Clear lru_cache so Settings re-reads env
        from app.core.config import get_settings
        get_settings.cache_clear()
        import app.main  # noqa: F401

    def test_create_app_returns_fastapi(self) -> None:
        """create_app produces a FastAPI instance with correct title."""
        self._ensure_main_imported()
        from app.main import create_app
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)
        assert app.title == "TELETRAAN"

    def test_register_exception_handlers(self) -> None:
        """Exception handlers can be registered on a FastAPI app."""
        self._ensure_main_imported()
        from fastapi import FastAPI
        from app.core.exceptions import TeletraanBaseException
        from app.main import _register_exception_handlers

        test_app = FastAPI()
        _register_exception_handlers(test_app)

        @test_app.get("/_test")
        async def _raise() -> None:
            raise TeletraanBaseException("boom", operation="test")

        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.get("/_test")
        assert resp.status_code == 500
        assert "error" in resp.json()

    def test_register_exception_handlers_generic(self) -> None:
        """Generic exception handler catches unhandled errors."""
        self._ensure_main_imported()
        from fastapi import FastAPI
        from app.main import _register_exception_handlers

        test_app = FastAPI()
        _register_exception_handlers(test_app)

        @test_app.get("/_boom")
        async def _raise() -> None:
            raise RuntimeError("unexpected")

        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.get("/_boom")
        assert resp.status_code == 500

    def test_register_middleware(self) -> None:
        """Middleware registration adds security headers."""
        self._ensure_main_imported()
        from fastapi import FastAPI
        from app.main import _register_middleware

        test_app = FastAPI()
        _register_middleware(test_app)

        @test_app.get("/_ping")
        async def _ping() -> dict:
            return {"ok": True}

        client = TestClient(test_app)
        resp = client.get("/_ping")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert "X-Request-ID" in resp.headers

    def test_register_routers(self) -> None:
        """Router registration adds routes to the app."""
        self._ensure_main_imported()
        from fastapi import FastAPI
        from app.main import _register_routers

        test_app = FastAPI()
        _register_routers(test_app)

        route_paths = [r.path for r in test_app.routes if hasattr(r, "path")]
        assert "/health" in route_paths

    @pytest.mark.asyncio
    async def test_lifespan_context_manager(self) -> None:
        """Lifespan starts and stops expected services."""
        self._ensure_main_imported()
        from app.main import lifespan

        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []

        mock_app = MagicMock()
        with patch("app.main.init_client", new_callable=AsyncMock), \
             patch("app.main.close_client", new_callable=AsyncMock) as mock_close, \
             patch("app.main.create_scheduler", return_value=mock_scheduler):
            async with lifespan(mock_app):
                pass
            mock_scheduler.start.assert_called_once()
            mock_scheduler.shutdown.assert_called_once()
            mock_close.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# SESSION EXPIRY
# ═══════════════════════════════════════════════════════════════


def _make_session(*, expires_in_minutes: float = 55, state: str = "ordering") -> MagicMock:
    """Create a mock Session with relevant attributes."""
    mock = MagicMock()
    mock.id = "sess-123"
    mock.whatsapp_number = "+923001234567"
    mock.current_state = state
    mock.expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    mock.state_data = {}
    return mock


class TestSessionExpiryHelpers:
    """Test pure helper functions in session_expiry module."""

    def test_is_session_expired_false(self) -> None:
        from app.channels.session_expiry import is_session_expired

        session = _make_session(expires_in_minutes=30)
        assert is_session_expired(session) is False

    def test_is_session_expired_true(self) -> None:
        from app.channels.session_expiry import is_session_expired

        session = _make_session(expires_in_minutes=-5)
        assert is_session_expired(session) is True

    def test_minutes_until_expiry_positive(self) -> None:
        from app.channels.session_expiry import minutes_until_expiry

        session = _make_session(expires_in_minutes=30)
        result = minutes_until_expiry(session)
        assert 29 < result < 31

    def test_minutes_until_expiry_negative(self) -> None:
        from app.channels.session_expiry import minutes_until_expiry

        session = _make_session(expires_in_minutes=-5)
        result = minutes_until_expiry(session)
        assert result < 0

    def test_should_warn_true(self) -> None:
        from app.channels.session_expiry import should_warn

        session = _make_session(expires_in_minutes=5, state="ordering")
        assert should_warn(session) is True

    def test_should_warn_false_idle(self) -> None:
        from app.channels.session_expiry import should_warn

        session = _make_session(expires_in_minutes=5, state="idle")
        assert should_warn(session) is False

    def test_should_warn_false_too_far(self) -> None:
        from app.channels.session_expiry import should_warn

        session = _make_session(expires_in_minutes=30, state="ordering")
        assert should_warn(session) is False


class TestRefreshSessionTimeout:
    """Test session timeout refresh."""

    @pytest.mark.asyncio
    async def test_refresh_session_timeout(self) -> None:
        from app.channels.session_expiry import refresh_session_timeout

        mock_repo = MagicMock()
        mock_repo.update = AsyncMock(return_value=_make_session())
        result = await refresh_session_timeout("sess-123", mock_repo)
        mock_repo.update.assert_called_once()
        assert result is not None


class TestProcessExpiringSessions:
    """Test batch expiry processing."""

    @pytest.mark.asyncio
    async def test_process_expired_sessions(self) -> None:
        from app.channels.session_expiry import process_expiring_sessions

        expired_session = _make_session(expires_in_minutes=-5)
        mock_repo = MagicMock()
        mock_repo.get_expired_sessions = AsyncMock(
            return_value=[expired_session]
        )
        mock_repo.update_state = AsyncMock()
        mock_repo.update = AsyncMock()

        send_expired_fn = AsyncMock()

        # Patch get_db_client for warning scan
        mock_client = MagicMock()
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.neq.return_value = mock_client
        mock_client.gt.return_value = mock_client
        mock_client.lte.return_value = mock_client
        mock_client.execute = AsyncMock(
            return_value=MagicMock(data=[])
        )

        with patch(
            "app.db.client.get_db_client",
            return_value=mock_client,
        ):
            result = await process_expiring_sessions(
                mock_repo,
                send_expired_fn=send_expired_fn,
            )
            assert result["expired"] == 1
            assert result["warned"] == 0
            send_expired_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_warning_sessions(self) -> None:
        from app.channels.session_expiry import process_expiring_sessions
        from app.db.models.session import Session

        mock_repo = MagicMock()
        mock_repo.get_expired_sessions = AsyncMock(return_value=[])
        mock_repo.update = AsyncMock()

        # A session within warning window
        session_row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "distributor_id": "00000000-0000-0000-0000-000000000002",
            "whatsapp_number": "+923001234567",
            "current_state": "ordering",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
            "last_message_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state_data": {},
        }

        mock_client = MagicMock()
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.neq.return_value = mock_client
        mock_client.gt.return_value = mock_client
        mock_client.lte.return_value = mock_client
        mock_client.execute = AsyncMock(
            return_value=MagicMock(data=[session_row])
        )

        send_warning_fn = AsyncMock()

        with patch(
            "app.db.client.get_db_client",
            return_value=mock_client,
        ):
            result = await process_expiring_sessions(
                mock_repo,
                send_warning_fn=send_warning_fn,
            )
            assert result["warned"] == 1
            send_warning_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_no_sessions(self) -> None:
        from app.channels.session_expiry import process_expiring_sessions

        mock_repo = MagicMock()
        mock_repo.get_expired_sessions = AsyncMock(return_value=[])

        mock_client = MagicMock()
        mock_client.table.return_value = mock_client
        mock_client.select.return_value = mock_client
        mock_client.neq.return_value = mock_client
        mock_client.gt.return_value = mock_client
        mock_client.lte.return_value = mock_client
        mock_client.execute = AsyncMock(
            return_value=MagicMock(data=[])
        )

        with patch(
            "app.db.client.get_db_client",
            return_value=mock_client,
        ):
            result = await process_expiring_sessions(mock_repo)
            assert result == {"warned": 0, "expired": 0}
