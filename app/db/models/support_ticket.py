"""Pydantic models for the support_tickets table.

Maps the ``support_tickets`` table defined in migration 014 to typed
Pydantic v2 models.  Three variants:

* **SupportTicket** — full row returned from the database.
* **SupportTicketCreate** — fields required (or optional) for INSERT.
* **SupportTicketUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import (
    ComplaintPriority,
    SupportTicketCategory,
    SupportTicketStatus,
)


class SupportTicket(BaseModel):
    """Full support_ticket row returned from DB.

    Attributes:
        id: Primary key UUID.
        ticket_number: Unique human-readable ticket number.
        distributor_id: FK to distributors — tenant boundary.
        category: Ticket category.
        description: Distributor's issue description.
        status: Ticket lifecycle state.
        priority: Urgency level (reuses ComplaintPriority).
        owner_response: TELETRAAN owner's response text.
        resolved_at: Resolution timestamp.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    ticket_number: str
    distributor_id: UUID
    category: Optional[SupportTicketCategory] = None
    description: str
    status: SupportTicketStatus = SupportTicketStatus.OPEN
    priority: ComplaintPriority = ComplaintPriority.NORMAL
    owner_response: Optional[str] = None
    resolved_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupportTicketCreate(BaseModel):
    """Fields for creating a new support ticket.

    Attributes:
        ticket_number: Unique ticket number.
        distributor_id: FK to distributors.
        category: Ticket category.
        description: Issue description text.
        status: Initial ticket state.
        priority: Urgency level.
        metadata: Arbitrary metadata.
    """

    ticket_number: str
    distributor_id: UUID
    category: Optional[SupportTicketCategory] = None
    description: str
    status: SupportTicketStatus = SupportTicketStatus.OPEN
    priority: ComplaintPriority = ComplaintPriority.NORMAL
    metadata: dict = Field(default_factory=dict)


class SupportTicketUpdate(BaseModel):
    """Fields for updating a support ticket (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        category: Updated category.
        description: Updated description.
        status: Updated ticket state.
        priority: Updated priority.
        owner_response: Updated owner response.
        resolved_at: Updated resolution timestamp.
        metadata: Updated metadata dict.
    """

    category: Optional[SupportTicketCategory] = None
    description: Optional[str] = None
    status: Optional[SupportTicketStatus] = None
    priority: Optional[ComplaintPriority] = None
    owner_response: Optional[str] = None
    resolved_at: Optional[datetime] = None
    metadata: Optional[dict] = None
