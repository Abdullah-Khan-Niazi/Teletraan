"""Pydantic models for the customers table.

Maps the ``customers`` table defined in migration 004 to typed
Pydantic v2 models.  Three variants:

* **Customer** — full row returned from the database.
* **CustomerCreate** — fields required (or optional) for INSERT.
* **CustomerUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import Language


class Customer(BaseModel):
    """Full customer row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        whatsapp_number: E.164 WhatsApp number.
        name: Customer full name.
        shop_name: Retail shop / pharmacy name.
        address: Delivery address.
        city: City of the customer.
        delivery_zone_id: FK to delivery_zones.
        language_preference: Preferred conversation language.
        is_verified: Whether identity has been verified.
        credit_limit_paisas: Max credit allowed in paisas.
        outstanding_balance_paisas: Current outstanding balance in paisas.
        is_active: Soft-active flag.
        is_blocked: Whether the customer is blocked.
        blocked_reason: Reason for blocking.
        blocked_at: Timestamp of block action.
        last_order_at: Timestamp of most recent order.
        total_orders: Lifetime order count.
        total_spend_paisas: Lifetime spend in paisas.
        tags: Freeform tags for segmentation.
        notes: Internal notes.
        metadata: Arbitrary JSONB metadata.
        registered_at: When the customer registered.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    distributor_id: UUID
    whatsapp_number: str
    name: str
    shop_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    delivery_zone_id: Optional[UUID] = None
    language_preference: Language = Language.ROMAN_URDU
    is_verified: bool = False
    credit_limit_paisas: int = 0
    outstanding_balance_paisas: int = 0
    is_active: bool = True
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
    total_orders: int = 0
    total_spend_paisas: int = 0
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    registered_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerCreate(BaseModel):
    """Fields for creating a new customer.

    Attributes:
        distributor_id: FK to distributors — tenant boundary.
        whatsapp_number: E.164 WhatsApp number.
        name: Customer full name.
        shop_name: Retail shop / pharmacy name.
        address: Delivery address.
        city: City of the customer.
        delivery_zone_id: FK to delivery_zones.
        language_preference: Preferred conversation language.
        is_verified: Whether identity has been verified.
        credit_limit_paisas: Max credit allowed in paisas.
        tags: Freeform tags.
        notes: Internal notes.
        metadata: Arbitrary JSONB metadata.
    """

    distributor_id: UUID
    whatsapp_number: str
    name: str
    shop_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    delivery_zone_id: Optional[UUID] = None
    language_preference: Language = Language.ROMAN_URDU
    is_verified: bool = False
    credit_limit_paisas: int = 0
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CustomerUpdate(BaseModel):
    """Fields for updating a customer (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        name: Updated customer name.
        shop_name: Updated shop name.
        address: Updated delivery address.
        city: Updated city.
        delivery_zone_id: Updated delivery zone.
        language_preference: Updated language preference.
        is_verified: Updated verification flag.
        credit_limit_paisas: Updated credit limit in paisas.
        outstanding_balance_paisas: Updated outstanding balance in paisas.
        is_active: Updated active flag.
        is_blocked: Updated block flag.
        blocked_reason: Updated block reason.
        blocked_at: Updated block timestamp.
        last_order_at: Updated last order timestamp.
        total_orders: Updated order count.
        total_spend_paisas: Updated total spend in paisas.
        tags: Updated tags list.
        notes: Updated internal notes.
        metadata: Updated metadata dict.
    """

    name: Optional[str] = None
    shop_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    delivery_zone_id: Optional[UUID] = None
    language_preference: Optional[Language] = None
    is_verified: Optional[bool] = None
    credit_limit_paisas: Optional[int] = None
    outstanding_balance_paisas: Optional[int] = None
    is_active: Optional[bool] = None
    is_blocked: Optional[bool] = None
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
    total_orders: Optional[int] = None
    total_spend_paisas: Optional[int] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None
