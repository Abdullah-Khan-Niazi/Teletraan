"""Webhook payload parser for incoming Meta WhatsApp Cloud API events.

Converts raw JSON from ``POST /webhook`` into typed dataclasses that
the rest of the application can consume without touching raw dicts.

Handles all documented incoming message types:
    text, audio, image, video, document, sticker, location, contacts,
    interactive (button_reply, list_reply), reaction, unsupported.

Also extracts status-update events (sent, delivered, read, failed).
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any

from loguru import logger


# ── Enums ────────────────────────────────────────────────────────────


class IncomingMessageType(StrEnum):
    """All recognised incoming message types."""

    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACTS = "contacts"
    BUTTON_REPLY = "button_reply"
    LIST_REPLY = "list_reply"
    REACTION = "reaction"
    UNSUPPORTED = "unsupported"


class StatusUpdateType(StrEnum):
    """WhatsApp message delivery status types."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# ── Dataclasses ──────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True, slots=True)
class MediaInfo:
    """Metadata for an attached media file."""

    media_id: str
    mime_type: str
    sha256: str | None = None
    caption: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class LocationInfo:
    """Location data from an incoming message."""

    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class InteractiveReply:
    """Extracted reply data from interactive button or list selection."""

    reply_id: str
    title: str
    description: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedMessage:
    """Normalised representation of a single incoming WhatsApp message.

    Attributes:
        message_id: Unique WhatsApp message ID (for dedup + read receipts).
        from_number: Sender phone number in E.164 format.
        sender_name: Profile name reported by WhatsApp (may be empty).
        phone_number_id: The business phone number that received the message.
        timestamp: Unix timestamp string from Meta.
        message_type: Classified ``IncomingMessageType``.
        text: Body text for ``TEXT`` messages, or caption for media.
        media: ``MediaInfo`` for audio/image/video/document/sticker.
        location: ``LocationInfo`` for location messages.
        interactive_reply: ``InteractiveReply`` for button/list replies.
        reaction_emoji: Emoji string for reaction messages.
        reaction_message_id: Target message ID for reactions.
        raw: The original message dict for debugging.
    """

    message_id: str
    from_number: str
    sender_name: str
    phone_number_id: str
    timestamp: str
    message_type: IncomingMessageType
    text: str | None = None
    media: MediaInfo | None = None
    location: LocationInfo | None = None
    interactive_reply: InteractiveReply | None = None
    reaction_emoji: str | None = None
    reaction_message_id: str | None = None
    raw: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedStatusUpdate:
    """Normalised representation of a delivery status update.

    Attributes:
        message_id: The message this status refers to.
        status: One of sent / delivered / read / failed.
        recipient_id: Recipient phone number.
        timestamp: Unix timestamp string from Meta.
        errors: List of error dicts (populated on ``failed`` status).
    """

    message_id: str
    status: StatusUpdateType
    recipient_id: str
    timestamp: str
    errors: list[dict[str, Any]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True, slots=True)
class WebhookParseResult:
    """Aggregated result of parsing a full webhook payload.

    A single webhook POST can contain multiple messages and/or status
    updates. This object collects them all.
    """

    messages: list[ParsedMessage] = dataclasses.field(default_factory=list)
    statuses: list[ParsedStatusUpdate] = dataclasses.field(default_factory=list)


# ── Parser ───────────────────────────────────────────────────────────


def parse_webhook_payload(payload: dict[str, Any]) -> WebhookParseResult:
    """Parse an incoming Meta webhook JSON payload.

    Extracts all messages and status updates from every entry/change in
    the payload.  Unknown or malformed items are logged and skipped —
    parsing never raises.

    Args:
        payload: The raw JSON body from ``POST /webhook``.

    Returns:
        ``WebhookParseResult`` with lists of messages and status updates.
    """
    messages: list[ParsedMessage] = []
    statuses: list[ParsedStatusUpdate] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = (
                value.get("metadata", {}).get("phone_number_id", "")
            )

            # ── messages ─────────────────────────────────────────
            for msg in value.get("messages", []):
                parsed = _parse_single_message(msg, phone_number_id, value)
                if parsed is not None:
                    messages.append(parsed)

            # ── status updates ───────────────────────────────────
            for status in value.get("statuses", []):
                parsed_status = _parse_status_update(status)
                if parsed_status is not None:
                    statuses.append(parsed_status)

    logger.debug(
        "webhook.parsed",
        message_count=len(messages),
        status_count=len(statuses),
    )
    return WebhookParseResult(messages=messages, statuses=statuses)


# ── Internal helpers ─────────────────────────────────────────────────


def _extract_sender_name(value: dict[str, Any], from_number: str) -> str:
    """Look up profile name from the contacts list in the webhook value."""
    for contact in value.get("contacts", []):
        if contact.get("wa_id") == from_number:
            return contact.get("profile", {}).get("name", "")
    return ""


