"""Unit tests for app.whatsapp.message_types payload builders."""

from __future__ import annotations

import pytest

from app.whatsapp.message_types import (
    build_audio_message,
    build_button_message,
    build_document_message,
    build_image_message,
    build_list_message,
    build_location_message,
    build_read_receipt,
    build_reaction_message,
    build_template_message,
    build_text_message,
)


# ── Text ─────────────────────────────────────────────────────────────


class TestBuildTextMessage:
    """Tests for build_text_message."""

    def test_basic_text(self) -> None:
        result = build_text_message("+923001234567", "Salam!")
        assert result["messaging_product"] == "whatsapp"
        assert result["to"] == "+923001234567"
        assert result["type"] == "text"
        assert result["text"]["body"] == "Salam!"
        assert result["text"]["preview_url"] is False

    def test_preview_url_enabled(self) -> None:
        result = build_text_message("+923001234567", "Check: https://example.com", preview_url=True)
        assert result["text"]["preview_url"] is True

    def test_truncates_at_4096(self) -> None:
        long_text = "A" * 5000
        result = build_text_message("+923001234567", long_text)
        assert len(result["text"]["body"]) == 4096


# ── Buttons ──────────────────────────────────────────────────────────


class TestBuildButtonMessage:
    """Tests for build_button_message."""

    def test_two_buttons(self) -> None:
        result = build_button_message(
            "+923001234567",
            "Choose:",
            [("confirm", "✅ Confirm"), ("cancel", "❌ Cancel")],
        )
        assert result["type"] == "interactive"
        interactive = result["interactive"]
        assert interactive["type"] == "button"
        assert len(interactive["action"]["buttons"]) == 2
        assert interactive["action"]["buttons"][0]["reply"]["id"] == "confirm"
        assert interactive["action"]["buttons"][0]["reply"]["title"] == "✅ Confirm"

    def test_max_three_buttons(self) -> None:
        buttons = [(f"btn_{i}", f"Button {i}") for i in range(5)]
        result = build_button_message("+923001234567", "Pick one:", buttons)
        assert len(result["interactive"]["action"]["buttons"]) == 3

    def test_title_truncated_at_20(self) -> None:
        result = build_button_message(
            "+923001234567",
            "Body",
            [("id1", "A" * 30)],
        )
        title = result["interactive"]["action"]["buttons"][0]["reply"]["title"]
        assert len(title) == 20

    def test_with_header_and_footer(self) -> None:
        result = build_button_message(
            "+923001234567",
            "Body",
            [("id1", "Yes")],
            header="Header",
            footer="Footer",
        )
        assert result["interactive"]["header"]["text"] == "Header"
        assert result["interactive"]["footer"]["text"] == "Footer"


# ── List ─────────────────────────────────────────────────────────────


class TestBuildListMessage:
    """Tests for build_list_message."""

    def test_single_section(self) -> None:
        sections = [
            {
                "title": "Medicines",
                "rows": [
                    {"id": "med_1", "title": "Paracetamol 500mg", "description": "Strip — PKR 35"},
                ],
            },
        ]
        result = build_list_message("+923001234567", "Choose:", "Dekho", sections)
        assert result["type"] == "interactive"
        assert result["interactive"]["type"] == "list"
        assert result["interactive"]["action"]["button"] == "Dekho"
        assert len(result["interactive"]["action"]["sections"]) == 1
        assert result["interactive"]["action"]["sections"][0]["rows"][0]["id"] == "med_1"

    def test_button_label_truncated(self) -> None:
        result = build_list_message("+923001234567", "Body", "A" * 30, [])
        assert len(result["interactive"]["action"]["button"]) == 20

    def test_row_title_truncated(self) -> None:
        sections = [
            {
                "title": "Section",
                "rows": [
                    {"id": "r1", "title": "A" * 50, "description": "B" * 100},
                ],
            },
        ]
        result = build_list_message("+923001234567", "Body", "Go", sections)
        row = result["interactive"]["action"]["sections"][0]["rows"][0]
        assert len(row["title"]) == 24
        assert len(row["description"]) == 72


