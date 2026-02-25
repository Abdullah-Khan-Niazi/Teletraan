"""Pydantic models for analytics aggregation tables.

* ``analytics_daily``           — DailyAnalytics, DailyAnalyticsCreate
* ``analytics_top_items``       — TopItem, TopItemCreate
* ``analytics_customer_events`` — CustomerEvent, CustomerEventCreate
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# DAILY ANALYTICS
# ═══════════════════════════════════════════════════════════════════


class DailyAnalytics(BaseModel):
    """Full analytics_daily row returned from DB.

    Pre-computed daily metrics per distributor.  Written nightly by
    the aggregation job.

    Attributes:
        id: Primary key UUID.
        distributor_id: Owning distributor.
        date: Calendar date.
        orders_confirmed: Confirmed order count.
        orders_pending: Pending order count.
        orders_cancelled: Cancelled order count.
        orders_total_paisas: Total revenue in paisas.
        avg_order_paisas: Average order value in paisas.
        unique_customers: Distinct customers who ordered.
        new_customers: First-time customers that day.
        returning_customers: Repeat customers that day.
        payments_received_paisas: Total payments received.
        outstanding_delta_paisas: Change in outstanding balance.
        messages_processed: WhatsApp messages processed.
        voice_notes_count: Voice notes received.
        ai_calls_count: AI provider calls made.
        ai_cost_paisas: AI provider cost in paisas.
        fallback_responses: Times the bot fell back to default.
        avg_response_ms: Average response latency.
        fuzzy_match_count: Fuzzy catalog matches.
        unlisted_requests: Requests for unlisted items.
        out_of_stock_events: Out-of-stock occurrences.
        computed_at: When this row was computed.
    """

    id: UUID
    distributor_id: UUID
    date: date
    orders_confirmed: int = 0
    orders_pending: int = 0
    orders_cancelled: int = 0
    orders_total_paisas: int = 0
    avg_order_paisas: int = 0
    unique_customers: int = 0
    new_customers: int = 0
    returning_customers: int = 0
    payments_received_paisas: int = 0
    outstanding_delta_paisas: int = 0
    messages_processed: int = 0
    voice_notes_count: int = 0
    ai_calls_count: int = 0
    ai_cost_paisas: int = 0
    fallback_responses: int = 0
    avg_response_ms: int = 0
    fuzzy_match_count: int = 0
    unlisted_requests: int = 0
    out_of_stock_events: int = 0
    computed_at: datetime

    model_config = {"from_attributes": True}


class DailyAnalyticsCreate(BaseModel):
    """Fields for upserting a daily analytics row.

    Uses a UNIQUE(distributor_id, date) constraint for upsert.
    """

    distributor_id: UUID
    date: date
    orders_confirmed: int = 0
    orders_pending: int = 0
    orders_cancelled: int = 0
    orders_total_paisas: int = 0
    avg_order_paisas: int = 0
    unique_customers: int = 0
    new_customers: int = 0
    returning_customers: int = 0
    payments_received_paisas: int = 0
    outstanding_delta_paisas: int = 0
    messages_processed: int = 0
    voice_notes_count: int = 0
    ai_calls_count: int = 0
    ai_cost_paisas: int = 0
    fallback_responses: int = 0
    avg_response_ms: int = 0
    fuzzy_match_count: int = 0
    unlisted_requests: int = 0
    out_of_stock_events: int = 0


# ═══════════════════════════════════════════════════════════════════
# TOP ITEMS
# ═══════════════════════════════════════════════════════════════════


class TopItem(BaseModel):
    """Full analytics_top_items row returned from DB.

    Per-day product ranking for a distributor.

    Attributes:
        id: Primary key UUID.
        distributor_id: Owning distributor.
        date: Calendar date.
        catalog_id: FK to catalog.
        medicine_name: Human-readable medicine name.
        units_sold: Units sold that day.
        revenue_paisas: Revenue in paisas.
        order_count: Number of orders containing this item.
    """

    id: UUID
    distributor_id: UUID
    date: date
    catalog_id: Optional[UUID] = None
    medicine_name: str
    units_sold: int = 0
    revenue_paisas: int = 0
    order_count: int = 0

    model_config = {"from_attributes": True}


class TopItemCreate(BaseModel):
    """Fields for creating a top_items analytics row."""

    distributor_id: UUID
    date: date
    catalog_id: Optional[UUID] = None
    medicine_name: str
    units_sold: int = 0
    revenue_paisas: int = 0
    order_count: int = 0


# ═══════════════════════════════════════════════════════════════════
# CUSTOMER EVENTS
# ═══════════════════════════════════════════════════════════════════


class CustomerEvent(BaseModel):
    """Full analytics_customer_events row returned from DB.

    Lifecycle events: first_order, reorder, escalation, churn_risk.

    Attributes:
        id: Primary key UUID.
        distributor_id: Owning distributor.
        customer_id: FK to customers.
        event_type: Machine-readable event type.
        event_data: Arbitrary event payload.
        occurred_at: When the event happened.
    """

    id: UUID
    distributor_id: UUID
    customer_id: UUID
    event_type: str
    event_data: dict = Field(default_factory=dict)
    occurred_at: datetime

    model_config = {"from_attributes": True}


class CustomerEventCreate(BaseModel):
    """Fields for creating a customer lifecycle event."""

    distributor_id: UUID
    customer_id: UUID
    event_type: str
    event_data: dict = Field(default_factory=dict)
