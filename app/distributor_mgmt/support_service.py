"""Support ticket system — create, prioritize, resolve, notify.

Distributors file support tickets via WhatsApp.  The TELETRAAN owner
receives notifications for new and updated tickets.  Resolution
confirmations are sent back to the distributor.

Ticket numbers are generated as ``TKT-{YYYYMMDD}-{seq}`` where
``seq`` is a zero-padded sequence derived from the current
microsecond to avoid collisions in a single-owner system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.config import get_settings
from app.core.constants import (
    ActorType,
    ComplaintPriority,
    RecipientType,
    SupportTicketCategory,
    SupportTicketStatus,
)
from app.db.models.audit import AuditLogCreate, ScheduledMessageCreate
from app.db.models.support_ticket import (
    SupportTicket,
    SupportTicketCreate,
    SupportTicketUpdate,
)
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.scheduled_message_repo import (
    ScheduledMessageRepository,
)
from app.db.repositories.support_ticket_repo import SupportTicketRepository


class SupportService:
    """Manages the full lifecycle of support tickets.

    Handles creation, priority assignment, owner notification,
    resolution flow, and distributor confirmation.

    Attributes:
        _ticket_repo: Support ticket repository.
        _dist_repo: Distributor repository.
        _msg_repo: Scheduled message repository.
        _audit_repo: Audit log repository.
    """

    def __init__(self) -> None:
        self._ticket_repo = SupportTicketRepository()
        self._dist_repo = DistributorRepository()
        self._msg_repo = ScheduledMessageRepository()
        self._audit_repo = AuditRepository()

    # ── Ticket creation ─────────────────────────────────────────────

    async def create_ticket(
        self,
        *,
        distributor_id: str,
        description: str,
        category: Optional[SupportTicketCategory] = None,
        priority: ComplaintPriority = ComplaintPriority.NORMAL,
        metadata: Optional[dict] = None,
    ) -> SupportTicket:
        """Create a new support ticket and notify the owner.

        Args:
            distributor_id: UUID of the filing distributor.
            description: Issue description from the distributor.
            category: Ticket category (optional, auto-detected later).
            priority: Urgency level (default NORMAL).
            metadata: Additional context.

        Returns:
            The created SupportTicket.

        Raises:
            DatabaseError: On creation failure.
        """
        ticket_number = self._generate_ticket_number()

        ticket_data = SupportTicketCreate(
            ticket_number=ticket_number,
            distributor_id=distributor_id,
            category=category,
            description=description,
            priority=priority,
            metadata=metadata or {},
        )

        ticket = await self._ticket_repo.create(ticket_data)

        # Notify owner about new ticket
        await self._notify_owner_new_ticket(
            ticket=ticket,
            distributor_id=distributor_id,
        )

        # Confirm receipt to distributor
        await self._send_receipt_confirmation(
            ticket=ticket,
            distributor_id=distributor_id,
        )

        # Audit
        await self._audit_ticket(
            ticket_id=str(ticket.id),
            distributor_id=distributor_id,
            action="support.ticket_created",
            actor_type=ActorType.DISTRIBUTOR,
            metadata={
                "ticket_number": ticket_number,
                "category": category.value if category else None,
                "priority": priority.value,
            },
        )

        logger.info(
            "support.ticket_created",
            ticket_number=ticket_number,
            distributor_id=distributor_id,
            priority=priority.value,
        )

        return ticket

    # ── Ticket resolution ───────────────────────────────────────────

    async def resolve_ticket(
        self,
        ticket_id: str,
        *,
        response: str,
        actor_id: Optional[str] = None,
    ) -> SupportTicket:
        """Resolve a support ticket and notify the distributor.

        Args:
            ticket_id: UUID of the ticket to resolve.
            response: Owner's resolution response text.
            actor_id: Optional owner UUID.

        Returns:
            The updated SupportTicket.

        Raises:
            NotFoundError: If ticket not found.
            DatabaseError: On update failure.
        """
        ticket = await self._ticket_repo.get_by_id_or_raise(ticket_id)

        now = datetime.now(tz=timezone.utc)
        update = SupportTicketUpdate(
            status=SupportTicketStatus.RESOLVED,
            owner_response=response,
            resolved_at=now,
        )
        updated_ticket = await self._ticket_repo.update(ticket_id, update)

        # Notify distributor about resolution
        await self._send_resolution_notification(
            ticket=updated_ticket,
            distributor_id=str(ticket.distributor_id),
        )

        # Audit
        await self._audit_ticket(
            ticket_id=ticket_id,
            distributor_id=str(ticket.distributor_id),
            action="support.ticket_resolved",
            actor_type=ActorType.OWNER,
            actor_id=actor_id,
            metadata={
                "ticket_number": ticket.ticket_number,
                "response_length": len(response),
            },
        )

        logger.info(
            "support.ticket_resolved",
            ticket_number=ticket.ticket_number,
            ticket_id=ticket_id,
        )

        return updated_ticket

    async def close_ticket(
        self,
        ticket_id: str,
        *,
        actor_id: Optional[str] = None,
    ) -> SupportTicket:
        """Close a resolved or open ticket.

        Args:
            ticket_id: UUID of the ticket to close.
            actor_id: Optional actor UUID.

        Returns:
            The updated SupportTicket.

        Raises:
            NotFoundError: If ticket not found.
            DatabaseError: On update failure.
        """
        ticket = await self._ticket_repo.get_by_id_or_raise(ticket_id)

        update = SupportTicketUpdate(
            status=SupportTicketStatus.CLOSED,
        )
        updated_ticket = await self._ticket_repo.update(ticket_id, update)

        await self._audit_ticket(
            ticket_id=ticket_id,
            distributor_id=str(ticket.distributor_id),
            action="support.ticket_closed",
            actor_type=ActorType.OWNER,
            actor_id=actor_id,
            metadata={"ticket_number": ticket.ticket_number},
        )

        logger.info(
            "support.ticket_closed",
            ticket_number=ticket.ticket_number,
            ticket_id=ticket_id,
        )

        return updated_ticket

    # ── Ticket updates ──────────────────────────────────────────────

    async def update_priority(
        self,
        ticket_id: str,
        priority: ComplaintPriority,
        *,
        actor_id: Optional[str] = None,
    ) -> SupportTicket:
        """Update a ticket's priority level.

        Args:
            ticket_id: UUID of the ticket.
            priority: New priority level.
            actor_id: Optional actor UUID.

        Returns:
            The updated SupportTicket.

        Raises:
            NotFoundError: If ticket not found.
            DatabaseError: On update failure.
        """
        ticket = await self._ticket_repo.get_by_id_or_raise(ticket_id)
        old_priority = ticket.priority

        update = SupportTicketUpdate(priority=priority)
        updated_ticket = await self._ticket_repo.update(ticket_id, update)

        await self._audit_ticket(
            ticket_id=ticket_id,
            distributor_id=str(ticket.distributor_id),
            action="support.priority_changed",
            actor_type=ActorType.OWNER,
            actor_id=actor_id,
            metadata={
                "old_priority": old_priority.value,
                "new_priority": priority.value,
            },
        )

        return updated_ticket

    async def assign_in_progress(
        self,
        ticket_id: str,
        *,
        actor_id: Optional[str] = None,
    ) -> SupportTicket:
        """Mark a ticket as in-progress.

        Args:
            ticket_id: UUID of the ticket.
            actor_id: Optional actor UUID.

        Returns:
            The updated SupportTicket.

        Raises:
            NotFoundError: If ticket not found.
            DatabaseError: On update failure.
        """
        update = SupportTicketUpdate(
            status=SupportTicketStatus.IN_PROGRESS,
        )
        updated_ticket = await self._ticket_repo.update(ticket_id, update)

        ticket = await self._ticket_repo.get_by_id_or_raise(ticket_id)
        await self._audit_ticket(
            ticket_id=ticket_id,
            distributor_id=str(ticket.distributor_id),
            action="support.ticket_in_progress",
            actor_type=ActorType.OWNER,
            actor_id=actor_id,
            metadata={"ticket_number": ticket.ticket_number},
        )

        return updated_ticket

    # ── Query methods ───────────────────────────────────────────────

    async def get_open_tickets(
        self,
        distributor_id: str,
    ) -> list[SupportTicket]:
        """Get all open/in-progress tickets for a distributor.

        Args:
            distributor_id: UUID of the distributor.

        Returns:
            List of open SupportTicket entities.
        """
        return await self._ticket_repo.get_open_tickets(distributor_id)

    async def get_all_open_tickets(self) -> list[SupportTicket]:
        """Get all open/in-progress tickets across all distributors.

        Returns:
            List of open SupportTicket entities (owner view).
        """
        return await self._ticket_repo.get_all_open_tickets()

    async def get_ticket_by_number(
        self,
        ticket_number: str,
    ) -> Optional[SupportTicket]:
        """Look up a ticket by its human-readable number.

        Args:
            ticket_number: Ticket number string (e.g., TKT-20250101-1234).

        Returns:
            SupportTicket if found, None otherwise.
        """
        return await self._ticket_repo.get_by_ticket_number(ticket_number)

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _generate_ticket_number() -> str:
        """Generate a unique ticket number.

        Format: ``TKT-{YYYYMMDD}-{microsecond_seq}``

        Returns:
            Ticket number string.
        """
        now = datetime.now(tz=timezone.utc)
        date_part = now.strftime("%Y%m%d")
        seq = str(now.microsecond).zfill(6)[:4]
        return f"TKT-{date_part}-{seq}"

    async def _notify_owner_new_ticket(
        self,
        *,
        ticket: SupportTicket,
        distributor_id: str,
    ) -> None:
        """Send a notification to the TELETRAAN owner about a new ticket.

        Args:
            ticket: The newly created ticket.
            distributor_id: UUID of the filing distributor.
        """
        try:
            settings = get_settings()
            distributor = await self._dist_repo.get_by_id(distributor_id)
            dist_name = (
                distributor.business_name if distributor else "Unknown"
            )

            priority_emoji = {
                ComplaintPriority.LOW: "🟢",
                ComplaintPriority.NORMAL: "🟡",
                ComplaintPriority.HIGH: "🟠",
                ComplaintPriority.URGENT: "🔴",
            }
            emoji = priority_emoji.get(ticket.priority, "🟡")

            text = (
                f"{emoji} New Support Ticket: {ticket.ticket_number}\n\n"
                f"From: {dist_name}\n"
                f"Priority: {ticket.priority.value.upper()}\n"
                f"Category: {ticket.category.value if ticket.category else 'N/A'}\n\n"
                f"Description:\n{ticket.description[:500]}\n\n"
                f"Reply with: RESOLVE {ticket.ticket_number} <response>"
            )

            idempotency_key = f"ticket_owner:{ticket.ticket_number}:new"

            msg_data = ScheduledMessageCreate(
                recipient_number=settings.owner_whatsapp_number,
                recipient_type=RecipientType.OWNER,
                message_type="support_ticket_new",
                message_payload={
                    "text": text,
                    "ticket_number": ticket.ticket_number,
                    "distributor_id": distributor_id,
                    "priority": ticket.priority.value,
                },
                scheduled_for=datetime.now(tz=timezone.utc),
                reference_id=ticket.id,
                reference_type="support_ticket",
                idempotency_key=idempotency_key,
            )

            await self._msg_repo.create(msg_data)
        except Exception as exc:
            logger.error(
                "support.owner_notification_failed",
                ticket_number=ticket.ticket_number,
                error=str(exc),
            )

    async def _send_receipt_confirmation(
        self,
        *,
        ticket: SupportTicket,
        distributor_id: str,
    ) -> None:
        """Send a ticket receipt confirmation to the distributor.

        Args:
            ticket: The newly created ticket.
            distributor_id: UUID of the distributor.
        """
        try:
            distributor = await self._dist_repo.get_by_id(distributor_id)
            if not distributor:
                return

            text = (
                f"✅ Support ticket created: {ticket.ticket_number}\n\n"
                f"We've received your request and will respond shortly.\n"
                f"Priority: {ticket.priority.value.upper()}"
            )

            idempotency_key = f"ticket_receipt:{ticket.ticket_number}"

            msg_data = ScheduledMessageCreate(
                distributor_id=distributor.id,
                recipient_number=distributor.whatsapp_number,
                recipient_type=RecipientType.DISTRIBUTOR,
                message_type="support_ticket_receipt",
                message_payload={
                    "text": text,
                    "ticket_number": ticket.ticket_number,
                },
                scheduled_for=datetime.now(tz=timezone.utc),
                reference_id=ticket.id,
                reference_type="support_ticket",
                idempotency_key=idempotency_key,
            )

            await self._msg_repo.create(msg_data)
        except Exception as exc:
            logger.error(
                "support.receipt_notification_failed",
                ticket_number=ticket.ticket_number,
                error=str(exc),
            )

    async def _send_resolution_notification(
        self,
        *,
        ticket: SupportTicket,
        distributor_id: str,
    ) -> None:
        """Send a resolution notification to the distributor.

        Args:
            ticket: The resolved ticket.
            distributor_id: UUID of the distributor.
        """
        try:
            distributor = await self._dist_repo.get_by_id(distributor_id)
            if not distributor:
                return

            text = (
                f"📬 Ticket Resolved: {ticket.ticket_number}\n\n"
                f"Response:\n{ticket.owner_response or 'No details provided.'}\n\n"
                f"If the issue persists, reply with your concern and "
                f"we'll reopen the ticket."
            )

            idempotency_key = f"ticket_resolved:{ticket.ticket_number}"

            msg_data = ScheduledMessageCreate(
                distributor_id=distributor.id,
                recipient_number=distributor.whatsapp_number,
                recipient_type=RecipientType.DISTRIBUTOR,
                message_type="support_ticket_resolved",
                message_payload={
                    "text": text,
                    "ticket_number": ticket.ticket_number,
                    "owner_response": ticket.owner_response,
                },
                scheduled_for=datetime.now(tz=timezone.utc),
                reference_id=ticket.id,
                reference_type="support_ticket",
                idempotency_key=idempotency_key,
            )

            await self._msg_repo.create(msg_data)
        except Exception as exc:
            logger.error(
                "support.resolution_notification_failed",
                ticket_number=ticket.ticket_number,
                error=str(exc),
            )

    async def _audit_ticket(
        self,
        *,
        ticket_id: str,
        distributor_id: str,
        action: str,
        actor_type: ActorType,
        actor_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Write a support ticket audit log entry.

        Never raises — audit failures are logged but don't block.

        Args:
            ticket_id: UUID of the ticket.
            distributor_id: UUID of the distributor.
            action: Audit action string.
            actor_type: Who triggered.
            actor_id: Optional actor UUID.
            metadata: Additional metadata.
        """
        try:
            audit_entry = AuditLogCreate(
                actor_type=actor_type,
                actor_id=actor_id,
                distributor_id=distributor_id,
                action=action,
                entity_type="support_ticket",
                entity_id=ticket_id,
                metadata=metadata or {},
            )
            await self._audit_repo.create(audit_entry)
        except Exception as exc:
            logger.error(
                "support.audit_failed",
                ticket_id=ticket_id,
                action=action,
                error=str(exc),
            )


# ── Module singleton ────────────────────────────────────────────────

support_service = SupportService()
