"""Async Meta WhatsApp Cloud API client.

Handles all outbound HTTP calls to the Meta Graph API: sending messages,
downloading media, and sending read receipts.  Retries transient errors
(HTTP 429 and 5xx) with exponential backoff via ``tenacity``.

Usage::

    from app.whatsapp.client import whatsapp_client

    msg_id = await whatsapp_client.send_message(
        phone_number_id="123456",
        payload=build_text_message("+923001234567", "Salam!"),
    )
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.exceptions import WhatsAppAPIError, WhatsAppRateLimitError


# ── Retry predicate ──────────────────────────────────────────────────


def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception warrants a retry.

    Only HTTP 429 (rate-limit) and 5xx (server errors) are retryable.
    4xx client errors (except 429) indicate invalid requests and must
    not be retried.
    """
    if isinstance(exc, WhatsAppRateLimitError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


# ── Client class ─────────────────────────────────────────────────────


class WhatsAppClient:
    """Async HTTP client for the Meta WhatsApp Cloud API.

    Attributes:
        _http: Shared ``httpx.AsyncClient`` created lazily on first call.
    """

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    # ── lifecycle ────────────────────────────────────────────────────

    def _get_http(self) -> httpx.AsyncClient:
        """Return or lazily create the shared httpx client."""
        if self._http is None or self._http.is_closed:
            settings = get_settings()
            self._http = httpx.AsyncClient(
                base_url=f"https://graph.facebook.com/{settings.meta_api_version}",
                headers={
                    "Authorization": f"Bearer {settings.meta_access_token}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._http

    async def close(self) -> None:
        """Close the underlying HTTP client gracefully."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None
            logger.info("whatsapp.client_closed")

    # ── send message ─────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def send_message(
        self,
        phone_number_id: str,
        payload: dict[str, Any],
    ) -> str:
        """Send a message via the Meta Cloud API.

        Args:
            phone_number_id: The WhatsApp phone number ID to send from.
            payload: Message payload dict from ``message_types`` builders.

        Returns:
            The WhatsApp message ID assigned by Meta.

        Raises:
            WhatsAppRateLimitError: On HTTP 429 (rate-limited).
            WhatsAppAPIError: On any other API error after retries.
        """
        http = self._get_http()
        url = f"/{phone_number_id}/messages"

        start = time.monotonic()
        try:
            response = await http.post(url, json=payload)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            if response.status_code == 429:
                logger.warning(
                    "whatsapp.rate_limited",
                    phone_number_id=phone_number_id,
                    elapsed_ms=elapsed_ms,
                )
                raise WhatsAppRateLimitError(
                    message="Meta API rate limit hit (429).",
                    operation="send_message",
                )

            if response.status_code >= 400:
                error_body = response.json() if response.content else {}
                error_detail = error_body.get("error", {})
                error_code = error_detail.get("code", response.status_code)
                error_message = error_detail.get("message", response.text)

                logger.error(
                    "whatsapp.send_failed",
                    phone_number_id=phone_number_id,
                    status=response.status_code,
                    error_code=error_code,
                    error_message=error_message,
                    elapsed_ms=elapsed_ms,
                )

                # 5xx will be retried by tenacity via httpx.HTTPStatusError path
                if response.status_code >= 500:
                    response.raise_for_status()

                raise WhatsAppAPIError(
                    message=f"Meta API error {error_code}: {error_message}",
                    operation="send_message",
                    details={
                        "status": response.status_code,
                        "error_code": error_code,
                    },
                )

            data = response.json()
            message_id: str = data["messages"][0]["id"]

            logger.info(
                "whatsapp.message_sent",
                phone_number_id=phone_number_id,
                message_id=message_id,
                msg_type=payload.get("type", "unknown"),
                elapsed_ms=elapsed_ms,
            )
            return message_id

        except (WhatsAppAPIError, WhatsAppRateLimitError):
            raise
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "whatsapp.send_exception",
                phone_number_id=phone_number_id,
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
            raise WhatsAppAPIError(
                message=f"Failed to send WhatsApp message: {exc}",
                operation="send_message",
            ) from exc

    # ── mark as read ─────────────────────────────────────────────────

    async def mark_as_read(
        self,
        phone_number_id: str,
        message_id: str,
    ) -> None:
        """Send a read receipt for the given message.

        Args:
            phone_number_id: The WhatsApp phone number ID.
            message_id: The message ID to mark as read.

        Raises:
            WhatsAppAPIError: On API failure (non-fatal, logged).
        """
        http = self._get_http()
        url = f"/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            response = await http.post(url, json=payload)
            if response.status_code >= 400:
                logger.warning(
                    "whatsapp.read_receipt_failed",
                    message_id=message_id,
                    status=response.status_code,
                )
            else:
                logger.debug(
                    "whatsapp.read_receipt_sent",
                    message_id=message_id,
                )
        except Exception as exc:
            # Read receipts are non-critical — log and move on
            logger.warning(
                "whatsapp.read_receipt_exception",
                message_id=message_id,
                error=str(exc),
            )

    # ── download media ───────────────────────────────────────────────

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Download media bytes from the Meta CDN.

        Two-step process:
        1. ``GET /{media_id}`` → JSON with ``url`` and ``mime_type``.
        2. ``GET {url}`` → raw media bytes.

        Args:
            media_id: The WhatsApp media ID from the incoming message.

        Returns:
            Tuple of ``(media_bytes, mime_type)``.

        Raises:
            WhatsAppAPIError: On any download failure after retries.
        """
        http = self._get_http()

        try:
            # Step 1: get media URL
            meta_response = await http.get(f"/{media_id}")
            meta_response.raise_for_status()
            meta_data = meta_response.json()
            media_url: str = meta_data["url"]
            mime_type: str = meta_data.get("mime_type", "application/octet-stream")

            # Step 2: download bytes (use same auth header)
            settings = get_settings()
            download_response = await http.get(
                media_url,
                headers={"Authorization": f"Bearer {settings.meta_access_token}"},
            )
            download_response.raise_for_status()

            media_bytes = download_response.content
            logger.info(
                "whatsapp.media_downloaded",
                media_id=media_id,
                mime_type=mime_type,
                size_bytes=len(media_bytes),
            )
            return media_bytes, mime_type

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise  # tenacity retries 5xx
            raise WhatsAppAPIError(
                message=f"Media download failed ({exc.response.status_code}): {exc}",
                operation="download_media",
                details={"media_id": media_id},
            ) from exc
        except (WhatsAppAPIError, WhatsAppRateLimitError):
            raise
        except Exception as exc:
            raise WhatsAppAPIError(
                message=f"Media download failed: {exc}",
                operation="download_media",
                details={"media_id": media_id},
            ) from exc

    # ── get media URL (utility) ──────────────────────────────────────

    async def get_media_url(self, media_id: str) -> str:
        """Retrieve the download URL for a media asset.

        Args:
            media_id: The WhatsApp media ID.

        Returns:
            Direct download URL string.

        Raises:
            WhatsAppAPIError: On failure.
        """
        http = self._get_http()
        try:
            response = await http.get(f"/{media_id}")
            response.raise_for_status()
            return response.json()["url"]
        except Exception as exc:
            raise WhatsAppAPIError(
                message=f"Failed to get media URL: {exc}",
                operation="get_media_url",
                details={"media_id": media_id},
            ) from exc


# ── Singleton instance ───────────────────────────────────────────────

whatsapp_client = WhatsAppClient()
