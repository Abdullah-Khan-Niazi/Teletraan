"""Tests for all remaining DB repositories with mocked Supabase client.

Covers: DistributorRepository, PaymentRepository, ComplaintRepository,
ProspectRepository, SupportTicketRepository, ScheduledMessageRepository,
RateLimitRepository, ServiceRegistryRepository, TopItemRepository,
CustomerEventRepository, DailyAnalyticsRepository, AnalyticsRepository,
AuditRepository, DeliveryZoneRepository, DiscountRuleRepository,
NotificationRepository, InventorySyncLogRepository.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ═══════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════

NOW = "2025-01-15T12:00:00+00:00"
LATER = "2025-01-16T12:00:00+00:00"
DIST_ID = str(uuid4())
CUST_ID = str(uuid4())
ORDER_ID = str(uuid4())


def _mock_supabase(data: list | dict | None = None) -> MagicMock:
    """Create a chainable Supabase mock that mirrors the real client."""
    mock = MagicMock()
    chain_methods = [
        "table", "select", "insert", "update", "delete", "upsert",
        "eq", "neq", "gt", "gte", "lt", "lte", "in_",
        "like", "ilike", "is_", "not_", "or_",
        "order", "limit", "offset", "range",
        "single", "maybe_single", "on_conflict",
    ]
    for method in chain_methods:
        getattr(mock, method).return_value = mock
    # not_ is accessed as an attribute (not called), so set it directly
    mock.not_ = mock
    if data is None:
        data = []
    mock.execute = AsyncMock(return_value=MagicMock(data=data))
    return mock


# ─────────────────── Factory functions ───────────────────


def _distributor_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "business_name": "Al-Shifa Distributors",
        "owner_name": "Ahmed Khan",
        "whatsapp_number": "+923001234567",
        "whatsapp_phone_number_id": "123456789",
        "city": "Lahore",
        "address": "Main Market, Lahore",
        "cnic_encrypted": None,
        "email": "ahmed@example.com",
        "subscription_status": "trial",
        "is_active": True,
        "is_deleted": False,
        "deleted_at": None,
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _payment_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "transaction_reference": f"TXN-{uuid4().hex[:8].upper()}",
        "payment_type": "order_payment",
        "distributor_id": DIST_ID,
        "order_id": ORDER_ID,
        "customer_id": CUST_ID,
        "gateway": "jazzcash",
        "gateway_transaction_id": "GW-001",
        "amount_paisas": 500000,
        "currency": "PKR",
        "status": "pending",
        "payment_link": "https://pay.example.com/abc",
        "payment_link_expires_at": LATER,
        "gateway_response": {},
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _complaint_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "ticket_number": "CMP-0001",
        "distributor_id": DIST_ID,
        "customer_id": CUST_ID,
        "category": "wrong_item",
        "description": "Received wrong medicine",
        "status": "open",
        "priority": "normal",
        "media_urls": [],
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _prospect_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "whatsapp_number": "+923009876543",
        "name": "Bilal",
        "business_name": "Bilal Pharmacy",
        "status": "new",
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _support_ticket_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "ticket_number": "SUP-0001",
        "distributor_id": DIST_ID,
        "description": "Bot not responding",
        "status": "open",
        "priority": "normal",
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _scheduled_message_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "recipient_number": "+923001234567",
        "recipient_type": "customer",
        "message_type": "reminder",
        "message_payload": {"text": "Your order is ready"},
        "scheduled_for": LATER,
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "created_at": NOW,
    }
    row.update(ov)
    return row


def _rate_limit_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "whatsapp_number": "+923001234567",
        "window_start": NOW,
        "window_end": LATER,
        "message_count": 5,
        "voice_count": 1,
        "ai_call_count": 2,
        "is_throttled": False,
    }
    row.update(ov)
    return row


def _service_registry_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "name": "TELETRAAN Order Bot",
        "slug": "teletraan-order-bot",
        "description": "WhatsApp order automation",
        "is_available": True,
        "is_coming_soon": False,
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _top_item_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "date": "2025-01-15",
        "medicine_name": "Panadol 500mg",
        "units_sold": 100,
        "revenue_paisas": 500000,
        "order_count": 10,
    }
    row.update(ov)
    return row


def _customer_event_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "customer_id": CUST_ID,
        "event_type": "order_placed",
        "event_data": {},
        "occurred_at": NOW,
    }
    row.update(ov)
    return row


def _daily_analytics_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "date": "2025-01-15",
        "total_orders": 10,
        "total_revenue_paisas": 5000000,
        "total_items_sold": 50,
        "new_customers": 3,
        "active_customers": 15,
        "messages_received": 200,
        "messages_sent": 180,
        "ai_calls_count": 50,
        "ai_tokens_used": 10000,
        "ai_cost_paisas": 500,
        "voice_messages_processed": 5,
        "complaints_received": 1,
        "complaints_resolved": 0,
        "avg_order_value_paisas": 500000,
        "avg_response_time_ms": 1500,
        "payment_success_count": 8,
        "payment_failure_count": 2,
        "computed_at": NOW,
    }
    row.update(ov)
    return row


def _analytics_event_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "event_type": "message_received",
        "properties": {},
        "occurred_at": NOW,
    }
    row.update(ov)
    return row


def _audit_log_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "actor_type": "system",
        "action": "order.created",
        "distributor_id": DIST_ID,
        "entity_type": "order",
        "entity_id": str(uuid4()),
        "metadata": {},
        "created_at": NOW,
    }
    row.update(ov)
    return row


def _delivery_zone_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "name": "Lahore Central",
        "areas": ["Gulberg", "Model Town", "DHA"],
        "delivery_days": ["monday", "wednesday", "friday"],
        "estimated_delivery_hours": 24,
        "delivery_charges_paisas": 20000,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _discount_rule_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "rule_name": "Buy 10 get 1 free",
        "rule_type": "buy_x_get_y",
        "buy_quantity": 10,
        "get_quantity": 1,
        "discount_percentage": None,
        "applicable_customer_tags": [],
        "priority": 1,
        "is_stackable": False,
        "valid_from": None,
        "valid_until": None,
        "usage_limit": None,
        "usage_count": 0,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(ov)
    return row


def _notification_log_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "notification_type": "order_confirmation",
        "recipient_number_masked": "****4567",
        "recipient_type": "customer",
        "delivery_status": "sent",
        "sent_at": NOW,
    }
    row.update(ov)
    return row


def _sync_log_row(**ov: object) -> dict:
    row = {
        "id": str(uuid4()),
        "distributor_id": DIST_ID,
        "sync_source": "google_drive",
        "status": "completed",
        "rows_processed": 100,
        "rows_updated": 50,
        "rows_inserted": 45,
        "rows_failed": 5,
        "error_details": [],
        "started_at": NOW,
        "completed_at": LATER,
    }
    row.update(ov)
    return row


# ═══════════════════════════════════════════════════════════════
# DISTRIBUTOR REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestDistributorRepo:
    """Test DistributorRepository with mocked Supabase."""

    PATCH = "app.db.repositories.distributor_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        row = _distributor_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None
            assert result.business_name == "Al-Shifa Distributors"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.get_by_id(str(uuid4()))
            assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_or_raise(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            with pytest.raises(NotFoundError):
                await repo.get_by_id_or_raise(str(uuid4()))

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.models.distributor import DistributorCreate
        from app.db.repositories.distributor_repo import DistributorRepository

        row = _distributor_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            data = DistributorCreate(
                business_name="Al-Shifa Distributors",
                owner_name="Ahmed Khan",
                whatsapp_number="+923001234567",
                whatsapp_phone_number_id="123456789",
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.models.distributor import DistributorUpdate
        from app.db.repositories.distributor_repo import DistributorRepository

        row = _distributor_row(business_name="Updated Name")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            data = DistributorUpdate(business_name="Updated Name")
            result = await repo.update(row["id"], data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_whatsapp_number(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        row = _distributor_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.get_by_whatsapp_number("+923001234567")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_phone_number_id(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        row = _distributor_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.get_by_phone_number_id("123456789")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_active_distributors(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        rows = [_distributor_row(), _distributor_row(business_name="Pharmacy 2")]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.get_active_distributors()
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_expiring_subscriptions(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        rows = [_distributor_row(subscription_status="active")]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.get_expiring_subscriptions(days_ahead=7)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_soft_delete(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository

        row = _distributor_row(is_deleted=True)
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            result = await repo.soft_delete(row["id"])
            assert result is True

    @pytest.mark.asyncio
    async def test_soft_delete_not_found(self) -> None:
        from app.db.repositories.distributor_repo import DistributorRepository
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase([])
        with patch(self.PATCH, return_value=mock_db):
            repo = DistributorRepository()
            with pytest.raises(NotFoundError):
                await repo.soft_delete(str(uuid4()))


# ═══════════════════════════════════════════════════════════════
# PAYMENT REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestPaymentRepo:
    """Test PaymentRepository with mocked Supabase."""

    PATCH = "app.db.repositories.payment_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository

        row = _payment_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_raise_not_found(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            with pytest.raises(NotFoundError):
                await repo.get_by_id_or_raise(str(uuid4()))

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.models.payment import PaymentCreate
        from app.db.repositories.payment_repo import PaymentRepository

        row = _payment_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            data = PaymentCreate(
                transaction_reference=row["transaction_reference"],
                payment_type="order_payment",
                gateway="jazzcash",
                amount_paisas=500000,
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.models.payment import PaymentUpdate
        from app.db.repositories.payment_repo import PaymentRepository

        row = _payment_row(status="completed")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            data = PaymentUpdate(status="completed")
            result = await repo.update(row["id"], data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_transaction_reference(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository

        row = _payment_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            result = await repo.get_by_transaction_reference(
                row["transaction_reference"]
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_gateway_transaction_id(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository

        row = _payment_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            result = await repo.get_by_gateway_transaction_id("GW-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_order_payments(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository

        rows = [_payment_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            result = await repo.get_order_payments(ORDER_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_distributor_payments(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository

        rows = [_payment_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            result = await repo.get_distributor_payments(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_pending_expired(self) -> None:
        from app.db.repositories.payment_repo import PaymentRepository

        rows = [_payment_row(status="pending")]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = PaymentRepository()
            result = await repo.get_pending_expired()
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# COMPLAINT REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestComplaintRepo:
    """Test ComplaintRepository with mocked Supabase."""

    PATCH = "app.db.repositories.complaint_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.complaint_repo import ComplaintRepository

        row = _complaint_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_raise_not_found(self) -> None:
        from app.db.repositories.complaint_repo import ComplaintRepository
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            with pytest.raises(NotFoundError):
                await repo.get_by_id_or_raise(str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_by_ticket_number(self) -> None:
        from app.db.repositories.complaint_repo import ComplaintRepository

        row = _complaint_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            result = await repo.get_by_ticket_number("CMP-0001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.models.complaint import ComplaintCreate
        from app.db.repositories.complaint_repo import ComplaintRepository

        row = _complaint_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            data = ComplaintCreate(
                ticket_number="CMP-0002",
                distributor_id=DIST_ID,
                customer_id=CUST_ID,
                category="wrong_item",
                description="Got Aspirin instead of Panadol",
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.models.complaint import ComplaintUpdate
        from app.db.repositories.complaint_repo import ComplaintRepository

        row = _complaint_row(status="resolved")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            data = ComplaintUpdate(status="resolved")
            result = await repo.update(row["id"], data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_open_complaints(self) -> None:
        from app.db.repositories.complaint_repo import ComplaintRepository

        rows = [_complaint_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            result = await repo.get_open_complaints(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_customer_complaints(self) -> None:
        from app.db.repositories.complaint_repo import ComplaintRepository

        rows = [_complaint_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ComplaintRepository()
            result = await repo.get_customer_complaints(DIST_ID, CUST_ID)
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# PROSPECT REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestProspectRepo:
    """Test ProspectRepository with mocked Supabase."""

    PATCH = "app.db.repositories.prospect_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.prospect_repo import ProspectRepository

        row = _prospect_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_raise_not_found(self) -> None:
        from app.db.repositories.prospect_repo import ProspectRepository
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            with pytest.raises(NotFoundError):
                await repo.get_by_id_or_raise(str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_by_whatsapp_number(self) -> None:
        from app.db.repositories.prospect_repo import ProspectRepository

        row = _prospect_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            result = await repo.get_by_whatsapp_number("+923009876543")
            assert result is not None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.models.prospect import ProspectCreate
        from app.db.repositories.prospect_repo import ProspectRepository

        row = _prospect_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            data = ProspectCreate(whatsapp_number="+923009876543")
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.models.prospect import ProspectUpdate
        from app.db.repositories.prospect_repo import ProspectRepository

        row = _prospect_row(status="qualified")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            data = ProspectUpdate(status="qualified")
            result = await repo.update(row["id"], data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_status(self) -> None:
        from app.db.repositories.prospect_repo import ProspectRepository

        rows = [_prospect_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            result = await repo.get_by_status("new")
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_follow_ups_due(self) -> None:
        from app.db.repositories.prospect_repo import ProspectRepository

        rows = [_prospect_row(follow_up_at=NOW)]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ProspectRepository()
            result = await repo.get_follow_ups_due()
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# SUPPORT TICKET REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestSupportTicketRepo:
    """Test SupportTicketRepository with mocked Supabase."""

    PATCH = "app.db.repositories.support_ticket_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )

        row = _support_ticket_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_raise_not_found(self) -> None:
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            with pytest.raises(NotFoundError):
                await repo.get_by_id_or_raise(str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_by_ticket_number(self) -> None:
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )

        row = _support_ticket_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            result = await repo.get_by_ticket_number("SUP-0001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.models.support_ticket import SupportTicketCreate
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )

        row = _support_ticket_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            data = SupportTicketCreate(
                ticket_number="SUP-0002",
                distributor_id=DIST_ID,
                description="Need help",
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.models.support_ticket import SupportTicketUpdate
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )

        row = _support_ticket_row(status="resolved")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            data = SupportTicketUpdate(status="resolved")
            result = await repo.update(row["id"], data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_open_tickets(self) -> None:
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )

        rows = [_support_ticket_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            result = await repo.get_open_tickets(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_all_open_tickets(self) -> None:
        from app.db.repositories.support_ticket_repo import (
            SupportTicketRepository,
        )

        rows = [_support_ticket_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = SupportTicketRepository()
            result = await repo.get_all_open_tickets()
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# SCHEDULED MESSAGE REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestScheduledMessageRepo:
    """Test ScheduledMessageRepository with mocked Supabase."""

    PATCH = "app.db.repositories.scheduled_message_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.scheduled_message_repo import (
            ScheduledMessageRepository,
        )

        row = _scheduled_message_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ScheduledMessageRepository()
            from app.db.models.audit import ScheduledMessageCreate

            data = ScheduledMessageCreate(
                recipient_number="+923001234567",
                recipient_type="customer",
                message_type="reminder",
                message_payload={"text": "Hello"},
                scheduled_for=datetime.now(tz=timezone.utc),
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_due_messages(self) -> None:
        from app.db.repositories.scheduled_message_repo import (
            ScheduledMessageRepository,
        )

        rows = [_scheduled_message_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ScheduledMessageRepository()
            result = await repo.get_due_messages()
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_mark_sent(self) -> None:
        from app.db.repositories.scheduled_message_repo import (
            ScheduledMessageRepository,
        )

        row = _scheduled_message_row(status="sent")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ScheduledMessageRepository()
            result = await repo.mark_sent(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_mark_failed(self) -> None:
        from app.db.repositories.scheduled_message_repo import (
            ScheduledMessageRepository,
        )

        row = _scheduled_message_row(status="failed")
        # mark_failed calls _get_or_raise first (maybe_single → dict)
        # then calls update (→ list)
        # We need two different return values:
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ScheduledMessageRepository()
            # Override to handle two sequential calls:
            mock_db.execute = AsyncMock(
                side_effect=[
                    MagicMock(data=row),  # _get_or_raise → maybe_single
                    MagicMock(data=[row]),  # update → data[0]
                ]
            )
            result = await repo.mark_failed(row["id"], "Network error")
            assert result is not None

    @pytest.mark.asyncio
    async def test_cancel(self) -> None:
        from app.db.repositories.scheduled_message_repo import (
            ScheduledMessageRepository,
        )

        row = _scheduled_message_row(status="cancelled")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ScheduledMessageRepository()
            result = await repo.cancel(row["id"])
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# RATE LIMIT REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestRateLimitRepo:
    """Test RateLimitRepository with mocked Supabase."""

    PATCH = "app.db.repositories.rate_limit_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_current_window(self) -> None:
        from app.db.repositories.rate_limit_repo import RateLimitRepository

        row = _rate_limit_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = RateLimitRepository()
            result = await repo.get_current_window(DIST_ID, "+923001234567")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_current_window_none(self) -> None:
        from app.db.repositories.rate_limit_repo import RateLimitRepository

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = RateLimitRepository()
            result = await repo.get_current_window(DIST_ID, "+923001234567")
            assert result is None

    @pytest.mark.asyncio
    async def test_create_or_increment_creates_new(self) -> None:
        from app.db.repositories.rate_limit_repo import RateLimitRepository

        row = _rate_limit_row()
        # First call: get_current_window returns None
        # Second call: insert returns new row
        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = RateLimitRepository()
            mock_db.execute = AsyncMock(
                side_effect=[
                    MagicMock(data=None),  # get_current_window → None
                    MagicMock(data=[row]),  # insert → data[0]
                ]
            )
            result = await repo.create_or_increment(DIST_ID, "+923001234567")
            assert result is not None

    @pytest.mark.asyncio
    async def test_create_or_increment_increments(self) -> None:
        from app.db.repositories.rate_limit_repo import RateLimitRepository

        row = _rate_limit_row(message_count=6)
        # First call: get_current_window returns existing
        # Second call: update returns updated row
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = RateLimitRepository()
            mock_db.execute = AsyncMock(
                side_effect=[
                    MagicMock(data=row),  # get_current_window → dict
                    MagicMock(data=[row]),  # update → data[0]
                ]
            )
            result = await repo.create_or_increment(DIST_ID, "+923001234567")
            assert result is not None

    @pytest.mark.asyncio
    async def test_set_throttled(self) -> None:
        from app.db.repositories.rate_limit_repo import RateLimitRepository

        row = _rate_limit_row(is_throttled=True)
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = RateLimitRepository()
            result = await repo.set_throttled(row["id"])
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# SERVICE REGISTRY REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestServiceRegistryRepo:
    """Test ServiceRegistryRepository with mocked Supabase."""

    PATCH = "app.db.repositories.service_registry_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )

        row = _service_registry_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_raise_not_found(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )
        from app.core.exceptions import NotFoundError

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            with pytest.raises(NotFoundError):
                await repo.get_by_id_or_raise(str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_by_slug(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )

        row = _service_registry_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            result = await repo.get_by_slug("teletraan-order-bot")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_available_services(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )

        rows = [_service_registry_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            result = await repo.get_available_services()
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_all(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )

        rows = [_service_registry_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            result = await repo.get_all()
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )
        from app.db.models.service_registry import ServiceRegistryCreate

        row = _service_registry_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            data = ServiceRegistryCreate(
                name="New Service",
                slug="new-service",
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.repositories.service_registry_repo import (
            ServiceRegistryRepository,
        )
        from app.db.models.service_registry import ServiceRegistryUpdate

        row = _service_registry_row(name="Updated Service")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = ServiceRegistryRepository()
            data = ServiceRegistryUpdate(name="Updated Service")
            result = await repo.update(row["id"], data)
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# TOP ITEM + CUSTOMER EVENT REPOSITORIES
# ═══════════════════════════════════════════════════════════════


class TestTopItemRepo:
    """Test TopItemRepository with mocked Supabase."""

    PATCH = "app.db.repositories.top_items_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_replace_for_date(self) -> None:
        from app.db.repositories.top_items_repo import TopItemRepository
        from app.db.models.analytics import TopItemCreate

        rows = [_top_item_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            # delete → execute (first call), then insert → execute (second call)
            mock_db.execute = AsyncMock(
                side_effect=[
                    MagicMock(data=[]),  # delete
                    MagicMock(data=rows),  # insert batch
                ]
            )
            repo = TopItemRepository()
            items = [
                TopItemCreate(
                    distributor_id=DIST_ID,
                    date=date(2025, 1, 15),
                    medicine_name="Panadol 500mg",
                )
            ]
            result = await repo.replace_for_date(
                DIST_ID, date(2025, 1, 15), items
            )
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_for_date(self) -> None:
        from app.db.repositories.top_items_repo import TopItemRepository

        rows = [_top_item_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = TopItemRepository()
            result = await repo.get_for_date(DIST_ID, date(2025, 1, 15))
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_range(self) -> None:
        from app.db.repositories.top_items_repo import TopItemRepository

        rows = [_top_item_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = TopItemRepository()
            result = await repo.get_range(
                DIST_ID, date(2025, 1, 1), date(2025, 1, 31)
            )
            assert len(result) >= 1


class TestCustomerEventRepo:
    """Test CustomerEventRepository with mocked Supabase."""

    PATCH = "app.db.repositories.top_items_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.top_items_repo import CustomerEventRepository
        from app.db.models.analytics import CustomerEventCreate

        row = _customer_event_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerEventRepository()
            data = CustomerEventCreate(
                distributor_id=DIST_ID,
                customer_id=CUST_ID,
                event_type="order_placed",
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_customer(self) -> None:
        from app.db.repositories.top_items_repo import CustomerEventRepository

        rows = [_customer_event_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerEventRepository()
            result = await repo.get_by_customer(DIST_ID, CUST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_by_type(self) -> None:
        from app.db.repositories.top_items_repo import CustomerEventRepository

        rows = [_customer_event_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = CustomerEventRepository()
            result = await repo.get_by_type(DIST_ID, "order_placed")
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# DAILY ANALYTICS REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestDailyAnalyticsRepo:
    """Test DailyAnalyticsRepository with mocked Supabase."""

    PATCH = "app.db.repositories.daily_analytics_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_upsert(self) -> None:
        from app.db.repositories.daily_analytics_repo import (
            DailyAnalyticsRepository,
        )
        from app.db.models.analytics import DailyAnalyticsCreate

        row = _daily_analytics_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DailyAnalyticsRepository()
            data = DailyAnalyticsCreate(
                distributor_id=DIST_ID,
                date=date(2025, 1, 15),
            )
            result = await repo.upsert(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_for_date(self) -> None:
        from app.db.repositories.daily_analytics_repo import (
            DailyAnalyticsRepository,
        )

        row = _daily_analytics_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DailyAnalyticsRepository()
            result = await repo.get_for_date(DIST_ID, date(2025, 1, 15))
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_for_date_none(self) -> None:
        from app.db.repositories.daily_analytics_repo import (
            DailyAnalyticsRepository,
        )

        mock_db = _mock_supabase([])
        with patch(self.PATCH, return_value=mock_db):
            repo = DailyAnalyticsRepository()
            result = await repo.get_for_date(DIST_ID, date(2025, 6, 1))
            assert result is None

    @pytest.mark.asyncio
    async def test_get_range(self) -> None:
        from app.db.repositories.daily_analytics_repo import (
            DailyAnalyticsRepository,
        )

        rows = [_daily_analytics_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DailyAnalyticsRepository()
            result = await repo.get_range(
                DIST_ID, date(2025, 1, 1), date(2025, 1, 31)
            )
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_latest(self) -> None:
        from app.db.repositories.daily_analytics_repo import (
            DailyAnalyticsRepository,
        )

        rows = [_daily_analytics_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DailyAnalyticsRepository()
            result = await repo.get_latest(DIST_ID)
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# ANALYTICS REPOSITORY (events)
# ═══════════════════════════════════════════════════════════════


class TestAnalyticsRepo:
    """Test AnalyticsRepository with mocked Supabase."""

    PATCH = "app.db.repositories.analytics_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.analytics_repo import AnalyticsRepository
        from app.db.models.audit import AnalyticsEventCreate

        row = _analytics_event_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = AnalyticsRepository()
            data = AnalyticsEventCreate(event_type="message_received")
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_distributor_events(self) -> None:
        from app.db.repositories.analytics_repo import AnalyticsRepository

        rows = [_analytics_event_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = AnalyticsRepository()
            result = await repo.get_distributor_events(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_events_in_range(self) -> None:
        from app.db.repositories.analytics_repo import AnalyticsRepository

        rows = [_analytics_event_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = AnalyticsRepository()
            result = await repo.get_events_in_range(
                DIST_ID, "2025-01-01T00:00:00Z", "2025-01-31T23:59:59Z"
            )
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# AUDIT REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestAuditRepo:
    """Test AuditRepository with mocked Supabase."""

    PATCH = "app.db.repositories.audit_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.audit_repo import AuditRepository
        from app.db.models.audit import AuditLogCreate

        row = _audit_log_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = AuditRepository()
            data = AuditLogCreate(actor_type="system", action="order.created")
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_entity_history(self) -> None:
        from app.db.repositories.audit_repo import AuditRepository

        rows = [_audit_log_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = AuditRepository()
            result = await repo.get_entity_history("order", str(uuid4()))
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_distributor_audit(self) -> None:
        from app.db.repositories.audit_repo import AuditRepository

        rows = [_audit_log_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = AuditRepository()
            result = await repo.get_distributor_audit(DIST_ID)
            assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# DELIVERY ZONE REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestDeliveryZoneRepo:
    """Test DeliveryZoneRepository with mocked Supabase."""

    PATCH = "app.db.repositories.delivery_zone_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.delivery_zone_repo import (
            DeliveryZoneRepository,
        )

        row = _delivery_zone_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = DeliveryZoneRepository()
            result = await repo.get_by_id(row["id"], distributor_id=DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_active_zones(self) -> None:
        from app.db.repositories.delivery_zone_repo import (
            DeliveryZoneRepository,
        )

        rows = [_delivery_zone_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DeliveryZoneRepository()
            result = await repo.get_active_zones(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_find_zone_for_area_found(self) -> None:
        from app.db.repositories.delivery_zone_repo import (
            DeliveryZoneRepository,
        )

        rows = [_delivery_zone_row(areas=["gulberg", "model town", "dha"])]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DeliveryZoneRepository()
            result = await repo.find_zone_for_area(DIST_ID, "gulberg")
            assert result is not None

    @pytest.mark.asyncio
    async def test_find_zone_for_area_not_found(self) -> None:
        from app.db.repositories.delivery_zone_repo import (
            DeliveryZoneRepository,
        )

        rows = [_delivery_zone_row(areas=["gulberg"])]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DeliveryZoneRepository()
            result = await repo.find_zone_for_area(DIST_ID, "johar town")
            assert result is None

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.delivery_zone_repo import (
            DeliveryZoneRepository,
        )
        from app.db.models.delivery_zone import DeliveryZoneCreate

        row = _delivery_zone_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DeliveryZoneRepository()
            data = DeliveryZoneCreate(
                distributor_id=DIST_ID,
                name="Lahore South",
            )
            result = await repo.create(data)
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# DISCOUNT RULE REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestDiscountRuleRepo:
    """Test DiscountRuleRepository with mocked Supabase."""

    PATCH = "app.db.repositories.discount_rule_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_get_active_rules(self) -> None:
        from app.db.repositories.discount_rule_repo import (
            DiscountRuleRepository,
        )

        rows = [_discount_rule_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DiscountRuleRepository()
            result = await repo.get_active_rules(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_item_rules(self) -> None:
        from app.db.repositories.discount_rule_repo import (
            DiscountRuleRepository,
        )

        cat_id = str(uuid4())
        rows = [_discount_rule_row(catalog_id=cat_id)]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = DiscountRuleRepository()
            result = await repo.get_item_rules(DIST_ID, cat_id)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_increment_usage(self) -> None:
        from app.db.repositories.discount_rule_repo import (
            DiscountRuleRepository,
        )

        rule_id = str(uuid4())
        row = _discount_rule_row(id=rule_id, usage_count=1)
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = DiscountRuleRepository()
            # First call: select usage_count → maybe_single → dict
            # Second call: update → data[0]
            mock_db.execute = AsyncMock(
                side_effect=[
                    MagicMock(data={"usage_count": 0}),  # select
                    MagicMock(data=[row]),  # update
                ]
            )
            await repo.increment_usage(rule_id)

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.discount_rule_repo import (
            DiscountRuleRepository,
        )
        from app.db.models.discount_rule import DiscountRuleCreate

        row = _discount_rule_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = DiscountRuleRepository()
            data = DiscountRuleCreate(
                distributor_id=DIST_ID,
                rule_type="buy_x_get_y",
            )
            result = await repo.create(data)
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# NOTIFICATION REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestNotificationRepo:
    """Test NotificationRepository with mocked Supabase."""

    PATCH = "app.db.repositories.notification_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.notification_repo import (
            NotificationRepository,
        )
        from app.db.models.audit import NotificationLogCreate

        row = _notification_log_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = NotificationRepository()
            data = NotificationLogCreate(
                notification_type="order_confirmation"
            )
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_recent(self) -> None:
        from app.db.repositories.notification_repo import (
            NotificationRepository,
        )

        rows = [_notification_log_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = NotificationRepository()
            result = await repo.get_recent(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_update_delivery_status(self) -> None:
        from app.db.repositories.notification_repo import (
            NotificationRepository,
        )

        row = _notification_log_row(delivery_status="delivered")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = NotificationRepository()
            result = await repo.update_delivery_status(
                row["id"], "delivered"
            )
            assert result is not None


# ═══════════════════════════════════════════════════════════════
# INVENTORY SYNC LOG REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestSyncLogRepo:
    """Test InventorySyncLogRepository with mocked Supabase."""

    PATCH = "app.db.repositories.sync_log_repo.get_db_client"

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from app.db.repositories.sync_log_repo import (
            InventorySyncLogRepository,
        )
        from app.db.models.audit import InventorySyncLogCreate

        row = _sync_log_row()
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = InventorySyncLogRepository()
            data = InventorySyncLogCreate(distributor_id=DIST_ID)
            result = await repo.create(data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        from app.db.repositories.sync_log_repo import (
            InventorySyncLogRepository,
        )
        from app.db.models.audit import InventorySyncLogUpdate

        row = _sync_log_row(status="completed")
        mock_db = _mock_supabase([row])
        with patch(self.PATCH, return_value=mock_db):
            repo = InventorySyncLogRepository()
            data = InventorySyncLogUpdate(status="completed")
            result = await repo.update(row["id"], data)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        from app.db.repositories.sync_log_repo import (
            InventorySyncLogRepository,
        )

        row = _sync_log_row()
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = InventorySyncLogRepository()
            result = await repo.get_by_id(row["id"])
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_latest_for_distributor(self) -> None:
        from app.db.repositories.sync_log_repo import (
            InventorySyncLogRepository,
        )

        rows = [_sync_log_row()]
        mock_db = _mock_supabase(rows)
        with patch(self.PATCH, return_value=mock_db):
            repo = InventorySyncLogRepository()
            result = await repo.get_latest_for_distributor(DIST_ID)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_last_successful_sync(self) -> None:
        from app.db.repositories.sync_log_repo import (
            InventorySyncLogRepository,
        )

        row = _sync_log_row(status="completed")
        mock_db = _mock_supabase(row)
        with patch(self.PATCH, return_value=mock_db):
            repo = InventorySyncLogRepository()
            result = await repo.get_last_successful_sync(DIST_ID)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_last_successful_sync_none(self) -> None:
        from app.db.repositories.sync_log_repo import (
            InventorySyncLogRepository,
        )

        mock_db = _mock_supabase(None)
        with patch(self.PATCH, return_value=mock_db):
            repo = InventorySyncLogRepository()
            result = await repo.get_last_successful_sync(DIST_ID)
            assert result is None
