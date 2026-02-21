"""Pydantic models for the complaints table.

Maps the ``complaints`` table defined in migration 013 to typed
Pydantic v2 models.  Three variants:

* **Complaint** — full row returned from the database.
* **ComplaintCreate** — fields required (or optional) for INSERT.
* **ComplaintUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import ComplaintCategory, ComplaintPriority, ComplaintStatus


class Complaint(BaseModel):
    """Full complaint row returned from DB.

    Attributes:
        id: Primary key UUID.
        ticket_number: Unique human-readable ticket number.
        distributor_id: FK to distributors — tenant boundary.
        customer_id: FK to customers who filed the complaint.
        order_id: FK to the related order (optional).
        category: Complaint category.
        description: Customer's complaint description.
        status: Complaint lifecycle state.
        priority: Urgency level.
        resolution_notes: Notes recorded upon resolution.
        resolved_at: Resolution timestamp.
        escalated_to_owner: Whether escalated to the distributor owner.
        media_urls: URLs to attached media files.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    ticket_number: str
    distributor_id: UUID
    customer_id: UUID
    order_id: Optional[UUID] = None
    category: ComplaintCategory
    description: str
    status: ComplaintStatus = ComplaintStatus.OPEN
    priority: ComplaintPriority = ComplaintPriority.NORMAL
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    escalated_to_owner: bool = False
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComplaintCreate(BaseModel):
    """Fields for creating a new complaint.

    Attributes:
        ticket_number: Unique ticket number.
        distributor_id: FK to distributors.
        customer_id: FK to customers.
        order_id: FK to related order (optional).
        category: Complaint category.
        description: Complaint description text.
        status: Initial complaint state.
        priority: Urgency level.
        media_urls: Attached media URLs.
        metadata: Arbitrary metadata.
    """

    ticket_number: str
    distributor_id: UUID
    customer_id: UUID
    order_id: Optional[UUID] = None
    category: ComplaintCategory
    description: str
    status: ComplaintStatus = ComplaintStatus.OPEN
    priority: ComplaintPriority = ComplaintPriority.NORMAL
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ComplaintUpdate(BaseModel):
    """Fields for updating a complaint (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        category: Updated category.
        description: Updated description.
        status: Updated complaint state.
        priority: Updated priority.
        resolution_notes: Updated resolution notes.
        resolved_at: Updated resolution timestamp.
        escalated_to_owner: Updated escalation flag.
        media_urls: Updated media URL list.
        metadata: Updated metadata dict.
    """

    category: Optional[ComplaintCategory] = None
    description: Optional[str] = None
    status: Optional[ComplaintStatus] = None
    priority: Optional[ComplaintPriority] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    escalated_to_owner: Optional[bool] = None
    media_urls: Optional[list[str]] = None
    metadata: Optional[dict] = None
