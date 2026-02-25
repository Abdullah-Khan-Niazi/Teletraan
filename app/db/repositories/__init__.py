"""TELETRAAN database repository package.

Re-exports all repository classes and pre-instantiated singletons for
use throughout the application.
"""

from __future__ import annotations

from app.db.repositories.analytics_repo import AnalyticsRepository
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.complaint_repo import ComplaintRepository
from app.db.repositories.delivery_zone_repo import DeliveryZoneRepository
from app.db.repositories.discount_rule_repo import DiscountRuleRepository
from app.db.repositories.customer_repo import CustomerRepository
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.notification_repo import NotificationRepository
from app.db.repositories.order_item_repo import OrderItemRepository
from app.db.repositories.order_repo import OrderRepository
from app.db.repositories.payment_repo import PaymentRepository
from app.db.repositories.prospect_repo import ProspectRepository
from app.db.repositories.rate_limit_repo import RateLimitRepository
from app.db.repositories.service_registry_repo import ServiceRegistryRepository
from app.db.repositories.scheduled_message_repo import ScheduledMessageRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.support_ticket_repo import SupportTicketRepository
from app.db.repositories.sync_log_repo import InventorySyncLogRepository

# ── Singleton instances ─────────────────────────────────────────────
# Services and handlers import these directly rather than instantiating
# their own copies.

# Group 1 — core entities
distributor_repo = DistributorRepository()
customer_repo = CustomerRepository()
order_repo = OrderRepository()
order_item_repo = OrderItemRepository()
catalog_repo = CatalogRepository()
delivery_zone_repo = DeliveryZoneRepository()
discount_rule_repo = DiscountRuleRepository()

# Group 2 — sessions, payments, complaints, support, prospects
session_repo = SessionRepository()
payment_repo = PaymentRepository()
complaint_repo = ComplaintRepository()
support_ticket_repo = SupportTicketRepository()
prospect_repo = ProspectRepository()
service_registry_repo = ServiceRegistryRepository()

# Group 3 — operational / logging / auxiliary
analytics_repo = AnalyticsRepository()
audit_repo = AuditRepository()
notification_repo = NotificationRepository()
scheduled_message_repo = ScheduledMessageRepository()
rate_limit_repo = RateLimitRepository()
sync_log_repo = InventorySyncLogRepository()

__all__ = [
    # Repository classes
    "AnalyticsRepository",
    "AuditRepository",
    "CatalogRepository",
    "ComplaintRepository",
    "DeliveryZoneRepository",
    "DiscountRuleRepository",
    "CustomerRepository",
    "DistributorRepository",
    "NotificationRepository",
    "OrderItemRepository",
    "OrderRepository",
    "PaymentRepository",
    "ProspectRepository",
    "RateLimitRepository",
    "ServiceRegistryRepository",
    "ScheduledMessageRepository",
    "SessionRepository",
    "SupportTicketRepository",
    "InventorySyncLogRepository",
    # Singleton instances
    "analytics_repo",
    "audit_repo",
    "catalog_repo",
    "complaint_repo",
    "delivery_zone_repo",
    "discount_rule_repo",
    "customer_repo",
    "distributor_repo",
    "notification_repo",
    "order_item_repo",
    "order_repo",
    "payment_repo",
    "prospect_repo",
    "rate_limit_repo",
    "service_registry_repo",
    "scheduled_message_repo",
    "session_repo",
    "support_ticket_repo",
    "sync_log_repo",
]
