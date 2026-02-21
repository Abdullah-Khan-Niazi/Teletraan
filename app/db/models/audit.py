"""Pydantic models for operational and system tables.

Groups all auxiliary / logging / configuration tables into one module:

* ``audit_log`` — AuditLog, AuditLogCreate (immutable)
* ``notifications_log`` — NotificationLog, NotificationLogCreate
* ``inventory_sync_log`` — InventorySyncLog, InventorySyncLogCreate, InventorySyncLogUpdate
* ``analytics_events`` — AnalyticsEvent, AnalyticsEventCreate
* ``rate_limits`` — RateLimit, RateLimitCreate, RateLimitUpdate
* ``scheduled_messages`` — ScheduledMessage, ScheduledMessageCreate, ScheduledMessageUpdate
* ``catalog_import_history`` — CatalogImportHistory, CatalogImportHistoryCreate
* ``bot_configuration`` — BotConfiguration, BotConfigurationCreate, BotConfigurationUpdate
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import (
    ActorType,
    ChannelType,
    DeliveryStatus,
    ExcelReportSchedule,
    RecipientType,
    ScheduledMessageStatus,
    SyncSource,
    SyncStatus,
)


# ═══════════════════════════════════════════════════════════════════
# AUDIT LOG (immutable — no update model)
# ═══════════════════════════════════════════════════════════════════


class AuditLog(BaseModel):
    """Full audit_log row returned from DB.

    Immutable append-only table.  Every state-changing action in the
    system writes one row here for compliance and debugging.

    Attributes:
        id: Primary key UUID.
        actor_type: Who performed the action.
        actor_id: UUID of the acting entity.
        actor_whatsapp_masked: Masked WhatsApp number (last 4 digits).
        distributor_id: FK to distributors — tenant boundary.
        action: Machine-readable action name.
        entity_type: Type of entity affected.
        entity_id: UUID of the affected entity.
        before_state: JSONB snapshot before the change.
        after_state: JSONB snapshot after the change.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
    """

    id: UUID
    actor_type: ActorType
    actor_id: Optional[UUID] = None
    actor_whatsapp_masked: Optional[str] = None
    distributor_id: Optional[UUID] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogCreate(BaseModel):
    """Fields for creating a new audit log entry.

    Attributes:
        actor_type: Who performed the action.
        actor_id: UUID of the acting entity.
        actor_whatsapp_masked: Masked WhatsApp number.
        distributor_id: FK to distributors.
        action: Machine-readable action name.
        entity_type: Type of entity affected.
        entity_id: UUID of the affected entity.
        before_state: Snapshot before the change.
        after_state: Snapshot after the change.
        metadata: Arbitrary metadata.
    """

    actor_type: ActorType
    actor_id: Optional[UUID] = None
    actor_whatsapp_masked: Optional[str] = None
    distributor_id: Optional[UUID] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None
    metadata: dict = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# NOTIFICATIONS LOG
# ═══════════════════════════════════════════════════════════════════


class NotificationLog(BaseModel):
    """Full notifications_log row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors.
        recipient_number_masked: Masked phone number (last 4 digits).
        recipient_type: Who the notification was sent to.
        notification_type: Machine-readable notification type.
        message_preview: Truncated message preview.
        whatsapp_message_id: Message ID from Meta Cloud API.
        delivery_status: WhatsApp delivery status.
        delivery_status_updated_at: When delivery status was last updated.
        reference_id: FK to the related entity.
        reference_type: Type of the related entity.
        error_message: Error description if delivery failed.
        sent_at: When the notification was dispatched.
    """

    id: UUID
    distributor_id: Optional[UUID] = None
    recipient_number_masked: Optional[str] = None
    recipient_type: Optional[RecipientType] = None
    notification_type: str
    message_preview: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    delivery_status: DeliveryStatus = DeliveryStatus.SENT
    delivery_status_updated_at: Optional[datetime] = None
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: datetime

    model_config = {"from_attributes": True}


class NotificationLogCreate(BaseModel):
    """Fields for creating a new notification log entry.

    Attributes:
        distributor_id: FK to distributors.
        recipient_number_masked: Masked phone number.
        recipient_type: Recipient type.
        notification_type: Notification type identifier.
        message_preview: Truncated message preview.
        whatsapp_message_id: Meta Cloud API message ID.
        delivery_status: Initial delivery status.
        reference_id: Related entity FK.
        reference_type: Related entity type.
        error_message: Error description.
    """

    distributor_id: Optional[UUID] = None
    recipient_number_masked: Optional[str] = None
    recipient_type: Optional[RecipientType] = None
    notification_type: str
    message_preview: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    delivery_status: DeliveryStatus = DeliveryStatus.SENT
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# INVENTORY SYNC LOG
# ═══════════════════════════════════════════════════════════════════


class InventorySyncLog(BaseModel):
    """Full inventory_sync_log row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        sync_source: How catalog data was imported.
        file_name: Name of the imported file.
        file_url: URL to the source file.
        status: Sync operation state.
        rows_processed: Total rows processed.
        rows_updated: Rows updated in catalog.
        rows_inserted: New rows inserted.
        rows_failed: Rows that failed validation.
        error_details: JSONB array of per-row errors.
        started_at: When the sync started.
        completed_at: When the sync finished.
    """

    id: UUID
    distributor_id: UUID
    sync_source: Optional[SyncSource] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    status: Optional[SyncStatus] = None
    rows_processed: int = 0
    rows_updated: int = 0
    rows_inserted: int = 0
    rows_failed: int = 0
    error_details: list = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class InventorySyncLogCreate(BaseModel):
    """Fields for creating a new inventory sync log entry.

    Attributes:
        distributor_id: FK to distributors.
        sync_source: Import source.
        file_name: Source file name.
        file_url: Source file URL.
        status: Initial sync state.
    """

    distributor_id: UUID
    sync_source: Optional[SyncSource] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    status: Optional[SyncStatus] = SyncStatus.STARTED


class InventorySyncLogUpdate(BaseModel):
    """Fields for updating an inventory sync log entry (all optional).

    Attributes:
        status: Updated sync state.
        rows_processed: Updated processed count.
        rows_updated: Updated update count.
        rows_inserted: Updated insert count.
        rows_failed: Updated failure count.
        error_details: Updated error details list.
        completed_at: Updated completion timestamp.
    """

    status: Optional[SyncStatus] = None
    rows_processed: Optional[int] = None
    rows_updated: Optional[int] = None
    rows_inserted: Optional[int] = None
    rows_failed: Optional[int] = None
    error_details: Optional[list] = None
    completed_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS EVENTS
# ═══════════════════════════════════════════════════════════════════


class AnalyticsEvent(BaseModel):
    """Full analytics_events row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors.
        event_type: Machine-readable event type.
        channel: Channel A or B.
        customer_id: FK to customers.
        session_id: FK to sessions.
        properties: Arbitrary event properties JSONB.
        duration_ms: Duration in milliseconds.
        ai_provider: AI provider used (if applicable).
        ai_tokens_used: Tokens consumed (if applicable).
        ai_cost_paisas: AI cost in paisas (if applicable).
        payment_gateway: Gateway used (if applicable).
        occurred_at: When the event occurred.
    """

    id: UUID
    distributor_id: Optional[UUID] = None
    event_type: str
    channel: Optional[ChannelType] = None
    customer_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    properties: dict = Field(default_factory=dict)
    duration_ms: Optional[int] = None
    ai_provider: Optional[str] = None
    ai_tokens_used: Optional[int] = None
    ai_cost_paisas: Optional[int] = None
    payment_gateway: Optional[str] = None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class AnalyticsEventCreate(BaseModel):
    """Fields for creating a new analytics event.

    Attributes:
        distributor_id: FK to distributors.
        event_type: Event type identifier.
        channel: Channel A or B.
        customer_id: FK to customers.
        session_id: FK to sessions.
        properties: Event properties.
        duration_ms: Duration in milliseconds.
        ai_provider: AI provider used.
        ai_tokens_used: Tokens consumed.
        ai_cost_paisas: AI cost in paisas.
        payment_gateway: Gateway used.
    """

    distributor_id: Optional[UUID] = None
    event_type: str
    channel: Optional[ChannelType] = None
    customer_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    properties: dict = Field(default_factory=dict)
    duration_ms: Optional[int] = None
    ai_provider: Optional[str] = None
    ai_tokens_used: Optional[int] = None
    ai_cost_paisas: Optional[int] = None
    payment_gateway: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# RATE LIMITS
# ═══════════════════════════════════════════════════════════════════


class RateLimit(BaseModel):
    """Full rate_limits row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors.
        whatsapp_number: E.164 number being rate-limited.
        window_start: Start of the sliding window.
        window_end: End of the sliding window.
        message_count: Messages in this window.
        voice_count: Voice messages in this window.
        ai_call_count: AI calls in this window.
        is_throttled: Whether the number is currently throttled.
    """

    id: UUID
    distributor_id: Optional[UUID] = None
    whatsapp_number: str
    window_start: datetime
    window_end: datetime
    message_count: int = 0
    voice_count: int = 0
    ai_call_count: int = 0
    is_throttled: bool = False

    model_config = {"from_attributes": True}


class RateLimitCreate(BaseModel):
    """Fields for creating a new rate limit record.

    Attributes:
        distributor_id: FK to distributors.
        whatsapp_number: E.164 number.
        window_start: Start of the sliding window.
        window_end: End of the sliding window.
        message_count: Initial message count.
        voice_count: Initial voice count.
        ai_call_count: Initial AI call count.
        is_throttled: Initial throttle flag.
    """

    distributor_id: Optional[UUID] = None
    whatsapp_number: str
    window_start: datetime
    window_end: datetime
    message_count: int = 0
    voice_count: int = 0
    ai_call_count: int = 0
    is_throttled: bool = False


class RateLimitUpdate(BaseModel):
    """Fields for updating a rate limit record (all optional).

    Attributes:
        message_count: Updated message count.
        voice_count: Updated voice count.
        ai_call_count: Updated AI call count.
        is_throttled: Updated throttle flag.
    """

    message_count: Optional[int] = None
    voice_count: Optional[int] = None
    ai_call_count: Optional[int] = None
    is_throttled: Optional[bool] = None


# ═══════════════════════════════════════════════════════════════════
# SCHEDULED MESSAGES
# ═══════════════════════════════════════════════════════════════════


class ScheduledMessage(BaseModel):
    """Full scheduled_messages row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors.
        recipient_number: E.164 recipient number.
        recipient_type: Who the message is for.
        message_type: Machine-readable message type.
        message_payload: Full message payload JSONB.
        scheduled_for: When the message should be sent.
        status: Message lifecycle state.
        retry_count: Delivery attempts so far.
        max_retries: Maximum delivery attempts.
        sent_at: When the message was actually sent.
        error_message: Error description if sending failed.
        reference_id: FK to related entity.
        reference_type: Related entity type.
        idempotency_key: Unique key to prevent duplicates.
        created_at: Row creation timestamp.
    """

    id: UUID
    distributor_id: Optional[UUID] = None
    recipient_number: str
    recipient_type: RecipientType
    message_type: str
    message_payload: dict
    scheduled_for: datetime
    status: ScheduledMessageStatus = ScheduledMessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduledMessageCreate(BaseModel):
    """Fields for creating a new scheduled message.

    Attributes:
        distributor_id: FK to distributors.
        recipient_number: E.164 recipient number.
        recipient_type: Recipient type.
        message_type: Message type identifier.
        message_payload: Full message payload.
        scheduled_for: When to send.
        status: Initial message state.
        max_retries: Maximum delivery attempts.
        reference_id: Related entity FK.
        reference_type: Related entity type.
        idempotency_key: Deduplication key.
    """

    distributor_id: Optional[UUID] = None
    recipient_number: str
    recipient_type: RecipientType
    message_type: str
    message_payload: dict
    scheduled_for: datetime
    status: ScheduledMessageStatus = ScheduledMessageStatus.PENDING
    max_retries: int = 3
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
    idempotency_key: Optional[str] = None


class ScheduledMessageUpdate(BaseModel):
    """Fields for updating a scheduled message (all optional).

    Attributes:
        scheduled_for: Updated send time.
        status: Updated message state.
        retry_count: Updated attempt count.
        sent_at: Updated sent timestamp.
        error_message: Updated error description.
    """

    scheduled_for: Optional[datetime] = None
    status: Optional[ScheduledMessageStatus] = None
    retry_count: Optional[int] = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# CATALOG IMPORT HISTORY
# ═══════════════════════════════════════════════════════════════════


class CatalogImportHistory(BaseModel):
    """Full catalog_import_history row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        file_name: Name of the imported file.
        storage_path: Storage path / URL.
        items_total: Total items in the file.
        items_imported: Items successfully imported.
        items_failed: Items that failed import.
        status: Import job status.
        error_log: JSONB array of per-item errors.
        imported_by: Who triggered the import.
        created_at: Row creation timestamp.
    """

    id: UUID
    distributor_id: UUID
    file_name: Optional[str] = None
    storage_path: Optional[str] = None
    items_total: int = 0
    items_imported: int = 0
    items_failed: int = 0
    status: Optional[str] = None
    error_log: list = Field(default_factory=list)
    imported_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CatalogImportHistoryCreate(BaseModel):
    """Fields for creating a new catalog import history entry.

    Attributes:
        distributor_id: FK to distributors.
        file_name: Imported file name.
        storage_path: Storage path / URL.
        items_total: Total item count.
        items_imported: Successfully imported count.
        items_failed: Failed item count.
        status: Import status.
        error_log: Per-item error list.
        imported_by: Who triggered the import.
    """

    distributor_id: UUID
    file_name: Optional[str] = None
    storage_path: Optional[str] = None
    items_total: int = 0
    items_imported: int = 0
    items_failed: int = 0
    status: Optional[str] = None
    error_log: list = Field(default_factory=list)
    imported_by: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# BOT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════


class BotConfiguration(BaseModel):
    """Full bot_configuration row returned from DB.

    One row per distributor — per-tenant bot settings.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors (unique per distributor).
        welcome_message_override: Custom welcome message.
        business_hours_start: Start of business hours.
        business_hours_end: End of business hours.
        timezone: IANA timezone string.
        out_of_hours_message: Message sent outside business hours.
        allow_orders_outside_hours: Accept orders outside hours flag.
        voice_enabled: Voice message support flag.
        catalog_pdf_enabled: Catalog PDF generation flag.
        discount_requests_enabled: Customer discount requests flag.
        credit_orders_enabled: Credit-based orders flag.
        minimum_order_value_paisas: Minimum order value in paisas.
        max_items_per_order: Maximum items per order.
        session_timeout_minutes: Session TTL in minutes.
        ai_temperature: AI model temperature setting.
        custom_system_prompt_suffix: Appended to system prompt.
        excel_report_email: Email for Excel report delivery.
        excel_report_schedule: When to send Excel reports.
        preferred_payment_gateways: List of enabled gateways.
        metadata: Arbitrary JSONB metadata.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    distributor_id: UUID
    welcome_message_override: Optional[str] = None
    business_hours_start: time = time(8, 0)
    business_hours_end: time = time(20, 0)
    timezone: str = "Asia/Karachi"
    out_of_hours_message: Optional[str] = None
    allow_orders_outside_hours: bool = True
    voice_enabled: bool = True
    catalog_pdf_enabled: bool = True
    discount_requests_enabled: bool = True
    credit_orders_enabled: bool = False
    minimum_order_value_paisas: int = 0
    max_items_per_order: int = 50
    session_timeout_minutes: int = 60
    ai_temperature: float = 0.30
    custom_system_prompt_suffix: Optional[str] = None
    excel_report_email: Optional[str] = None
    excel_report_schedule: ExcelReportSchedule = ExcelReportSchedule.DAILY_EVENING
    preferred_payment_gateways: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BotConfigurationCreate(BaseModel):
    """Fields for creating a new bot configuration.

    Attributes:
        distributor_id: FK to distributors.
        welcome_message_override: Custom welcome message.
        business_hours_start: Start of business hours.
        business_hours_end: End of business hours.
        timezone: IANA timezone.
        out_of_hours_message: Out-of-hours message.
        allow_orders_outside_hours: Accept orders outside hours.
        voice_enabled: Voice support flag.
        catalog_pdf_enabled: Catalog PDF flag.
        discount_requests_enabled: Discount requests flag.
        credit_orders_enabled: Credit orders flag.
        minimum_order_value_paisas: Minimum order value in paisas.
        max_items_per_order: Max items per order.
        session_timeout_minutes: Session TTL.
        ai_temperature: AI temperature.
        custom_system_prompt_suffix: System prompt suffix.
        excel_report_email: Report email.
        excel_report_schedule: Report schedule.
        preferred_payment_gateways: Enabled gateways list.
        metadata: Arbitrary metadata.
    """

    distributor_id: UUID
    welcome_message_override: Optional[str] = None
    business_hours_start: time = time(8, 0)
    business_hours_end: time = time(20, 0)
    timezone: str = "Asia/Karachi"
    out_of_hours_message: Optional[str] = None
    allow_orders_outside_hours: bool = True
    voice_enabled: bool = True
    catalog_pdf_enabled: bool = True
    discount_requests_enabled: bool = True
    credit_orders_enabled: bool = False
    minimum_order_value_paisas: int = 0
    max_items_per_order: int = 50
    session_timeout_minutes: int = 60
    ai_temperature: float = 0.30
    custom_system_prompt_suffix: Optional[str] = None
    excel_report_email: Optional[str] = None
    excel_report_schedule: ExcelReportSchedule = ExcelReportSchedule.DAILY_EVENING
    preferred_payment_gateways: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class BotConfigurationUpdate(BaseModel):
    """Fields for updating a bot configuration (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        welcome_message_override: Updated welcome message.
        business_hours_start: Updated business hours start.
        business_hours_end: Updated business hours end.
        timezone: Updated timezone.
        out_of_hours_message: Updated OOH message.
        allow_orders_outside_hours: Updated OOH orders flag.
        voice_enabled: Updated voice flag.
        catalog_pdf_enabled: Updated PDF flag.
        discount_requests_enabled: Updated discount flag.
        credit_orders_enabled: Updated credit flag.
        minimum_order_value_paisas: Updated min order in paisas.
        max_items_per_order: Updated max items.
        session_timeout_minutes: Updated session TTL.
        ai_temperature: Updated AI temperature.
        custom_system_prompt_suffix: Updated prompt suffix.
        excel_report_email: Updated report email.
        excel_report_schedule: Updated report schedule.
        preferred_payment_gateways: Updated gateways list.
        metadata: Updated metadata dict.
    """

    welcome_message_override: Optional[str] = None
    business_hours_start: Optional[time] = None
    business_hours_end: Optional[time] = None
    timezone: Optional[str] = None
    out_of_hours_message: Optional[str] = None
    allow_orders_outside_hours: Optional[bool] = None
    voice_enabled: Optional[bool] = None
    catalog_pdf_enabled: Optional[bool] = None
    discount_requests_enabled: Optional[bool] = None
    credit_orders_enabled: Optional[bool] = None
    minimum_order_value_paisas: Optional[int] = None
    max_items_per_order: Optional[int] = None
    session_timeout_minutes: Optional[int] = None
    ai_temperature: Optional[float] = None
    custom_system_prompt_suffix: Optional[str] = None
    excel_report_email: Optional[str] = None
    excel_report_schedule: Optional[ExcelReportSchedule] = None
    preferred_payment_gateways: Optional[list[str]] = None
    metadata: Optional[dict] = None
