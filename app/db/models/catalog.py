"""Pydantic models for the catalog table.

Maps the ``catalog`` table defined in migration 005 to typed
Pydantic v2 models.  Three variants:

* **CatalogItem** — full row returned from the database.
* **CatalogItemCreate** — fields required (or optional) for INSERT.
* **CatalogItemUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import MedicineForm


class CatalogItem(BaseModel):
    """Full catalog row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        medicine_name: Display name of the medicine.
        generic_name: Generic / salt name.
        brand_name: Brand / trade name.
        manufacturer: Manufacturing company.
        category: Therapeutic category.
        form: Dosage form (tablet, syrup, etc.).
        strength: Dosage strength string.
        unit: Sale unit (strip, bottle, etc.).
        units_per_pack: How many units in one pack.
        price_per_unit_paisas: Selling price per unit in paisas.
        mrp_paisas: Maximum retail price in paisas.
        stock_quantity: Current stock count.
        reserved_quantity: Quantity reserved by pending orders.
        low_stock_threshold: Alert threshold.
        is_in_stock: Whether currently in stock.
        allow_order_when_out_of_stock: Accept orders even when OOS.
        requires_prescription: Prescription-only flag.
        is_controlled_substance: Controlled-substance flag.
        search_keywords: Additional search terms.
        sku: Stock keeping unit code.
        barcode: Barcode string.
        image_url: URL to product image.
        is_active: Soft-active flag.
        is_deleted: Soft-delete flag.
        deleted_at: Timestamp of soft deletion.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    distributor_id: UUID
    medicine_name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    form: Optional[MedicineForm] = None
    strength: Optional[str] = None
    unit: Optional[str] = None
    units_per_pack: int = 1
    price_per_unit_paisas: int
    mrp_paisas: Optional[int] = None
    stock_quantity: int = 0
    reserved_quantity: int = 0
    low_stock_threshold: int = 10
    is_in_stock: bool = True
    allow_order_when_out_of_stock: bool = True
    requires_prescription: bool = False
    is_controlled_substance: bool = False
    search_keywords: list[str] = Field(default_factory=list)
    sku: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CatalogItemCreate(BaseModel):
    """Fields for creating a new catalog item.

    Attributes:
        distributor_id: FK to distributors — tenant boundary.
        medicine_name: Display name of the medicine.
        generic_name: Generic / salt name.
        brand_name: Brand / trade name.
        manufacturer: Manufacturing company.
        category: Therapeutic category.
        form: Dosage form.
        strength: Dosage strength string.
        unit: Sale unit.
        units_per_pack: Units in one pack.
        price_per_unit_paisas: Selling price per unit in paisas.
        mrp_paisas: Maximum retail price in paisas.
        stock_quantity: Initial stock count.
        low_stock_threshold: Alert threshold.
        is_in_stock: In-stock flag.
        allow_order_when_out_of_stock: Accept OOS orders flag.
        requires_prescription: Prescription-only flag.
        is_controlled_substance: Controlled-substance flag.
        search_keywords: Additional search terms.
        sku: SKU code.
        barcode: Barcode string.
        image_url: Product image URL.
        metadata: Arbitrary JSONB metadata.
    """

    distributor_id: UUID
    medicine_name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    form: Optional[MedicineForm] = None
    strength: Optional[str] = None
    unit: Optional[str] = None
    units_per_pack: int = 1
    price_per_unit_paisas: int
    mrp_paisas: Optional[int] = None
    stock_quantity: int = 0
    low_stock_threshold: int = 10
    is_in_stock: bool = True
    allow_order_when_out_of_stock: bool = True
    requires_prescription: bool = False
    is_controlled_substance: bool = False
    search_keywords: list[str] = Field(default_factory=list)
    sku: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CatalogItemUpdate(BaseModel):
    """Fields for updating a catalog item (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        medicine_name: Updated medicine name.
        generic_name: Updated generic name.
        brand_name: Updated brand name.
        manufacturer: Updated manufacturer.
        category: Updated category.
        form: Updated dosage form.
        strength: Updated strength.
        unit: Updated sale unit.
        units_per_pack: Updated units per pack.
        price_per_unit_paisas: Updated price in paisas.
        mrp_paisas: Updated MRP in paisas.
        stock_quantity: Updated stock count.
        reserved_quantity: Updated reserved count.
        low_stock_threshold: Updated alert threshold.
        is_in_stock: Updated in-stock flag.
        allow_order_when_out_of_stock: Updated OOS flag.
        requires_prescription: Updated prescription flag.
        is_controlled_substance: Updated controlled-substance flag.
        search_keywords: Updated search terms.
        sku: Updated SKU.
        barcode: Updated barcode.
        image_url: Updated image URL.
        is_active: Updated active flag.
        is_deleted: Updated delete flag.
        deleted_at: Updated deletion timestamp.
        metadata: Updated metadata dict.
    """

    medicine_name: Optional[str] = None
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    form: Optional[MedicineForm] = None
    strength: Optional[str] = None
    unit: Optional[str] = None
    units_per_pack: Optional[int] = None
    price_per_unit_paisas: Optional[int] = None
    mrp_paisas: Optional[int] = None
    stock_quantity: Optional[int] = None
    reserved_quantity: Optional[int] = None
    low_stock_threshold: Optional[int] = None
    is_in_stock: Optional[bool] = None
    allow_order_when_out_of_stock: Optional[bool] = None
    requires_prescription: Optional[bool] = None
    is_controlled_substance: Optional[bool] = None
    search_keywords: Optional[list[str]] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_deleted: Optional[bool] = None
    deleted_at: Optional[datetime] = None
    metadata: Optional[dict] = None
