"""Pydantic models for the service_registry table.

The service_registry holds all TELETRAAN products and services that
can be offered through Channel B (the sales funnel).  Each entry
describes pricing, a sales-flow handler slug, and optional marketing
assets (demo video, catalog URL).

Financial amounts in **paisas** (BIGINT).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ServiceRegistryEntry(BaseModel):
    """Row read from ``service_registry`` table."""

    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    setup_fee_paisas: int = 0
    monthly_fee_paisas: int = 0
    demo_video_url: Optional[str] = None
    catalog_url: Optional[str] = None
    target_business_types: list[str] = Field(default_factory=list)
    sales_flow_handler: Optional[str] = None
    is_available: bool = True
    is_coming_soon: bool = False
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def setup_fee_pkr(self) -> float:
        """Setup fee in PKR (display only — never use for calculations)."""
        return self.setup_fee_paisas / 100

    @property
    def monthly_fee_pkr(self) -> float:
        """Monthly fee in PKR (display only — never use for calculations)."""
        return self.monthly_fee_paisas / 100

    def format_pricing(self) -> str:
        """Human-readable pricing line: 'PKR X,XXX/mo + PKR X,XXX setup'."""
        monthly = f"PKR {self.monthly_fee_pkr:,.0f}/mo"
        if self.setup_fee_paisas:
            return f"{monthly} + PKR {self.setup_fee_pkr:,.0f} setup"
        return monthly


class ServiceRegistryCreate(BaseModel):
    """INSERT payload for ``service_registry``."""

    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    setup_fee_paisas: int = 0
    monthly_fee_paisas: int = 0
    demo_video_url: Optional[str] = None
    catalog_url: Optional[str] = None
    target_business_types: list[str] = Field(default_factory=list)
    sales_flow_handler: Optional[str] = None
    is_available: bool = True
    is_coming_soon: bool = False
    metadata: dict = Field(default_factory=dict)


class ServiceRegistryUpdate(BaseModel):
    """Partial UPDATE payload for ``service_registry``."""

    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    setup_fee_paisas: Optional[int] = None
    monthly_fee_paisas: Optional[int] = None
    demo_video_url: Optional[str] = None
    catalog_url: Optional[str] = None
    target_business_types: Optional[list[str]] = None
    sales_flow_handler: Optional[str] = None
    is_available: Optional[bool] = None
    is_coming_soon: Optional[bool] = None
    metadata: Optional[dict] = None
