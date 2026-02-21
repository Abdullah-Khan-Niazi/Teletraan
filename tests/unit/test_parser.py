"""Unit tests for app.whatsapp.parser webhook payload parsing."""

from __future__ import annotations

import pytest

from app.whatsapp.parser import (
    IncomingMessageType,
    StatusUpdateType,
    parse_webhook_payload,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _wrap_message(
    msg: dict,
    phone_number_id: str = "1234567890",
    contacts: list | None = None,
) -> dict:
    """Wrap a message dict in the full Meta webhook payload structure."""
    value: dict = {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "+923001234567",
            "phone_number_id": phone_number_id,
        },
        "messages": [msg],
    }
    if contacts is not None:
        value["contacts"] = contacts
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "entry_1", "changes": [{"value": value, "field": "messages"}]}],
    }


def _wrap_status(status: dict) -> dict:
    """Wrap a status dict in the full Meta webhook payload structure."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "1234567890"},
                            "statuses": [status],
                        },
                        "field": "messages",
                    },
                ],
            },
        ],
    }


# ── Text ─────────────────────────────────────────────────────────────


class TestParseTextMessage:
    """Tests for text message parsing."""

    def test_basic_text(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.text001",
                "timestamp": "1700000000",
                "type": "text",
                "text": {"body": "Paracetamol 500mg 10 strip"},
            },
            contacts=[
                {"profile": {"name": "Ahmed"}, "wa_id": "+923001234567"},
            ],
        )
        result = parse_webhook_payload(payload)

        assert len(result.messages) == 1
        msg = result.messages[0]
        assert msg.message_id == "wamid.text001"
        assert msg.from_number == "+923001234567"
        assert msg.sender_name == "Ahmed"
        assert msg.phone_number_id == "1234567890"
        assert msg.message_type == IncomingMessageType.TEXT
        assert msg.text == "Paracetamol 500mg 10 strip"

    def test_text_without_contacts(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.text002",
                "timestamp": "1700000000",
                "type": "text",
                "text": {"body": "Hello"},
            },
        )
        result = parse_webhook_payload(payload)
        assert result.messages[0].sender_name == ""


# ── Audio ────────────────────────────────────────────────────────────


class TestParseAudioMessage:
    """Tests for audio (voice) message parsing."""

    def test_audio_message(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.audio001",
                "timestamp": "1700000000",
                "type": "audio",
                "audio": {
                    "id": "media_id_audio_123",
                    "mime_type": "audio/ogg; codecs=opus",
                    "sha256": "abc123sha",
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]

        assert msg.message_type == IncomingMessageType.AUDIO
        assert msg.media is not None
        assert msg.media.media_id == "media_id_audio_123"
        assert msg.media.mime_type == "audio/ogg; codecs=opus"
        assert msg.media.sha256 == "abc123sha"


# ── Image ────────────────────────────────────────────────────────────


class TestParseImageMessage:
    """Tests for image message parsing."""

    def test_image_with_caption(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.img001",
                "timestamp": "1700000000",
                "type": "image",
                "image": {
                    "id": "media_id_img_123",
                    "mime_type": "image/jpeg",
                    "sha256": "imgsha",
                    "caption": "Complaint photo",
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]

        assert msg.message_type == IncomingMessageType.IMAGE
        assert msg.media is not None
        assert msg.media.media_id == "media_id_img_123"
        assert msg.media.caption == "Complaint photo"
        assert msg.text == "Complaint photo"  # caption also in text

    def test_image_without_caption(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.img002",
                "timestamp": "1700000000",
                "type": "image",
                "image": {
                    "id": "media_id_img_456",
                    "mime_type": "image/png",
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]
        assert msg.text is None
        assert msg.media.caption is None


# ── Interactive — Button Reply ───────────────────────────────────────


class TestParseButtonReply:
    """Tests for interactive button reply parsing."""

    def test_button_reply(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.btn001",
                "timestamp": "1700000000",
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {
                        "id": "confirm_order",
                        "title": "✅ Confirm",
                    },
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]

        assert msg.message_type == IncomingMessageType.BUTTON_REPLY
        assert msg.interactive_reply is not None
        assert msg.interactive_reply.reply_id == "confirm_order"
        assert msg.interactive_reply.title == "✅ Confirm"


# ── Interactive — List Reply ─────────────────────────────────────────


class TestParseListReply:
    """Tests for interactive list reply parsing."""

    def test_list_reply(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.list001",
                "timestamp": "1700000000",
                "type": "interactive",
                "interactive": {
                    "type": "list_reply",
                    "list_reply": {
                        "id": "catalog_uuid_1",
                        "title": "Paracetamol 500mg",
                        "description": "Strip — PKR 35",
                    },
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]

        assert msg.message_type == IncomingMessageType.LIST_REPLY
        assert msg.interactive_reply is not None
        assert msg.interactive_reply.reply_id == "catalog_uuid_1"
        assert msg.interactive_reply.description == "Strip — PKR 35"


# ── Reaction ─────────────────────────────────────────────────────────


class TestParseReaction:
    """Tests for reaction message parsing."""

    def test_reaction(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.react001",
                "timestamp": "1700000000",
                "type": "reaction",
                "reaction": {
                    "message_id": "wamid.text001",
                    "emoji": "👍",
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]

        assert msg.message_type == IncomingMessageType.REACTION
        assert msg.reaction_emoji == "👍"
        assert msg.reaction_message_id == "wamid.text001"


# ── Location ─────────────────────────────────────────────────────────


class TestParseLocation:
    """Tests for location message parsing."""

    def test_location(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.loc001",
                "timestamp": "1700000000",
                "type": "location",
                "location": {
                    "latitude": 24.8607,
                    "longitude": 67.0011,
                    "name": "Karachi Office",
                    "address": "Clifton Block 5",
                },
            },
        )
        result = parse_webhook_payload(payload)
        msg = result.messages[0]

        assert msg.message_type == IncomingMessageType.LOCATION
        assert msg.location is not None
        assert msg.location.latitude == 24.8607
        assert msg.location.name == "Karachi Office"


# ── Sticker / Contacts / Unsupported ────────────────────────────────


class TestParseSpecialTypes:
    """Tests for sticker, contacts, and unsupported types."""

    def test_sticker(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.stk001",
                "timestamp": "1700000000",
                "type": "sticker",
                "sticker": {
                    "id": "media_stk_123",
                    "mime_type": "image/webp",
                },
            },
        )
        result = parse_webhook_payload(payload)
        assert result.messages[0].message_type == IncomingMessageType.STICKER

    def test_contacts(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.cnt001",
                "timestamp": "1700000000",
                "type": "contacts",
                "contacts": [{"name": {"formatted_name": "Test"}}],
            },
        )
        result = parse_webhook_payload(payload)
        assert result.messages[0].message_type == IncomingMessageType.CONTACTS

    def test_unknown_type_falls_to_unsupported(self) -> None:
        payload = _wrap_message(
            {
                "from": "+923001234567",
                "id": "wamid.unk001",
                "timestamp": "1700000000",
                "type": "ephemeral",
            },
        )
        result = parse_webhook_payload(payload)
        assert result.messages[0].message_type == IncomingMessageType.UNSUPPORTED


# ── Status Updates ───────────────────────────────────────────────────


class TestParseStatusUpdates:
    """Tests for delivery status update parsing."""

    def test_delivered_status(self) -> None:
        payload = _wrap_status(
            {
                "id": "wamid.text001",
                "status": "delivered",
                "timestamp": "1700000001",
                "recipient_id": "+923001234567",
            },
        )
        result = parse_webhook_payload(payload)

        assert len(result.statuses) == 1
        status = result.statuses[0]
        assert status.message_id == "wamid.text001"
        assert status.status == StatusUpdateType.DELIVERED
        assert status.recipient_id == "+923001234567"

    def test_failed_status_with_errors(self) -> None:
        payload = _wrap_status(
            {
                "id": "wamid.text002",
                "status": "failed",
                "timestamp": "1700000002",
                "recipient_id": "+923009876543",
                "errors": [{"code": 131026, "title": "Message undeliverable"}],
            },
        )
        result = parse_webhook_payload(payload)
        status = result.statuses[0]
        assert status.status == StatusUpdateType.FAILED
        assert len(status.errors) == 1
        assert status.errors[0]["code"] == 131026

    def test_read_status(self) -> None:
        payload = _wrap_status(
            {
                "id": "wamid.text003",
                "status": "read",
                "timestamp": "1700000003",
                "recipient_id": "+923001234567",
            },
        )
        result = parse_webhook_payload(payload)
        assert result.statuses[0].status == StatusUpdateType.READ

    def test_unknown_status_skipped(self) -> None:
        payload = _wrap_status(
            {
                "id": "wamid.text004",
                "status": "unknown_status",
                "timestamp": "1700000004",
                "recipient_id": "+923001234567",
            },
        )
        result = parse_webhook_payload(payload)
        assert len(result.statuses) == 0


# ── Edge Cases ───────────────────────────────────────────────────────


class TestParserEdgeCases:
    """Tests for parser robustness."""

    def test_empty_payload(self) -> None:
        result = parse_webhook_payload({})
        assert len(result.messages) == 0
        assert len(result.statuses) == 0

    def test_missing_messages_key(self) -> None:
        payload = {
            "entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "123"}}}]}],
        }
        result = parse_webhook_payload(payload)
        assert len(result.messages) == 0

    def test_multiple_messages_in_one_webhook(self) -> None:
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123"},
                                "messages": [
                                    {
                                        "from": "+923001111111",
                                        "id": "wamid.m1",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": "Order 1"},
                                    },
                                    {
                                        "from": "+923002222222",
                                        "id": "wamid.m2",
                                        "timestamp": "1700000001",
                                        "type": "text",
                                        "text": {"body": "Order 2"},
                                    },
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        result = parse_webhook_payload(payload)
        assert len(result.messages) == 2
        assert result.messages[0].text == "Order 1"
        assert result.messages[1].text == "Order 2"

    def test_malformed_message_skipped(self) -> None:
        """Message missing required 'id' field should be skipped."""
        payload = _wrap_message(
            {
                "from": "+923001234567",
                # "id" is missing — required field
                "timestamp": "1700000000",
                "type": "text",
                "text": {"body": "Hello"},
            },
        )
        result = parse_webhook_payload(payload)
        assert len(result.messages) == 0  # skipped, not raised

    def test_mixed_messages_and_statuses(self) -> None:
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123"},
                                "messages": [
                                    {
                                        "from": "+923001234567",
                                        "id": "wamid.m1",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": "Hello"},
                                    },
                                ],
                                "statuses": [
                                    {
                                        "id": "wamid.s1",
                                        "status": "delivered",
                                        "timestamp": "1700000001",
                                        "recipient_id": "+923009876543",
                                    },
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        result = parse_webhook_payload(payload)
        assert len(result.messages) == 1
        assert len(result.statuses) == 1