# ── Template ─────────────────────────────────────────────────────────


class TestBuildTemplateMessage:
    """Tests for build_template_message."""

    def test_basic_template(self) -> None:
        result = build_template_message(
            "+923001234567",
            "payment_reminder_7d",
            "en",
        )
        assert result["type"] == "template"
        assert result["template"]["name"] == "payment_reminder_7d"
        assert result["template"]["language"]["code"] == "en"
        assert "components" not in result["template"]

    def test_with_body_parameters(self) -> None:
        params = [{"type": "text", "text": "PKR 8,500"}]
        result = build_template_message(
            "+923001234567",
            "payment_reminder",
            "ur",
            body_parameters=params,
        )
        components = result["template"]["components"]
        assert len(components) == 1
        assert components[0]["type"] == "body"
        assert components[0]["parameters"] == params

    def test_with_header_and_body(self) -> None:
        result = build_template_message(
            "+923001234567",
            "order_update",
            "en",
            header_parameters=[{"type": "text", "text": "#ORD-001"}],
            body_parameters=[{"type": "text", "text": "Confirmed"}],
        )
        components = result["template"]["components"]
        assert len(components) == 2
        assert components[0]["type"] == "header"
        assert components[1]["type"] == "body"


# ── Media ────────────────────────────────────────────────────────────


class TestBuildImageMessage:
    """Tests for build_image_message."""

    def test_basic_image(self) -> None:
        result = build_image_message("+923001234567", "https://example.com/img.jpg")
        assert result["type"] == "image"
        assert result["image"]["link"] == "https://example.com/img.jpg"
        assert "caption" not in result["image"]

    def test_with_caption(self) -> None:
        result = build_image_message("+923001234567", "https://example.com/img.jpg", caption="Photo")
        assert result["image"]["caption"] == "Photo"

    def test_caption_truncated(self) -> None:
        result = build_image_message("+923001234567", "https://example.com/img.jpg", caption="X" * 2000)
        assert len(result["image"]["caption"]) == 1024


class TestBuildDocumentMessage:
    """Tests for build_document_message."""

    def test_basic_document(self) -> None:
        result = build_document_message("+923001234567", "https://example.com/report.pdf", "report.pdf")
        assert result["type"] == "document"
        assert result["document"]["link"] == "https://example.com/report.pdf"
        assert result["document"]["filename"] == "report.pdf"


class TestBuildAudioMessage:
    """Tests for build_audio_message."""

    def test_basic_audio(self) -> None:
        result = build_audio_message("+923001234567", "https://example.com/audio.mp3")
        assert result["type"] == "audio"
        assert result["audio"]["link"] == "https://example.com/audio.mp3"


# ── Reaction ─────────────────────────────────────────────────────────


class TestBuildReactionMessage:
    """Tests for build_reaction_message."""

    def test_reaction(self) -> None:
        result = build_reaction_message("+923001234567", "wamid.abc123", "👍")
        assert result["type"] == "reaction"
        assert result["reaction"]["message_id"] == "wamid.abc123"
        assert result["reaction"]["emoji"] == "👍"


# ── Location ─────────────────────────────────────────────────────────


class TestBuildLocationMessage:
    """Tests for build_location_message."""

    def test_basic_location(self) -> None:
        result = build_location_message("+923001234567", 24.8607, 67.0011)
        assert result["type"] == "location"
        assert result["location"]["latitude"] == 24.8607
        assert result["location"]["longitude"] == 67.0011

    def test_with_name_and_address(self) -> None:
        result = build_location_message(
            "+923001234567", 24.8607, 67.0011,
            name="Office", address="Karachi",
        )
        assert result["location"]["name"] == "Office"
        assert result["location"]["address"] == "Karachi"


# ── Read Receipt ─────────────────────────────────────────────────────


class TestBuildReadReceipt:
    """Tests for build_read_receipt."""

    def test_read_receipt(self) -> None:
        result = build_read_receipt("wamid.abc123")
        assert result["messaging_product"] == "whatsapp"
        assert result["status"] == "read"
        assert result["message_id"] == "wamid.abc123"
