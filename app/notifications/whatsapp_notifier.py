"""WhatsApp notification sender with logging, retry, and delivery tracking.

Wraps the low-level ``WhatsAppClient.send_message()`` with:
    - Notification logging to ``notifications_log`` table.
    - Delivery status tracking.
    - Language-aware template resolution.
    - Owner/customer recipient handling.

All outbound messages to customers and owner go through this service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.core.constants import DeliveryStatus, RecipientType
from app.db.models.audit import NotificationLogCreate
from app.db.repositories import notification_repo
from app.notifications.templates import get_template
from app.whatsapp.client import whatsapp_client
from app.whatsapp.message_types import (
    build_button_message,
    build_document_message,
    build_list_message,
    build_text_message,
)


class WhatsAppNotifier:
    """High-level notification service for sending WhatsApp messages.

    Every message sent through this service is:
        1. Resolved from templates (if template key provided).
        2. Sent via the WhatsApp client.
        3. Logged to ``notifications_log`` for audit and delivery tracking.
    """

    # ── Text messages ────────────────────────────────────────────────

    async def send_text(
        self,
        phone_number_id: str,
        to: str,
        text: str,
        *,
        distributor_id: str | None = None,
        recipient_type: str = RecipientType.CUSTOMER,
        notification_type: str = "message",
    ) -> str | None:
        """Send a plain text message and log it.

        Args:
            phone_number_id: Sender's WhatsApp phone number ID.
            to: Recipient phone number in E.164 format.
            text: Message body text.
            distributor_id: Distributor UUID for logging.
            recipient_type: ``"customer"`` or ``"distributor"``.
            notification_type: Category for logging (e.g. ``"order_update"``).

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        payload = build_text_message(to, text)
        return await self._send_and_log(
            phone_number_id=phone_number_id,
            to=to,
            payload=payload,
            distributor_id=distributor_id,
            recipient_type=recipient_type,
            notification_type=notification_type,
            content_preview=text[:200],
        )

    async def send_template_text(
        self,
        phone_number_id: str,
        to: str,
        template_key: str,
        language: str = "roman_urdu",
        *,
        template_kwargs: dict[str, Any] | None = None,
        distributor_id: str | None = None,
        recipient_type: str = RecipientType.CUSTOMER,
        notification_type: str = "message",
    ) -> str | None:
        """Resolve a template and send as text message.

        Args:
            phone_number_id: Sender's WhatsApp phone number ID.
            to: Recipient phone number in E.164 format.
            template_key: Template constant name (e.g. ``"GREETING_NEW_CUSTOMER"``).
            language: Language code for template resolution.
            template_kwargs: Keyword arguments to format the template.
            distributor_id: Distributor UUID for logging.
            recipient_type: Recipient type for logging.
            notification_type: Category for logging.

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        template = get_template(template_key, language)
        text = template.format(**(template_kwargs or {}))
        return await self.send_text(
            phone_number_id=phone_number_id,
            to=to,
            text=text,
            distributor_id=distributor_id,
            recipient_type=recipient_type,
            notification_type=notification_type,
        )

    # ── Button messages ──────────────────────────────────────────────

    async def send_buttons(
        self,
        phone_number_id: str,
        to: str,
        body: str,
        buttons: list[tuple[str, str]],
        *,
        header: str | None = None,
        footer: str | None = None,
        distributor_id: str | None = None,
        notification_type: str = "interactive",
    ) -> str | None:
        """Send an interactive button message and log it.

        Args:
            phone_number_id: Sender's WhatsApp phone number ID.
            to: Recipient phone number in E.164 format.
            body: Main message text.
            buttons: Up to 3 ``(id, title)`` tuples.
            header: Optional header text.
            footer: Optional footer text.
            distributor_id: Distributor UUID for logging.
            notification_type: Category for logging.

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        payload = build_button_message(
            to, body, buttons, header=header, footer=footer,
        )
        return await self._send_and_log(
            phone_number_id=phone_number_id,
            to=to,
            payload=payload,
            distributor_id=distributor_id,
            recipient_type=RecipientType.CUSTOMER,
            notification_type=notification_type,
            content_preview=body[:200],
        )

    # ── List messages ────────────────────────────────────────────────

    async def send_list(
        self,
        phone_number_id: str,
        to: str,
        body: str,
        button_label: str,
        sections: list[dict[str, Any]],
        *,
        header: str | None = None,
        footer: str | None = None,
        distributor_id: str | None = None,
        notification_type: str = "interactive",
    ) -> str | None:
        """Send an interactive list message and log it.

        Args:
            phone_number_id: Sender's WhatsApp phone number ID.
            to: Recipient phone number in E.164 format.
            body: Main message text.
            button_label: CTA button text (max 20 chars).
            sections: Sections with rows for the list.
            header: Optional header text.
            footer: Optional footer text.
            distributor_id: Distributor UUID for logging.
            notification_type: Category for logging.

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        payload = build_list_message(
            to, body, button_label, sections,
            header=header, footer=footer,
        )
        return await self._send_and_log(
            phone_number_id=phone_number_id,
            to=to,
            payload=payload,
            distributor_id=distributor_id,
            recipient_type=RecipientType.CUSTOMER,
            notification_type=notification_type,
            content_preview=body[:200],
        )

    # ── Document messages ────────────────────────────────────────────

    async def send_document(
        self,
        phone_number_id: str,
        to: str,
        document_url: str,
        filename: str,
        *,
        caption: str | None = None,
        distributor_id: str | None = None,
        notification_type: str = "document",
    ) -> str | None:
        """Send a document (PDF, Excel) and log it.

        Args:
            phone_number_id: Sender's WhatsApp phone number ID.
            to: Recipient phone number in E.164 format.
            document_url: Signed or public URL for the document.
            filename: Display filename.
            caption: Optional caption.
            distributor_id: Distributor UUID for logging.
            notification_type: Category for logging.

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        payload = build_document_message(
            to, document_url, filename, caption=caption,
        )
        return await self._send_and_log(
            phone_number_id=phone_number_id,
            to=to,
            payload=payload,
            distributor_id=distributor_id,
            recipient_type=RecipientType.CUSTOMER,
            notification_type=notification_type,
            content_preview=f"[Document] {filename}",
        )

    # ── Owner notifications ──────────────────────────────────────────

    async def notify_owner(
        self,
        template_key: str,
        template_kwargs: dict[str, Any],
        *,
        distributor_id: str | None = None,
        notification_type: str = "owner_notification",
        language: str = "roman_urdu",
    ) -> str | None:
        """Send a notification to the system owner via WhatsApp.

        Uses ``OWNER_WHATSAPP_NUMBER`` and ``OWNER_PHONE_NUMBER_ID``
        from settings.

        Args:
            template_key: Template constant name from owner notification set.
            template_kwargs: Keyword arguments to format the template.
            distributor_id: Distributor UUID context for logging.
            notification_type: Category for logging.
            language: Language for template resolution.

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        settings = get_settings()
        template = get_template(template_key, language)
        text = template.format(**template_kwargs)

        payload = build_text_message(settings.owner_whatsapp_number, text)
        return await self._send_and_log(
            phone_number_id=settings.owner_phone_number_id,
            to=settings.owner_whatsapp_number,
            payload=payload,
            distributor_id=distributor_id,
            recipient_type=RecipientType.DISTRIBUTOR,
            notification_type=notification_type,
            content_preview=text[:200],
        )

    # ── Read receipt ─────────────────────────────────────────────────

    async def send_read_receipt(
        self,
        phone_number_id: str,
        message_id: str,
    ) -> None:
        """Mark a message as read. Non-critical — failures are logged only.

        Args:
            phone_number_id: The WhatsApp phone number ID.
            message_id: The message ID to mark as read.
        """
        await whatsapp_client.mark_as_read(phone_number_id, message_id)

    # ── Internal: send + log ─────────────────────────────────────────

    async def _send_and_log(
        self,
        *,
        phone_number_id: str,
        to: str,
        payload: dict[str, Any],
        distributor_id: str | None,
        recipient_type: str,
        notification_type: str,
        content_preview: str,
    ) -> str | None:
        """Send a message and log the outcome to notifications_log.

        Args:
            phone_number_id: Sender phone number ID.
            to: Recipient phone number.
            payload: Full message payload dict.
            distributor_id: Distributor UUID.
            recipient_type: customer or distributor.
            notification_type: Logging category.
            content_preview: Truncated content for logging.

        Returns:
            WhatsApp message ID on success, ``None`` on failure.
        """
        message_id: str | None = None
        delivery_status = DeliveryStatus.SENT
        error_message: str | None = None

        try:
            message_id = await whatsapp_client.send_message(
                phone_number_id, payload,
            )
            logger.info(
                "notifier.message_sent",
                message_id=message_id,
                recipient_suffix=to[-4:] if to else "????",
                notification_type=notification_type,
            )

        except Exception as exc:
            delivery_status = DeliveryStatus.FAILED
            error_message = str(exc)[:500]
            logger.error(
                "notifier.send_failed",
                recipient_suffix=to[-4:] if to else "????",
                notification_type=notification_type,
                error=error_message,
            )

        # Log to notifications_log table
        await self._log_notification(
            distributor_id=distributor_id,
            recipient_number=to,
            recipient_type=recipient_type,
            notification_type=notification_type,
            content_preview=content_preview,
            whatsapp_message_id=message_id,
            delivery_status=delivery_status,
            error_message=error_message,
        )

        return message_id

    async def _log_notification(
        self,
        *,
        distributor_id: str | None,
        recipient_number: str,
        recipient_type: str,
        notification_type: str,
        content_preview: str,
        whatsapp_message_id: str | None,
        delivery_status: str,
        error_message: str | None,
    ) -> None:
        """Persist notification record to the database.

        Never raises — logging failures are captured and logged to stderr.
        """
        try:
            # Mask phone number for storage — show only last 4 digits
            masked_number = f"****{recipient_number[-4:]}" if recipient_number else None

            log_data = NotificationLogCreate(
                distributor_id=distributor_id or "",
                recipient_number_masked=masked_number,
                recipient_type=recipient_type,
                notification_type=notification_type,
                message_preview=content_preview,
                whatsapp_message_id=whatsapp_message_id,
                delivery_status=delivery_status,
                error_message=error_message,
            )
            await notification_repo.create(log_data)
        except Exception as exc:
            # Non-critical — log failure should never break message flow
            logger.warning(
                "notifier.log_failed",
                error=str(exc),
                notification_type=notification_type,
            )


# ── Singleton ────────────────────────────────────────────────────────

whatsapp_notifier = WhatsAppNotifier()
