"""Media download from Meta CDN and upload to Supabase Storage.

Handles the complete lifecycle of incoming media files: downloading from
WhatsApp's CDN, optional format conversion (OGG→WAV for voice), and
uploading to Supabase Storage for persistent access.

Audio files are processed in memory and never saved to disk.
"""

from __future__ import annotations

import io
import uuid
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import WhatsAppAPIError
from app.db.client import get_db_client
from app.whatsapp.client import whatsapp_client


# ── Storage buckets ──────────────────────────────────────────────────

MEDIA_BUCKET = "media"
COMPLAINTS_BUCKET = "complaints"
VOICE_BUCKET = "voice"

# ── MIME → extension map ─────────────────────────────────────────────

_MIME_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


def _ext_from_mime(mime_type: str) -> str:
    """Derive a file extension from a MIME type."""
    return _MIME_EXTENSIONS.get(mime_type.split(";")[0].strip(), ".bin")


# ── Download + Upload ────────────────────────────────────────────────


async def download_and_store_media(
    media_id: str,
    distributor_id: str,
    *,
    subfolder: str = "general",
    bucket: str = MEDIA_BUCKET,
) -> tuple[str, str]:
    """Download media from WhatsApp CDN and upload to Supabase Storage.

    Args:
        media_id: WhatsApp media ID from the incoming message.
        distributor_id: Distributor UUID for path scoping.
        subfolder: Sub-folder within the distributor path.
        bucket: Target Supabase Storage bucket name.

    Returns:
        Tuple of ``(storage_path, public_url)`` in Supabase.

    Raises:
        WhatsAppAPIError: On download or upload failure.
    """
    # Step 1: download from Meta
    media_bytes, mime_type = await whatsapp_client.download_media(media_id)

    # Step 2: derive storage path
    extension = _ext_from_mime(mime_type)
    filename = f"{uuid.uuid4().hex}{extension}"
    storage_path = f"{distributor_id}/{subfolder}/{filename}"

    # Step 3: upload to Supabase Storage
    await _upload_to_storage(bucket, storage_path, media_bytes, mime_type)

    # Step 4: get signed or public URL
    public_url = await _get_signed_url(bucket, storage_path)

    logger.info(
        "media.stored",
        media_id=media_id,
        bucket=bucket,
        path=storage_path,
        size_bytes=len(media_bytes),
        mime_type=mime_type,
    )
    return storage_path, public_url


async def download_and_store_complaint_image(
    media_id: str,
    distributor_id: str,
    complaint_id: str,
) -> tuple[str, str]:
    """Download a complaint image and store under complaints bucket.

    Args:
        media_id: WhatsApp media ID.
        distributor_id: Distributor UUID.
        complaint_id: Complaint UUID for path scoping.

    Returns:
        Tuple of ``(storage_path, public_url)``.

    Raises:
        WhatsAppAPIError: On any failure.
    """
    return await download_and_store_media(
        media_id,
        distributor_id,
        subfolder=f"complaints/{complaint_id}",
        bucket=COMPLAINTS_BUCKET,
    )


async def download_voice_bytes(media_id: str) -> tuple[bytes, str]:
    """Download voice message bytes for transcription.

    Voice messages are **not** persisted to storage — they live only
    in memory during the transcription pipeline.  WhatsApp sends voice
    as ``audio/ogg; codecs=opus``.

    Args:
        media_id: WhatsApp media ID for the voice message.

    Returns:
        Tuple of ``(audio_bytes, mime_type)``.

    Raises:
        WhatsAppAPIError: On download failure.
    """
    audio_bytes, mime_type = await whatsapp_client.download_media(media_id)

    logger.info(
        "media.voice_downloaded",
        media_id=media_id,
        mime_type=mime_type,
        size_bytes=len(audio_bytes),
    )
    return audio_bytes, mime_type


async def convert_ogg_to_wav(audio_bytes: bytes) -> bytes:
    """Convert OGG Opus audio to WAV format for AI transcription.

    Uses pydub with ffmpeg backend.  Processes entirely in memory.

    Args:
        audio_bytes: Raw OGG audio bytes.

    Returns:
        WAV audio bytes.

    Raises:
        WhatsAppAPIError: If conversion fails (e.g. ffmpeg not found).
    """
    try:
        from pydub import AudioSegment

        ogg_buffer = io.BytesIO(audio_bytes)
        audio_segment = AudioSegment.from_ogg(ogg_buffer)

        wav_buffer = io.BytesIO()
        audio_segment.export(wav_buffer, format="wav")
        wav_bytes = wav_buffer.getvalue()

        logger.debug(
            "media.ogg_to_wav_converted",
            input_bytes=len(audio_bytes),
            output_bytes=len(wav_bytes),
        )
        return wav_bytes

    except ImportError:
        raise WhatsAppAPIError(
            message="pydub is required for audio conversion but not installed.",
            operation="convert_ogg_to_wav",
        )
    except Exception as exc:
        raise WhatsAppAPIError(
            message=f"Audio conversion failed: {exc}",
            operation="convert_ogg_to_wav",
        ) from exc


# ── Supabase Storage helpers ─────────────────────────────────────────


async def _upload_to_storage(
    bucket: str,
    path: str,
    data: bytes,
    content_type: str,
) -> None:
    """Upload bytes to a Supabase Storage bucket.

    Args:
        bucket: Bucket name.
        path: Full path within the bucket.
        data: File bytes.
        content_type: MIME type for the upload.

    Raises:
        WhatsAppAPIError: On upload failure.
    """
    try:
        client = get_db_client()
        await client.storage.from_(bucket).upload(
            path,
            data,
            file_options={"content-type": content_type},
        )
    except Exception as exc:
        raise WhatsAppAPIError(
            message=f"Supabase Storage upload failed: {exc}",
            operation="upload_to_storage",
            details={"bucket": bucket, "path": path},
        ) from exc


async def _get_signed_url(
    bucket: str,
    path: str,
    *,
    expires_in: int = 3600,
) -> str:
    """Generate a signed URL for a stored file.

    Args:
        bucket: Bucket name.
        path: File path.
        expires_in: URL validity in seconds (default 1 hour).

    Returns:
        Signed download URL.

    Raises:
        WhatsAppAPIError: On URL generation failure.
    """
    try:
        client = get_db_client()
        result: Any = await client.storage.from_(bucket).create_signed_url(
            path,
            expires_in,
        )
        # supabase-py returns dict or object — extract URL defensively
        if isinstance(result, dict):
            return result.get("signedURL", result.get("signedUrl", ""))
        return getattr(result, "signed_url", str(result))
    except Exception as exc:
        raise WhatsAppAPIError(
            message=f"Failed to generate signed URL: {exc}",
            operation="get_signed_url",
            details={"bucket": bucket, "path": path},
        ) from exc
