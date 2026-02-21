"""Pydantic models for the prospects table.

Maps the ``prospects`` table defined in migration 015 to typed
Pydantic v2 models.  Three variants:

* **Prospect** — full row returned from the database.
* **ProspectCreate** — fields required (or optional) for INSERT.
* **ProspectUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import ProspectStatus


class Prospect(BaseModel):
    """Full prospect row returned from DB.

    Attributes:
        id: Primary key UUID.
        whatsapp_number: E.164 WhatsApp number (unique).
        name: Contact name.
        business_name: Business / company name.
        business_type: Type of business (e.g. distributor, wholesaler).
        city: City of operation.
        estimated_retailer_count: Estimated number of retailers served.
        monthly_order_estimate: Estimated monthly order volume.
        interested_service_id: FK to service_registry.
        status: Sales funnel lifecycle state.
        demo_booked_at: When a demo was booked.
        demo_slot: Scheduled demo date/time.
        converted_at: When prospect converted to distributor.
        converted_distributor_id: FK to distributors (after conversion).
        lost_reason: Reason the prospect was marked lost.
        waitlist_service: Service they are waitlisted for.
        follow_up_at: Next follow-up timestamp.
        preferred_payment_gateway: Preferred gateway identifier.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    whatsapp_number: str
    name: Optional[str] = None
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    city: Optional[str] = None
    estimated_retailer_count: Optional[int] = None
    monthly_order_estimate: Optional[int] = None
    interested_service_id: Optional[UUID] = None
    status: ProspectStatus = ProspectStatus.NEW
    demo_booked_at: Optional[datetime] = None
    demo_slot: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    converted_distributor_id: Optional[UUID] = None
    lost_reason: Optional[str] = None
    waitlist_service: Optional[str] = None
    follow_up_at: Optional[datetime] = None
    preferred_payment_gateway: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProspectCreate(BaseModel):
    """Fields for creating a new prospect.

    Attributes:
        whatsapp_number: E.164 WhatsApp number.
        name: Contact name.
        business_name: Business / company name.
        business_type: Type of business.
        city: City of operation.
        estimated_retailer_count: Estimated retailers served.
        monthly_order_estimate: Estimated monthly orders.
        interested_service_id: FK to service_registry.
        status: Initial funnel state.
        preferred_payment_gateway: Preferred gateway.
        metadata: Arbitrary metadata.
    """

    whatsapp_number: str
    name: Optional[str] = None
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    city: Optional[str] = None
    estimated_retailer_count: Optional[int] = None
    monthly_order_estimate: Optional[int] = None
    interested_service_id: Optional[UUID] = None
    status: ProspectStatus = ProspectStatus.NEW
    preferred_payment_gateway: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ProspectUpdate(BaseModel):
    """Fields for updating a prospect (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        name: Updated contact name.
        business_name: Updated business name.
        business_type: Updated business type.
        city: Updated city.
        estimated_retailer_count: Updated retailer count.
        monthly_order_estimate: Updated order estimate.
        interested_service_id: Updated service interest.
        status: Updated funnel state.
        demo_booked_at: Updated demo booking timestamp.
        demo_slot: Updated demo slot.
        converted_at: Updated conversion timestamp.
        converted_distributor_id: Updated converted distributor FK.
        lost_reason: Updated lost reason.
        waitlist_service: Updated waitlist service.
        follow_up_at: Updated follow-up timestamp.
        preferred_payment_gateway: Updated gateway preference.
        metadata: Updated metadata dict.
    """

    name: Optional[str] = None
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    city: Optional[str] = None
    estimated_retailer_count: Optional[int] = None
    monthly_order_estimate: Optional[int] = None
    interested_service_id: Optional[UUID] = None
    status: Optional[ProspectStatus] = None
    demo_booked_at: Optional[datetime] = None
    demo_slot: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    converted_distributor_id: Optional[UUID] = None
    lost_reason: Optional[str] = None
    waitlist_service: Optional[str] = None
    follow_up_at: Optional[datetime] = None
    preferred_payment_gateway: Optional[str] = None
    metadata: Optional[dict] = None
