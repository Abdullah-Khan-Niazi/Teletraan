"""Outbound WhatsApp message payload builders.

Every function returns a ``dict`` that is JSON-serialisable and ready
to POST to ``/{phone_number_id}/messages`` on the Meta Cloud API.

Reference:
    https://developers.facebook.com/docs/whatsapp/cloud-api/messages
    Button title max 20 chars, button id max 256 chars.
    List row title max 24 chars, description max 72 chars.
    Text body max 4096 chars.
"""

from __future__ import annotations

from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────


def _base_payload(to: str, msg_type: str) -> dict[str, Any]:
    """Return the common root structure shared by every outbound message."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": msg_type,
    }


# ── Text ─────────────────────────────────────────────────────────────


def build_text_message(
    to: str,
    body: str,
    *,
    preview_url: bool = False,
) -> dict[str, Any]:
    """Build a plain-text message payload.

    Args:
        to: Recipient phone number in E.164 format.
        body: Message body text (max 4096 chars, no markdown).
        preview_url: Whether WhatsApp should render link previews.

    Returns:
        Message payload dict.
    """
    payload = _base_payload(to, "text")
    payload["text"] = {"preview_url": preview_url, "body": body[:4096]}
    return payload


# ── Interactive — Buttons (max 3) ────────────────────────────────────


def build_button_message(
    to: str,
    body: str,
    buttons: list[tuple[str, str]],
    *,
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Build an interactive button-reply message.

    Args:
        to: Recipient phone number in E.164 format.
        body: Main body text.
        buttons: Up to 3 ``(id, title)`` tuples.  ``id`` max 256 chars,
            ``title`` max 20 chars.
        header: Optional header text.
        footer: Optional footer text.

    Returns:
        Message payload dict.
    """
    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": bid[:256], "title": btitle[:20]},
                }
                for bid, btitle in buttons[:3]
            ],
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    payload = _base_payload(to, "interactive")
    payload["interactive"] = interactive
    return payload


# ── Interactive — List (max 10 rows across all sections) ─────────────


def build_list_message(
    to: str,
    body: str,
    button_label: str,
    sections: list[dict[str, Any]],
    *,
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Build an interactive list message.

    Args:
        to: Recipient phone number in E.164 format.
        body: Main body text explaining the list.
        button_label: CTA button text (max 20 chars).
        sections: List of section dicts, each containing ``title`` (str)
            and ``rows`` (list of dicts with ``id``, ``title``,
            optional ``description``).
        header: Optional header text.
        footer: Optional footer text.

    Returns:
        Message payload dict.

    Example section::

        {
            "title": "Best Matches",
            "rows": [
                {"id": "cat_uuid_1", "title": "Paracetamol 500mg",
                 "description": "Strip — PKR 35"},
            ],
        }
    """
    # Enforce Meta limits on label lengths
    sanitised_sections: list[dict[str, Any]] = []
    for section in sections:
        sanitised_rows = [
            {
                "id": row["id"][:200],
                "title": row["title"][:24],
                **(
                    {"description": row["description"][:72]}
                    if row.get("description")
                    else {}
                ),
            }
            for row in section.get("rows", [])
        ]
        sanitised_sections.append(
            {
                "title": section.get("title", "")[:24],
                "rows": sanitised_rows,
            }
        )

    interactive: dict[str, Any] = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": button_label[:20],
            "sections": sanitised_sections,
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    payload = _base_payload(to, "interactive")
    payload["interactive"] = interactive
    return payload


# ── Template ─────────────────────────────────────────────────────────


def build_template_message(
    to: str,
    template_name: str,
    lang_code: str,
    *,
    body_parameters: list[dict[str, Any]] | None = None,
    header_parameters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a pre-approved template message.

    Required for business-initiated messages outside the 24-hour window.

    Args:
        to: Recipient phone number in E.164 format.
        template_name: Approved template name from Meta Business Manager.
        lang_code: Language code (e.g. ``"en"``, ``"ur"``).
        body_parameters: List of component parameter dicts for the body.
        header_parameters: List of component parameter dicts for the header.

    Returns:
        Message payload dict.
    """
    components: list[dict[str, Any]] = []
    if header_parameters:
        components.append(
            {"type": "header", "parameters": header_parameters},
        )
    if body_parameters:
        components.append(
            {"type": "body", "parameters": body_parameters},
        )

    payload = _base_payload(to, "template")
    payload["template"] = {
        "name": template_name,
        "language": {"code": lang_code},
    }
    if components:
        payload["template"]["components"] = components
    return payload


# ── Media — Image ────────────────────────────────────────────────────


def build_image_message(
    to: str,
    image_url: str,
    *,
    caption: str | None = None,
) -> dict[str, Any]:
    """Build an image message with an optional caption.

    Args:
        to: Recipient phone number in E.164 format.
        image_url: Publicly accessible image URL.
        caption: Optional caption (max 1024 chars).

    Returns:
        Message payload dict.
    """
    image: dict[str, Any] = {"link": image_url}
    if caption:
        image["caption"] = caption[:1024]

    payload = _base_payload(to, "image")
    payload["image"] = image
    return payload


# ── Media — Document (PDF) ───────────────────────────────────────────


def build_document_message(
    to: str,
    document_url: str,
    filename: str,
    *,
    caption: str | None = None,
) -> dict[str, Any]:
    """Build a document message (PDF, Excel, etc.).

    Args:
        to: Recipient phone number in E.164 format.
        document_url: Publicly accessible or signed URL.
        filename: Display filename with extension.
        caption: Optional caption (max 1024 chars).

    Returns:
        Message payload dict.
    """
    document: dict[str, Any] = {"link": document_url, "filename": filename}
    if caption:
        document["caption"] = caption[:1024]

    payload = _base_payload(to, "document")
    payload["document"] = document
    return payload


# ── Media — Audio ────────────────────────────────────────────────────


def build_audio_message(
    to: str,
    audio_url: str,
) -> dict[str, Any]:
    """Build an audio message.

    Args:
        to: Recipient phone number in E.164 format.
        audio_url: Publicly accessible audio file URL.

    Returns:
        Message payload dict.
    """
    payload = _base_payload(to, "audio")
    payload["audio"] = {"link": audio_url}
    return payload


# ── Reaction ─────────────────────────────────────────────────────────


def build_reaction_message(
    to: str,
    message_id: str,
    emoji: str,
) -> dict[str, Any]:
    """Build a reaction to a specific message.

    Args:
        to: Recipient phone number in E.164 format.
        message_id: The WhatsApp message ID to react to.
        emoji: A single emoji character.

    Returns:
        Message payload dict.
    """
    payload = _base_payload(to, "reaction")
    payload["reaction"] = {"message_id": message_id, "emoji": emoji}
    return payload


# ── Location ─────────────────────────────────────────────────────────


def build_location_message(
    to: str,
    latitude: float,
    longitude: float,
    *,
    name: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """Build a location pin message.

    Args:
        to: Recipient phone number in E.164 format.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        name: Optional location name.
        address: Optional address string.

    Returns:
        Message payload dict.
    """
    location: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
    }
    if name:
        location["name"] = name
    if address:
        location["address"] = address

    payload = _base_payload(to, "location")
    payload["location"] = location
    return payload


# ── Read Receipt ─────────────────────────────────────────────────────


def build_read_receipt(message_id: str) -> dict[str, Any]:
    """Build a read-receipt payload for the given message.

    Args:
        message_id: The WhatsApp message ID to mark as read.

    Returns:
        Read-receipt payload dict.
    """
    return {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
