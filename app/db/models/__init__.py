"""TELETRAAN database models package.

Re-exports every Pydantic model so callers can do::

    from app.db.models import Distributor, DistributorCreate
"""

from __future__ import annotations

from app.db.models.audit import (
    AnalyticsEvent,
    AnalyticsEventCreate,
    AuditLog,
    AuditLogCreate,
    BotConfiguration,
    BotConfigurationCreate,
    BotConfigurationUpdate,
    CatalogImportHistory,
    CatalogImportHistoryCreate,
    InventorySyncLog,
    InventorySyncLogCreate,
    InventorySyncLogUpdate,
    NotificationLog,
    NotificationLogCreate,
    RateLimit,
    RateLimitCreate,
    RateLimitUpdate,
    ScheduledMessage,
    ScheduledMessageCreate,
    ScheduledMessageUpdate,
)
from app.db.models.catalog import CatalogItem, CatalogItemCreate, CatalogItemUpdate
from app.db.models.complaint import Complaint, ComplaintCreate, ComplaintUpdate
from app.db.models.delivery_zone import DeliveryZone, DeliveryZoneCreate
from app.db.models.discount_rule import DiscountRule, DiscountRuleCreate
from app.db.models.customer import Customer, CustomerCreate, CustomerUpdate
from app.db.models.distributor import Distributor, DistributorCreate, DistributorUpdate
from app.db.models.order import (
    Order,
    OrderCreate,
    OrderItem,
    OrderItemCreate,
    OrderStatusHistory,
    OrderStatusHistoryCreate,
    OrderUpdate,
)
from app.db.models.payment import Payment, PaymentCreate, PaymentUpdate
from app.db.models.prospect import Prospect, ProspectCreate, ProspectUpdate
from app.db.models.service_registry import (
    ServiceRegistryCreate,
    ServiceRegistryEntry,
    ServiceRegistryUpdate,
)
from app.db.models.session import Session, SessionCreate, SessionUpdate
from app.db.models.support_ticket import (
    SupportTicket,
    SupportTicketCreate,
    SupportTicketUpdate,
)

__all__ = [
    # Distributor
    "Distributor",
    "DistributorCreate",
    "DistributorUpdate",
    # Customer
    "Customer",
    "CustomerCreate",
    "CustomerUpdate",
    # Catalog
    "CatalogItem",
    "CatalogItemCreate",
    "CatalogItemUpdate",
    # Delivery Zone
    "DeliveryZone",
    "DeliveryZoneCreate",
    # Discount Rule
    "DiscountRule",
    "DiscountRuleCreate",
    # Session
    "Session",
    "SessionCreate",
    "SessionUpdate",
    # Order
    "Order",
    "OrderCreate",
    "OrderUpdate",
    "OrderItem",
    "OrderItemCreate",
    "OrderStatusHistory",
    "OrderStatusHistoryCreate",
    # Payment
    "Payment",
    "PaymentCreate",
    "PaymentUpdate",
    # Complaint
    "Complaint",
    "ComplaintCreate",
    "ComplaintUpdate",
    # Support Ticket
    "SupportTicket",
    "SupportTicketCreate",
    "SupportTicketUpdate",
    # Prospect
    "Prospect",
    "ProspectCreate",
    "ProspectUpdate",
    # Service Registry
    "ServiceRegistryEntry",
    "ServiceRegistryCreate",
    "ServiceRegistryUpdate",
    # Audit / Operational
    "AuditLog",
    "AuditLogCreate",
    "NotificationLog",
    "NotificationLogCreate",
    "InventorySyncLog",
    "InventorySyncLogCreate",
    "InventorySyncLogUpdate",
    "AnalyticsEvent",
    "AnalyticsEventCreate",
    "RateLimit",
    "RateLimitCreate",
    "RateLimitUpdate",
    "ScheduledMessage",
    "ScheduledMessageCreate",
    "ScheduledMessageUpdate",
    "CatalogImportHistory",
    "CatalogImportHistoryCreate",
    "BotConfiguration",
    "BotConfigurationCreate",
    "BotConfigurationUpdate",
]
