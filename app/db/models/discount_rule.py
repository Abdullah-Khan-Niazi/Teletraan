"""Pydantic models for the discount_rules table."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import DiscountRuleType


class DiscountRule(BaseModel):
    """Full discount rule row from the database.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        catalog_id: FK to catalog item, or None for order-level rules.
        rule_name: Human-readable rule name.
        rule_type: Type of discount (bonus_units, percentage_discount, etc.).
        buy_quantity: For bonus rules — buy X quantity.
        get_quantity: For bonus rules — get Y free.
        discount_percentage: For percentage rules (0-100).
        discount_flat_paisas: For flat rules — fixed amount in paisas.
        minimum_order_quantity: Minimum qty to trigger this rule.
        minimum_order_value_paisas: Minimum order value to trigger.
        applicable_customer_tags: Customer tags this rule applies to.
        priority: Higher priority rules applied first.
        is_stackable: Whether this rule stacks with others.
        valid_from: Start of validity window.
        valid_until: End of validity window.
        usage_limit: Max times this rule can be used (None = unlimited).
        usage_count: Current usage count.
        is_active: Whether this rule is active.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    distributor_id: UUID
    catalog_id: Optional[UUID] = None
    rule_name: Optional[str] = None
    rule_type: str
    buy_quantity: Optional[int] = None
    get_quantity: Optional[int] = None
    discount_percentage: Optional[float] = None
    discount_flat_paisas: Optional[int] = None
    minimum_order_quantity: Optional[int] = None
    minimum_order_value_paisas: Optional[int] = None
    applicable_customer_tags: list[str] = Field(default_factory=list)
    priority: int = 0
    is_stackable: bool = False
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    usage_limit: Optional[int] = None
    usage_count: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscountRuleCreate(BaseModel):
    """Payload for creating a new discount rule.

    Attributes:
        distributor_id: Tenant FK.
        catalog_id: Optional catalog item FK.
        rule_name: Rule display name.
        rule_type: Type of discount.
        buy_quantity: For bonus rules.
        get_quantity: For bonus rules.
        discount_percentage: For percentage rules.
        discount_flat_paisas: For flat rules.
        minimum_order_quantity: Min qty trigger.
        minimum_order_value_paisas: Min value trigger.
        applicable_customer_tags: Tags for customer targeting.
        priority: Rule priority (higher first).
        is_stackable: Whether stackable.
        valid_from: Validity start.
        valid_until: Validity end.
        usage_limit: Max usage count.
    """

    distributor_id: UUID
    catalog_id: Optional[UUID] = None
    rule_name: Optional[str] = None
    rule_type: str
    buy_quantity: Optional[int] = None
    get_quantity: Optional[int] = None
    discount_percentage: Optional[float] = None
    discount_flat_paisas: Optional[int] = None
    minimum_order_quantity: Optional[int] = None
    minimum_order_value_paisas: Optional[int] = None
    applicable_customer_tags: list[str] = Field(default_factory=list)
    priority: int = 0
    is_stackable: bool = False
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    usage_limit: Optional[int] = None
