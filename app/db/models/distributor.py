"""Pydantic models for the distributors table.

Maps the ``distributors`` table defined in migration 003 to typed
Pydantic v2 models.  Three variants:

* **Distributor** — full row returned from the database.
* **DistributorCreate** — fields required (or optional) for INSERT.
* **DistributorUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import Language, SubscriptionStatus


class Distributor(BaseModel):
    """Full distributor row returned from DB.

    Attributes:
        id: Primary key UUID.
        business_name: Registered business name.
        owner_name: Name of the distributor owner.
        whatsapp_number: E.164 WhatsApp number for this distributor.
        whatsapp_phone_number_id: Meta Cloud API phone-number ID.
        whatsapp_group_id: Optional group ID for distributor notifications.
        city: City where the distributor operates.
        address: Physical address.
        cnic_encrypted: Fernet-encrypted CNIC string.
        email: Contact email.
        plan_id: FK to subscription_plans.
        subscription_status: Current subscription lifecycle state.
        subscription_start: When the current subscription began.
        subscription_end: When the current subscription expires.
        trial_end: When the trial period ends.
        grace_period_days: Days after expiry before suspension.
        deployment_version: Deployed TELETRAAN version tag.
        bot_language_default: Default conversation language.
        catalog_last_synced: Last successful catalog sync timestamp.
        catalog_sync_url: Google Drive / URL for catalog sync.
        onboarding_completed: Whether distributor finished onboarding.
        onboarding_completed_at: Timestamp of onboarding completion.
        preferred_payment_gateway: Default payment gateway identifier.
        is_active: Soft-active flag.
        is_deleted: Soft-delete flag.
        deleted_at: Timestamp of soft deletion.
        notes: Free-form internal notes.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    business_name: str
    owner_name: str
    whatsapp_number: str
    whatsapp_phone_number_id: str
    whatsapp_group_id: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    cnic_encrypted: Optional[str] = None
    email: Optional[str] = None
    plan_id: Optional[UUID] = None
    subscription_status: SubscriptionStatus = SubscriptionStatus.TRIAL
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    grace_period_days: int = 3
    deployment_version: Optional[str] = None
    bot_language_default: Language = Language.ROMAN_URDU
    catalog_last_synced: Optional[datetime] = None
    catalog_sync_url: Optional[str] = None
    onboarding_completed: bool = False
    onboarding_completed_at: Optional[datetime] = None
    preferred_payment_gateway: Optional[str] = None
    is_active: bool = True
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DistributorCreate(BaseModel):
    """Fields for creating a new distributor.

    Attributes:
        business_name: Registered business name.
        owner_name: Name of the distributor owner.
        whatsapp_number: E.164 WhatsApp number.
        whatsapp_phone_number_id: Meta Cloud API phone-number ID.
        whatsapp_group_id: Optional group ID for notifications.
        city: City of operation.
        address: Physical address.
        cnic_encrypted: Fernet-encrypted CNIC.
        email: Contact email.
        plan_id: FK to subscription_plans.
        subscription_status: Initial subscription state.
        subscription_start: When subscription begins.
        subscription_end: When subscription expires.
        trial_end: When trial ends.
        grace_period_days: Days of grace after expiry.
        bot_language_default: Default conversation language.
        catalog_sync_url: Google Drive / URL for catalog sync.
        preferred_payment_gateway: Default payment gateway.
        notes: Free-form internal notes.
        metadata: Arbitrary JSONB metadata.
    """

    business_name: str
    owner_name: str
    whatsapp_number: str
    whatsapp_phone_number_id: str
    whatsapp_group_id: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    cnic_encrypted: Optional[str] = None
    email: Optional[str] = None
    plan_id: Optional[UUID] = None
    subscription_status: SubscriptionStatus = SubscriptionStatus.TRIAL
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    grace_period_days: int = 3
    bot_language_default: Language = Language.ROMAN_URDU
    catalog_sync_url: Optional[str] = None
    preferred_payment_gateway: Optional[str] = None
    notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class DistributorUpdate(BaseModel):
    """Fields for updating a distributor (all optional).

    Only non-``None`` fields are written to the database, allowing
    granular PATCH-style updates without touching unchanged columns.

    Attributes:
        business_name: Updated business name.
        owner_name: Updated owner name.
        whatsapp_group_id: Updated group ID.
        city: Updated city.
        address: Updated address.
        cnic_encrypted: Updated encrypted CNIC.
        email: Updated email.
        plan_id: Updated subscription plan.
        subscription_status: Updated subscription state.
        subscription_start: Updated subscription start.
        subscription_end: Updated subscription end.
        trial_end: Updated trial end.
        grace_period_days: Updated grace period.
        deployment_version: Updated version tag.
        bot_language_default: Updated default language.
        catalog_last_synced: Updated catalog sync timestamp.
        catalog_sync_url: Updated catalog sync URL.
        onboarding_completed: Updated onboarding flag.
        onboarding_completed_at: Updated onboarding timestamp.
        preferred_payment_gateway: Updated payment gateway.
        is_active: Updated active flag.
        is_deleted: Updated soft-delete flag.
        deleted_at: Updated deletion timestamp.
        notes: Updated notes.
        metadata: Updated metadata dict.
    """

    business_name: Optional[str] = None
    owner_name: Optional[str] = None
    whatsapp_group_id: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    cnic_encrypted: Optional[str] = None
    email: Optional[str] = None
    plan_id: Optional[UUID] = None
    subscription_status: Optional[SubscriptionStatus] = None
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    grace_period_days: Optional[int] = None
    deployment_version: Optional[str] = None
    bot_language_default: Optional[Language] = None
    catalog_last_synced: Optional[datetime] = None
    catalog_sync_url: Optional[str] = None
    onboarding_completed: Optional[bool] = None
    onboarding_completed_at: Optional[datetime] = None
    preferred_payment_gateway: Optional[str] = None
    is_active: Optional[bool] = None
    is_deleted: Optional[bool] = None
    deleted_at: Optional[datetime] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None
