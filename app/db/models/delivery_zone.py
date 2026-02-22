"""Pydantic models for the delivery_zones table."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DeliveryZone(BaseModel):
    """Full delivery zone row from the database.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        name: Zone display name.
        areas: List of area/locality names in this zone.
        delivery_days: Days of the week for delivery.
        estimated_delivery_hours: ETA in hours.
        delivery_charges_paisas: Flat delivery charge in paisas.
        minimum_order_for_free_delivery_paisas: Order value for free
            delivery (None = no free delivery threshold).
        is_active: Whether this zone is active.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    distributor_id: UUID
    name: str
    areas: list[str] = Field(default_factory=list)
    delivery_days: list[str] = Field(default_factory=list)
    estimated_delivery_hours: int = 24
    delivery_charges_paisas: int = 0
    minimum_order_for_free_delivery_paisas: Optional[int] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeliveryZoneCreate(BaseModel):
    """Payload for creating a new delivery zone.

    Attributes:
        distributor_id: Tenant FK.
        name: Zone display name.
        areas: Area/locality names.
        delivery_days: Week day names.
        estimated_delivery_hours: ETA in hours.
        delivery_charges_paisas: Charge in paisas.
        minimum_order_for_free_delivery_paisas: Free delivery threshold.
    """

    distributor_id: UUID
    name: str
    areas: list[str] = Field(default_factory=list)
    delivery_days: list[str] = Field(default_factory=list)
    estimated_delivery_hours: int = 24
    delivery_charges_paisas: int = 0
    minimum_order_for_free_delivery_paisas: Optional[int] = None
