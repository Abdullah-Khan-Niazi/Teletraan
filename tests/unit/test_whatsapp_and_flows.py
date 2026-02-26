"""Tests for WhatsApp client, media, and Channel A flows – coverage boost.

Covers uncovered branches in:
- app.whatsapp.client (send_message error paths, download_media, etc.)
- app.whatsapp.media (download_and_store, convert_ogg, upload, signed_url)
- app.channels.channel_a.catalog_flow
- app.channels.channel_a.complaint_flow
- app.channels.channel_a.profile_flow

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import httpx
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# WhatsApp client
# ═══════════════════════════════════════════════════════════════════════════


class TestIsRetryable:
    """Cover _is_retryable helper."""

    def test_rate_limit_error(self) -> None:
        from app.core.exceptions import WhatsAppRateLimitError
        from app.whatsapp.client import _is_retryable

        exc = WhatsAppRateLimitError("rate limited", operation="send")
        assert _is_retryable(exc) is True

    def test_http_500(self) -> None:
        from app.whatsapp.client import _is_retryable

        resp = MagicMock()
        resp.status_code = 502
        exc = httpx.HTTPStatusError("bad gw", request=MagicMock(), response=resp)
        assert _is_retryable(exc) is True

    def test_http_400(self) -> None:
        from app.whatsapp.client import _is_retryable

        resp = MagicMock()
        resp.status_code = 400
        exc = httpx.HTTPStatusError("bad req", request=MagicMock(), response=resp)
        assert _is_retryable(exc) is False

    def test_generic_exception(self) -> None:
        from app.whatsapp.client import _is_retryable

        assert _is_retryable(ValueError("x")) is False


class TestWhatsAppClientLifecycle:
    """Cover _get_http re-creation, close."""

    @patch("app.whatsapp.client.get_settings")
    def test_get_http_creates_client(self, gs: MagicMock) -> None:
        gs.return_value = MagicMock(
            meta_api_version="v19.0",
            meta_access_token="test-token",
        )
        from app.whatsapp.client import WhatsAppClient

        c = WhatsAppClient()
        http = c._get_http()
        assert http is not None
        # Second call returns same instance
        assert c._get_http() is http

    @patch("app.whatsapp.client.get_settings")
    def test_get_http_recreates_if_closed(self, gs: MagicMock) -> None:
        gs.return_value = MagicMock(
            meta_api_version="v19.0",
            meta_access_token="test-token",
        )
        from app.whatsapp.client import WhatsAppClient

        c = WhatsAppClient()
        first = c._get_http()
        # Simulate close
        c._http = MagicMock()
        c._http.is_closed = True
        second = c._get_http()
        assert second is not first

    @patch("app.whatsapp.client.get_settings")
    async def test_close_client(self, gs: MagicMock) -> None:
        gs.return_value = MagicMock(
            meta_api_version="v19.0",
            meta_access_token="test-token",
        )
        from app.whatsapp.client import WhatsAppClient

        c = WhatsAppClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        c._http = mock_http
        await c.close()
        mock_http.aclose.assert_called_once()
        assert c._http is None


class TestWhatsAppClientSendMessage:
    """Cover send_message error paths."""

    def _make_client(self) -> Any:
        from app.whatsapp.client import WhatsAppClient

        c = WhatsAppClient()
        mock_http = AsyncMock()
        c._http = mock_http
        c._get_http = MagicMock(return_value=mock_http)
        return c, mock_http

    async def test_send_message_rate_limit(self) -> None:
        from app.core.exceptions import WhatsAppRateLimitError

        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 429
        http.post.return_value = resp

        with pytest.raises(WhatsAppRateLimitError):
            await c.send_message("pnid", {"type": "text"})

    async def test_send_message_4xx(self) -> None:
        from app.core.exceptions import WhatsAppAPIError

        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 400
        resp.content = b'{"error":{"code":100,"message":"bad"}}'
        resp.json.return_value = {"error": {"code": 100, "message": "bad"}}
        resp.text = "bad"
        http.post.return_value = resp

        with pytest.raises(WhatsAppAPIError, match="Meta API error"):
            await c.send_message("pnid", {"type": "text"})

    async def test_send_message_5xx_raises_for_retry(self) -> None:
        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 500
        resp.content = b'{"error":{}}'
        resp.json.return_value = {"error": {}}
        resp.text = "ISE"
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "ise", request=MagicMock(), response=resp
        )
        http.post.return_value = resp

        with pytest.raises(httpx.HTTPStatusError):
            await c.send_message("pnid", {"type": "text"})

    async def test_send_message_generic_exception(self) -> None:
        from app.core.exceptions import WhatsAppAPIError

        c, http = self._make_client()
        http.post.side_effect = RuntimeError("kaboom")

        with pytest.raises(WhatsAppAPIError, match="Failed to send"):
            await c.send_message("pnid", {"type": "text"})

    async def test_send_message_success(self) -> None:
        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": [{"id": "wamid.123"}]}
        http.post.return_value = resp

        mid = await c.send_message("pnid", {"type": "text"})
        assert mid == "wamid.123"


class TestWhatsAppClientMarkAsRead:
    """Cover mark_as_read."""

    def _make_client(self) -> Any:
        from app.whatsapp.client import WhatsAppClient

        c = WhatsAppClient()
        mock_http = AsyncMock()
        c._http = mock_http
        c._get_http = MagicMock(return_value=mock_http)
        return c, mock_http

    async def test_mark_as_read_success(self) -> None:
        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 200
        http.post.return_value = resp

        await c.mark_as_read("pnid", "wamid.1")  # should not raise

    async def test_mark_as_read_400(self) -> None:
        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 400
        http.post.return_value = resp

        await c.mark_as_read("pnid", "wamid.1")  # logs warning, no raise

    async def test_mark_as_read_exception(self) -> None:
        c, http = self._make_client()
        http.post.side_effect = RuntimeError("network")

        await c.mark_as_read("pnid", "wamid.1")  # swallowed


class TestWhatsAppClientDownloadMedia:
    """Cover download_media and get_media_url."""

    def _make_client(self) -> Any:
        from app.whatsapp.client import WhatsAppClient

        c = WhatsAppClient()
        mock_http = AsyncMock()
        c._http = mock_http
        c._get_http = MagicMock(return_value=mock_http)
        return c, mock_http

    @patch("app.whatsapp.client.get_settings")
    async def test_download_media_success(self, gs: MagicMock) -> None:
        gs.return_value = MagicMock(meta_access_token="tok")
        c, http = self._make_client()

        meta_resp = MagicMock()
        meta_resp.status_code = 200
        meta_resp.raise_for_status = MagicMock()
        meta_resp.json.return_value = {
            "url": "https://cdn.example.com/media/123",
            "mime_type": "image/jpeg",
        }

        dl_resp = MagicMock()
        dl_resp.status_code = 200
        dl_resp.raise_for_status = MagicMock()
        dl_resp.content = b"\xff\xd8\xff\xe0"

        http.get.side_effect = [meta_resp, dl_resp]

        data, mime = await c.download_media("media-123")
        assert data == b"\xff\xd8\xff\xe0"
        assert mime == "image/jpeg"

    @patch("app.whatsapp.client.get_settings")
    async def test_download_media_4xx(self, gs: MagicMock) -> None:
        from app.core.exceptions import WhatsAppAPIError

        gs.return_value = MagicMock(meta_access_token="tok")
        c, http = self._make_client()

        resp = MagicMock()
        resp.status_code = 404
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "not found", request=MagicMock(), response=resp
        )
        http.get.return_value = resp

        with pytest.raises(WhatsAppAPIError, match="Media download failed"):
            await c.download_media("bad-id")

    async def test_download_media_generic_error(self) -> None:
        from app.core.exceptions import WhatsAppAPIError

        c, http = self._make_client()
        http.get.side_effect = RuntimeError("crash")

        with pytest.raises(WhatsAppAPIError, match="Media download failed"):
            await c.download_media("err-id")

    async def test_get_media_url_success(self) -> None:
        c, http = self._make_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"url": "https://cdn.example.com/media/789"}
        http.get.return_value = resp

        url = await c.get_media_url("media-789")
        assert url == "https://cdn.example.com/media/789"

    async def test_get_media_url_error(self) -> None:
        from app.core.exceptions import WhatsAppAPIError

        c, http = self._make_client()
        http.get.side_effect = RuntimeError("fail")

        with pytest.raises(WhatsAppAPIError, match="Failed to get media URL"):
            await c.get_media_url("bad-id")


# ═══════════════════════════════════════════════════════════════════════════
# WhatsApp media module
# ═══════════════════════════════════════════════════════════════════════════


class TestMediaHelpers:
    """Cover media.py functions."""

    def test_ext_from_mime_known(self) -> None:
        from app.whatsapp.media import _ext_from_mime

        assert _ext_from_mime("image/jpeg") == ".jpg"
        assert _ext_from_mime("audio/ogg; codecs=opus") == ".ogg"

    def test_ext_from_mime_unknown(self) -> None:
        from app.whatsapp.media import _ext_from_mime

        assert _ext_from_mime("application/x-weird") == ".bin"

    @patch("app.whatsapp.media._get_signed_url", new_callable=AsyncMock)
    @patch("app.whatsapp.media._upload_to_storage", new_callable=AsyncMock)
    @patch("app.whatsapp.media.whatsapp_client")
    async def test_download_and_store_media(
        self, wa_client: MagicMock, upload: AsyncMock, signed: AsyncMock
    ) -> None:
        from app.whatsapp.media import download_and_store_media

        wa_client.download_media = AsyncMock(
            return_value=(b"media-bytes", "image/png")
        )
        signed.return_value = "https://storage.example.com/signed-url"

        path, url = await download_and_store_media("mid-1", "dist-1")
        assert url == "https://storage.example.com/signed-url"
        assert "dist-1" in path
        upload.assert_called_once()

    @patch("app.whatsapp.media.download_and_store_media", new_callable=AsyncMock)
    async def test_download_and_store_complaint_image(
        self, mock_store: AsyncMock
    ) -> None:
        from app.whatsapp.media import download_and_store_complaint_image

        mock_store.return_value = ("path/img.jpg", "https://url.com/img")
        path, url = await download_and_store_complaint_image(
            "mid-2", "dist-2", "comp-1"
        )
        assert path == "path/img.jpg"
        mock_store.assert_called_once()

    @patch("app.whatsapp.media.whatsapp_client")
    async def test_download_voice_bytes(self, wa_client: MagicMock) -> None:
        from app.whatsapp.media import download_voice_bytes

        wa_client.download_media = AsyncMock(
            return_value=(b"ogg-data", "audio/ogg")
        )
        data, mime = await download_voice_bytes("mid-3")
        assert data == b"ogg-data"
        assert mime == "audio/ogg"

    async def test_convert_ogg_to_wav_import_error(self) -> None:
        from app.core.exceptions import WhatsAppAPIError

        with patch.dict("sys.modules", {"pydub": None, "pydub.AudioSegment": None}):
            # Force reimport to hit ImportError
            import importlib
            import app.whatsapp.media as media_mod

            # The convert function does lazy import inside
            with pytest.raises(WhatsAppAPIError):
                await media_mod.convert_ogg_to_wav(b"fake-ogg")

    @patch("app.whatsapp.media.get_db_client")
    async def test_upload_to_storage_success(self, mock_db: MagicMock) -> None:
        from app.whatsapp.media import _upload_to_storage

        mock_client = MagicMock()
        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.upload = AsyncMock(return_value=None)
        mock_storage.from_ = MagicMock(return_value=mock_bucket)
        mock_client.storage = mock_storage
        mock_db.return_value = mock_client

        await _upload_to_storage("media", "test/path.jpg", b"data", "image/jpeg")
        mock_bucket.upload.assert_called_once()

    @patch("app.whatsapp.media.get_db_client")
    async def test_upload_to_storage_error(self, mock_db: MagicMock) -> None:
        from app.core.exceptions import WhatsAppAPIError
        from app.whatsapp.media import _upload_to_storage

        mock_db.side_effect = RuntimeError("DB down")

        with pytest.raises(WhatsAppAPIError):
            await _upload_to_storage("media", "path", b"data", "image/jpeg")

    @patch("app.whatsapp.media.get_db_client")
    async def test_get_signed_url_dict_response(self, mock_db: MagicMock) -> None:
        from app.whatsapp.media import _get_signed_url

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.create_signed_url = AsyncMock(
            return_value={"signedURL": "https://signed.example.com/path"}
        )
        mock_client.storage.from_ = MagicMock(return_value=mock_bucket)
        mock_db.return_value = mock_client

        url = await _get_signed_url("media", "test/path.jpg")
        assert url == "https://signed.example.com/path"

    @patch("app.whatsapp.media.get_db_client")
    async def test_get_signed_url_error(self, mock_db: MagicMock) -> None:
        from app.core.exceptions import WhatsAppAPIError
        from app.whatsapp.media import _get_signed_url

        mock_db.side_effect = RuntimeError("fail")

        with pytest.raises(WhatsAppAPIError):
            await _get_signed_url("media", "path")


# ═══════════════════════════════════════════════════════════════════════════
# Channel A — Catalog Flow
# ═══════════════════════════════════════════════════════════════════════════


def _mock_session(**kwargs: Any) -> MagicMock:
    """Create a mock Session object."""
    s = MagicMock()
    s.id = kwargs.get("id", str(uuid4()))
    s.distributor_id = kwargs.get("distributor_id", str(uuid4()))
    s.whatsapp_number = kwargs.get("whatsapp_number", "+923001234567")
    s.language = kwargs.get("language", "english")
    s.current_state = kwargs.get("current_state", "catalog_browsing")
    s.state_data = kwargs.get("state_data", {})
    s.customer_id = kwargs.get("customer_id", str(uuid4()))
    return s


class TestCatalogFlow:
    """Cover catalog_flow.py."""

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_back_to_menu(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cat = AsyncMock()

        result = await handle_catalog_step(
            session, "back",
            button_id=None, session_repo=repo, catalog_service=cat
        )
        assert result == []

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_order_intent(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cat = AsyncMock()

        result = await handle_catalog_step(
            session, "order now",
            button_id=None, session_repo=repo, catalog_service=cat
        )
        assert result == []

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_categories_browse(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cat = AsyncMock()
        cat.get_categories.return_value = {"Antibiotics": 5, "Painkillers": 3}

        result = await handle_catalog_step(
            session, "categories",
            button_id=None, session_repo=repo, catalog_service=cat
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_search_with_results(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cat = AsyncMock()
        match_item = MagicMock(medicine_name="Panadol", price_per_unit_paisas=5000, score=95)
        match_result = MagicMock()
        match_result.matches = [MagicMock(item=match_item, score=95)]
        cat.find_medicine.return_value = match_result

        result = await handle_catalog_step(
            session, "panadol",
            button_id=None, session_repo=repo, catalog_service=cat
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_search_no_results(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cat = AsyncMock()
        match_result = MagicMock()
        match_result.matches = []
        cat.find_medicine.return_value = match_result
        cat.get_categories.return_value = {"Antibiotics": 5}

        result = await handle_catalog_step(
            session, "nonexistent_med",
            button_id=None, session_repo=repo, catalog_service=cat
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_button_back(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cat = AsyncMock()

        result = await handle_catalog_step(
            session, "",
            button_id="catalog_back_menu", session_repo=repo, catalog_service=cat
        )
        assert result == []

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_start_catalog(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import start_catalog

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()

        result = await start_catalog(session, session_repo=repo)
        assert len(result) > 0

    @patch("app.channels.channel_a.catalog_flow.transition")
    async def test_handle_roman_urdu(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.catalog_flow import handle_catalog_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(language="roman_urdu")
        repo = AsyncMock()
        cat = AsyncMock()
        cat.get_categories.return_value = {}

        result = await handle_catalog_step(
            session, "categories",
            button_id=None, session_repo=repo, catalog_service=cat
        )
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Channel A — Complaint Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestComplaintFlow:
    """Cover complaint_flow.py."""

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_start_complaint(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import start_complaint

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()

        result = await start_complaint(session, session_repo=repo)
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_description_cancel(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="complaint_description")
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "cancel",
            button_id=None, session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_description_too_short(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="complaint_description")
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "short",
            button_id=None, session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_description_valid(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="complaint_description", state_data={})
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "This medicine was damaged when it arrived",
            button_id=None, session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_category_valid(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(
            current_state="complaint_category",
            state_data={"complaint_description": "Damaged box"},
        )
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "1",
            button_id=None, session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_category_invalid(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="complaint_category")
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "xyz",
            button_id=None, session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_confirm_cancel(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(
            current_state="complaint_confirm",
            state_data={
                "complaint_description": "Test",
                "complaint_category": "quality",
            },
        )
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "",
            button_id="complaint_cancel", session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_confirm_edit(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(
            current_state="complaint_confirm",
            state_data={
                "complaint_description": "Test",
                "complaint_category": "quality",
            },
        )
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "",
            button_id="complaint_confirm_edit", session_repo=repo, complaint_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.complaint_flow.transition")
    async def test_handle_unknown_state(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.complaint_flow import handle_complaint_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="UNKNOWN_STATE")
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_complaint_step(
            session, "text",
            button_id=None, session_repo=repo, complaint_repo=cr
        )
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Channel A — Profile Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestProfileFlow:
    """Cover profile_flow.py."""

    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_start_profile_no_customer(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.profile_flow import start_profile

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(customer_id=None)
        repo = AsyncMock()
        cr = AsyncMock()

        result = await start_profile(session, session_repo=repo, customer_repo=cr)
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_start_profile_with_customer(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.profile_flow import start_profile

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session()
        repo = AsyncMock()
        cr = AsyncMock()
        cr.get_by_id = AsyncMock(return_value=MagicMock(
            name="Ali",
            shop_name="Ali Medical",
            whatsapp_number="+923001234567",
            address="Lahore",
        ))

        result = await start_profile(session, session_repo=repo, customer_repo=cr)
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_view_back(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="profile_view")
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_profile_step(
            session, "back",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert result == []

    @patch("app.channels.channel_a.profile_flow.start_profile", new_callable=AsyncMock)
    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_view_edit_name(self, mock_tr: MagicMock, mock_sp: AsyncMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="profile_view", state_data={})
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_profile_step(
            session, "edit name",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.start_profile", new_callable=AsyncMock)
    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_edit_name_valid(self, mock_tr: MagicMock, mock_sp: AsyncMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        mock_sp.return_value = [{"type": "text"}]
        session = _mock_session(
            current_state="profile_edit",
            state_data={"profile_edit_field": "name"},
        )
        repo = AsyncMock()
        cr = AsyncMock()
        cr.update = AsyncMock(return_value=MagicMock())

        result = await handle_profile_step(
            session, "Ahmed Khan",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.start_profile", new_callable=AsyncMock)
    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_edit_name_invalid(self, mock_tr: MagicMock, mock_sp: AsyncMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(
            current_state="profile_edit",
            state_data={"profile_edit_field": "name"},
        )
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_profile_step(
            session, "X",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.start_profile", new_callable=AsyncMock)
    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_edit_shop(self, mock_tr: MagicMock, mock_sp: AsyncMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        mock_sp.return_value = [{"type": "text"}]
        session = _mock_session(
            current_state="profile_edit",
            state_data={"profile_edit_field": "shop_name"},
        )
        repo = AsyncMock()
        cr = AsyncMock()
        cr.update = AsyncMock(return_value=MagicMock())

        result = await handle_profile_step(
            session, "New Medical Store",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.start_profile", new_callable=AsyncMock)
    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_edit_address(self, mock_tr: MagicMock, mock_sp: AsyncMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        mock_sp.return_value = [{"type": "text"}]
        session = _mock_session(
            current_state="profile_edit",
            state_data={"profile_edit_field": "address"},
        )
        repo = AsyncMock()
        cr = AsyncMock()
        cr.update = AsyncMock(return_value=MagicMock())

        result = await handle_profile_step(
            session, "Shop 5, Anarkali Bazaar, Lahore",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert len(result) > 0

    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_unknown_state(self, mock_tr: MagicMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(current_state="UNKNOWN")
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_profile_step(
            session, "text",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert result == []

    @patch("app.channels.channel_a.profile_flow.start_profile", new_callable=AsyncMock)
    @patch("app.channels.channel_a.profile_flow.transition")
    async def test_handle_profile_edit_no_customer(self, mock_tr: MagicMock, mock_sp: AsyncMock) -> None:
        from app.channels.channel_a.profile_flow import handle_profile_step

        mock_tr.return_value = MagicMock(allowed=True)
        session = _mock_session(
            current_state="profile_edit",
            state_data={"profile_edit_field": "name"},
            customer_id=None,
        )
        repo = AsyncMock()
        cr = AsyncMock()

        result = await handle_profile_step(
            session, "Ahmed Khan",
            button_id=None, session_repo=repo, customer_repo=cr
        )
        assert len(result) > 0