def _parse_single_message(
    msg: dict[str, Any],
    phone_number_id: str,
    value: dict[str, Any],
) -> ParsedMessage | None:
    """Parse a single message dict into a ``ParsedMessage``."""
    try:
        message_id = msg["id"]
        from_number = msg["from"]
        timestamp = msg.get("timestamp", "")
        msg_type_raw = msg.get("type", "unsupported")
        sender_name = _extract_sender_name(value, from_number)

        # ── text ─────────────────────────────────────────────────
        if msg_type_raw == "text":
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.TEXT,
                text=msg.get("text", {}).get("body", ""),
                raw=msg,
            )

        # ── audio ────────────────────────────────────────────────
        if msg_type_raw == "audio":
            audio = msg.get("audio", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.AUDIO,
                media=MediaInfo(
                    media_id=audio.get("id", ""),
                    mime_type=audio.get("mime_type", "audio/ogg"),
                    sha256=audio.get("sha256"),
                ),
                raw=msg,
            )

        # ── image ────────────────────────────────────────────────
        if msg_type_raw == "image":
            image = msg.get("image", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.IMAGE,
                text=image.get("caption"),
                media=MediaInfo(
                    media_id=image.get("id", ""),
                    mime_type=image.get("mime_type", "image/jpeg"),
                    sha256=image.get("sha256"),
                    caption=image.get("caption"),
                ),
                raw=msg,
            )

        # ── video ────────────────────────────────────────────────
        if msg_type_raw == "video":
            video = msg.get("video", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.VIDEO,
                text=video.get("caption"),
                media=MediaInfo(
                    media_id=video.get("id", ""),
                    mime_type=video.get("mime_type", "video/mp4"),
                    sha256=video.get("sha256"),
                    caption=video.get("caption"),
                ),
                raw=msg,
            )

        # ── document ─────────────────────────────────────────────
        if msg_type_raw == "document":
            doc = msg.get("document", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.DOCUMENT,
                text=doc.get("caption"),
                media=MediaInfo(
                    media_id=doc.get("id", ""),
                    mime_type=doc.get("mime_type", "application/octet-stream"),
                    sha256=doc.get("sha256"),
                    caption=doc.get("caption"),
                ),
                raw=msg,
            )

        # ── sticker ──────────────────────────────────────────────
        if msg_type_raw == "sticker":
            sticker = msg.get("sticker", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.STICKER,
                media=MediaInfo(
                    media_id=sticker.get("id", ""),
                    mime_type=sticker.get("mime_type", "image/webp"),
                    sha256=sticker.get("sha256"),
                ),
                raw=msg,
            )

        # ── location ─────────────────────────────────────────────
        if msg_type_raw == "location":
            loc = msg.get("location", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.LOCATION,
                location=LocationInfo(
                    latitude=loc.get("latitude", 0.0),
                    longitude=loc.get("longitude", 0.0),
                    name=loc.get("name"),
                    address=loc.get("address"),
                ),
                raw=msg,
            )

        # ── contacts ─────────────────────────────────────────────
        if msg_type_raw == "contacts":
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.CONTACTS,
                raw=msg,
            )

        # ── interactive (button_reply / list_reply) ──────────────
        if msg_type_raw == "interactive":
            interactive = msg.get("interactive", {})
            interactive_type = interactive.get("type", "")

            if interactive_type == "button_reply":
                reply = interactive.get("button_reply", {})
                return ParsedMessage(
                    message_id=message_id,
                    from_number=from_number,
                    sender_name=sender_name,
                    phone_number_id=phone_number_id,
                    timestamp=timestamp,
                    message_type=IncomingMessageType.BUTTON_REPLY,
                    interactive_reply=InteractiveReply(
                        reply_id=reply.get("id", ""),
                        title=reply.get("title", ""),
                    ),
                    raw=msg,
                )

            if interactive_type == "list_reply":
                reply = interactive.get("list_reply", {})
                return ParsedMessage(
                    message_id=message_id,
                    from_number=from_number,
                    sender_name=sender_name,
                    phone_number_id=phone_number_id,
                    timestamp=timestamp,
                    message_type=IncomingMessageType.LIST_REPLY,
                    interactive_reply=InteractiveReply(
                        reply_id=reply.get("id", ""),
                        title=reply.get("title", ""),
                        description=reply.get("description"),
                    ),
                    raw=msg,
                )

            logger.warning(
                "parser.unknown_interactive_type",
                interactive_type=interactive_type,
                message_id=message_id,
            )

        # ── reaction ─────────────────────────────────────────────
        if msg_type_raw == "reaction":
            reaction = msg.get("reaction", {})
            return ParsedMessage(
                message_id=message_id,
                from_number=from_number,
                sender_name=sender_name,
                phone_number_id=phone_number_id,
                timestamp=timestamp,
                message_type=IncomingMessageType.REACTION,
                reaction_emoji=reaction.get("emoji"),
                reaction_message_id=reaction.get("message_id"),
                raw=msg,
            )

        # ── unsupported / unknown ────────────────────────────────
        logger.info(
            "parser.unsupported_message_type",
            message_type=msg_type_raw,
            message_id=message_id,
        )
        return ParsedMessage(
            message_id=message_id,
            from_number=from_number,
            sender_name=sender_name,
            phone_number_id=phone_number_id,
            timestamp=timestamp,
            message_type=IncomingMessageType.UNSUPPORTED,
            raw=msg,
        )

    except KeyError as exc:
        logger.error(
            "parser.missing_required_field",
            field=str(exc),
            raw=str(msg)[:500],
        )
        return None
    except Exception as exc:
        logger.error(
            "parser.unexpected_error",
            error=str(exc),
            raw=str(msg)[:500],
        )
        return None


def _parse_status_update(
    status: dict[str, Any],
) -> ParsedStatusUpdate | None:
    """Parse a single status-update dict."""
    try:
        raw_status = status.get("status", "")
        try:
            typed_status = StatusUpdateType(raw_status)
        except ValueError:
            logger.warning(
                "parser.unknown_status_type",
                status=raw_status,
            )
            return None

        return ParsedStatusUpdate(
            message_id=status["id"],
            status=typed_status,
            recipient_id=status.get("recipient_id", ""),
            timestamp=status.get("timestamp", ""),
            errors=status.get("errors", []),
        )
    except KeyError as exc:
        logger.error(
            "parser.status_missing_field",
            field=str(exc),
            raw=str(status)[:500],
        )
        return None
    except Exception as exc:
        logger.error(
            "parser.status_unexpected_error",
            error=str(exc),
            raw=str(status)[:500],
        )
        return None
