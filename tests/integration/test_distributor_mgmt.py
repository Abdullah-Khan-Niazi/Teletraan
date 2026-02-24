"""Integration tests for Phase 9 — Distributor Management System.

Tests cover:
- Subscription lifecycle FSM (transitions, validation, grace period)
- Reminder generation (7d, 3d, 1d, expiry, deduplication)
- Notification service (batch announcements, feature releases)
- Onboarding service (multi-step sequence, progress tracking)
- Support service (ticket lifecycle, owner notification)
- Scheduler jobs (reminder check, session cleanup, health checks)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.constants import (
    ActorType,
    ComplaintPriority,
    Language,
    RecipientType,
    ScheduledMessageStatus,
    SubscriptionStatus,
    SupportTicketCategory,
    SupportTicketStatus,
)
from app.db.models.distributor import Distributor


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _make_distributor(**overrides: Any) -> Distributor:
    """Build a Distributor model with sensible defaults."""
    now = datetime.now(tz=timezone.utc)
    defaults = {
        "id": uuid4(),
        "business_name": "Test Pharma",
        "owner_name": "Test Owner",
        "whatsapp_number": "+923001234567",
        "whatsapp_phone_number_id": "1234567890",
        "subscription_status": SubscriptionStatus.ACTIVE,
        "subscription_start": now - timedelta(days=25),
        "subscription_end": now + timedelta(days=5),
        "trial_end": now - timedelta(days=20),
        "grace_period_days": 3,
        "bot_language_default": Language.ROMAN_URDU,
        "is_active": True,
        "is_deleted": False,
        "metadata": {},
        "created_at": now - timedelta(days=30),
        "updated_at": now,
    }
    defaults.update(overrides)
    return Distributor(**defaults)


def _mock_supabase_chain() -> MagicMock:
    """Create a mock Supabase client chain.

    Returns synchronous MagicMock chain where each method returns
    self, and only .execute is AsyncMock.
    """
    mock = MagicMock()
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.insert.return_value = mock
    mock.update.return_value = mock
    mock.delete.return_value = mock
    mock.eq.return_value = mock
    mock.in_.return_value = mock
    mock.lte.return_value = mock
    mock.order.return_value = mock
    mock.limit.return_value = mock
    mock.maybe_single.return_value = mock
    mock.execute = AsyncMock()
    return mock


# ═══════════════════════════════════════════════════════════════════
# SUBSCRIPTION MANAGER TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSubscriptionManager:
    """Tests for SubscriptionManager FSM."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_activate_from_trial(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Trial → Active transition sets subscription dates."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.TRIAL)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.activate_subscription(str(dist.id), subscription_months=1)

        mock_dist_repo.update.assert_called_once()
        call_args = mock_dist_repo.update.call_args
        update_data = call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.ACTIVE
        assert update_data.is_active is True
        assert update_data.subscription_start is not None
        assert update_data.subscription_end is not None

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_activate_from_expiring_extends_end(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Expiring → Active extends from current subscription_end."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        now = datetime.now(tz=timezone.utc)
        sub_end = now + timedelta(days=2)
        dist = _make_distributor(
            subscription_status=SubscriptionStatus.EXPIRING,
            subscription_start=now - timedelta(days=28),
            subscription_end=sub_end,
        )

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.activate_subscription(str(dist.id), subscription_months=1)

        update_data = mock_dist_repo.update.call_args[0][1]
        # Should extend from sub_end, not from now
        assert update_data.subscription_end > sub_end

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_mark_expiring_from_active(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Active → Expiring transition."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.ACTIVE)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.mark_expiring(str(dist.id))

        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.EXPIRING

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_mark_expiring_idempotent(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Already EXPIRING — skip without error."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.EXPIRING)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.mark_expiring(str(dist.id))

        # update should NOT have been called
        mock_dist_repo.update.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_suspend_from_expiring(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Expiring → Suspended sets is_active=False."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.EXPIRING)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.suspend(str(dist.id))

        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.SUSPENDED
        assert update_data.is_active is False

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_cancel_from_suspended(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Suspended → Cancelled transition."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.SUSPENDED)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.cancel(str(dist.id))

        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.CANCELLED
        assert update_data.is_active is False

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_invalid_transition_raises(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Trial → Suspended is invalid — should raise ValueError."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.TRIAL)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        with pytest.raises(ValueError, match="Invalid subscription transition"):
            await mgr.suspend(str(dist.id))

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_reactivate_from_cancelled(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Cancelled → Active (re-subscription)."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        dist = _make_distributor(subscription_status=SubscriptionStatus.CANCELLED)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mgr = SubscriptionManager()
        await mgr.activate_subscription(str(dist.id))

        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.ACTIVE

    def test_is_subscription_valid(self) -> None:
        """Only TRIAL and ACTIVE allow bot operation."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        mgr = SubscriptionManager.__new__(SubscriptionManager)
        assert mgr.is_subscription_valid(SubscriptionStatus.TRIAL) is True
        assert mgr.is_subscription_valid(SubscriptionStatus.ACTIVE) is True
        assert mgr.is_subscription_valid(SubscriptionStatus.EXPIRING) is False
        assert mgr.is_subscription_valid(SubscriptionStatus.SUSPENDED) is False
        assert mgr.is_subscription_valid(SubscriptionStatus.CANCELLED) is False

    def test_calculate_grace_end(self) -> None:
        """Grace end = subscription_end + grace_period_days."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        now = datetime.now(tz=timezone.utc)
        dist = _make_distributor(
            subscription_end=now,
            grace_period_days=5,
        )
        result = SubscriptionManager._calculate_grace_end(dist)
        assert result is not None
        expected = now + timedelta(days=5)
        assert abs((result - expected).total_seconds()) < 1

    @pytest.mark.asyncio
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_lifecycle_checks_order(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """run_lifecycle_checks returns correct counts."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        mock_dist_repo = MagicMock()
        # get_expiring_subscriptions returns empty for simplicity
        mock_dist_repo.get_expiring_subscriptions = AsyncMock(return_value=[])
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        # Mock for _get_suspended_distributors
        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(data=[])
        mock_db_client.return_value = mock_client

        mgr = SubscriptionManager()
        result = await mgr.run_lifecycle_checks()

        assert "expiring" in result
        assert "suspended" in result
        assert "cancelled" in result
        assert result["expiring"] == 0
        assert result["suspended"] == 0
        assert result["cancelled"] == 0


# ═══════════════════════════════════════════════════════════════════
# REMINDER SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestReminderService:
    """Tests for ReminderService."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.reminder_service.get_settings")
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.reminder_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.reminder_service.DistributorRepository")
    async def test_generate_7day_reminder(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_db_client: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Generates 7-day reminder for distributor expiring in 5 days."""
        from app.distributor_mgmt.reminder_service import ReminderService

        now = datetime.now(tz=timezone.utc)
        dist = _make_distributor(
            subscription_end=now + timedelta(days=5),
        )

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_expiring_subscriptions = AsyncMock(
            return_value=[dist]
        )
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        # Mock dedup check — no existing reminders
        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(data=None)
        mock_db_client.return_value = mock_client

        settings = MagicMock()
        settings.payment_callback_base_url = "https://test.com"
        mock_settings.return_value = settings

        svc = ReminderService()
        result = await svc.generate_reminders_for_all()

        assert result["created"] >= 1
        assert mock_msg_repo.create.called

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.reminder_service.get_settings")
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.reminder_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.reminder_service.DistributorRepository")
    async def test_generate_all_reminders_for_expired(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_db_client: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Distributor past expiry gets all 4 reminders."""
        from app.distributor_mgmt.reminder_service import ReminderService

        now = datetime.now(tz=timezone.utc)
        dist = _make_distributor(
            subscription_status=SubscriptionStatus.EXPIRING,
            subscription_end=now - timedelta(hours=1),
        )

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_expiring_subscriptions = AsyncMock(
            return_value=[dist]
        )
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(data=None)
        mock_db_client.return_value = mock_client

        settings = MagicMock()
        settings.payment_callback_base_url = "https://test.com"
        mock_settings.return_value = settings

        svc = ReminderService()
        result = await svc.generate_reminders_for_all()

        # Should create 4 reminders (7d, 3d, 1d, expiry)
        assert result["created"] == 4

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.reminder_service.get_settings")
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.reminder_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.reminder_service.DistributorRepository")
    async def test_deduplication_skips_existing(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_db_client: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Existing reminders are skipped via idempotency_key check."""
        from app.distributor_mgmt.reminder_service import ReminderService

        now = datetime.now(tz=timezone.utc)
        dist = _make_distributor(
            subscription_end=now + timedelta(days=5),
        )

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_expiring_subscriptions = AsyncMock(
            return_value=[dist]
        )
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        # Mock dedup check — ALL reminders already exist
        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(
            data={"id": str(uuid4())}
        )
        mock_db_client.return_value = mock_client

        settings = MagicMock()
        settings.payment_callback_base_url = "https://test.com"
        mock_settings.return_value = settings

        svc = ReminderService()
        result = await svc.generate_reminders_for_all()

        assert result["created"] == 0
        assert result["skipped"] >= 1
        mock_msg_repo.create.assert_not_called()

    def test_idempotency_key_format(self) -> None:
        """Idempotency key follows expected format."""
        from app.distributor_mgmt.reminder_service import ReminderService

        dist_id = "abc-123"
        sub_end = datetime(2025, 3, 15, tzinfo=timezone.utc)
        key = ReminderService._build_idempotency_key(dist_id, 7, sub_end)
        assert key == "sub_reminder:abc-123:7:2025-03"

    def test_idempotency_key_ties_to_billing_cycle(self) -> None:
        """Different billing cycles get different keys."""
        from app.distributor_mgmt.reminder_service import ReminderService

        dist_id = "abc-123"
        key1 = ReminderService._build_idempotency_key(
            dist_id, 7, datetime(2025, 3, 15, tzinfo=timezone.utc)
        )
        key2 = ReminderService._build_idempotency_key(
            dist_id, 7, datetime(2025, 4, 15, tzinfo=timezone.utc)
        )
        assert key1 != key2

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.reminder_service.get_settings")
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.reminder_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.reminder_service.DistributorRepository")
    async def test_suspension_notification(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_db_client: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Generates suspension notification for suspended distributor."""
        from app.distributor_mgmt.reminder_service import ReminderService

        dist = _make_distributor(
            subscription_status=SubscriptionStatus.SUSPENDED,
            grace_period_days=3,
        )

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(data=None)
        mock_db_client.return_value = mock_client

        settings = MagicMock()
        settings.payment_callback_base_url = "https://test.com"
        mock_settings.return_value = settings

        svc = ReminderService()
        await svc.generate_suspension_notification(dist)

        mock_msg_repo.create.assert_called_once()
        call_args = mock_msg_repo.create.call_args[0][0]
        assert call_args.message_type == "subscription_suspended"


# ═══════════════════════════════════════════════════════════════════
# NOTIFICATION SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.notification_service.AuditRepository")
    @patch("app.distributor_mgmt.notification_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.notification_service.DistributorRepository")
    async def test_send_announcement(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Announcement sends to all active distributors."""
        from app.distributor_mgmt.notification_service import NotificationService

        dists = [_make_distributor() for _ in range(3)]

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_active_distributors = AsyncMock(return_value=dists)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = NotificationService()
        result = await svc.send_announcement(
            title="System Update",
            body="New features available.",
        )

        assert result["created"] == 3
        assert result["failed"] == 0
        assert mock_msg_repo.create.call_count == 3

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.notification_service.AuditRepository")
    @patch("app.distributor_mgmt.notification_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.notification_service.DistributorRepository")
    async def test_send_to_subset(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Targeted notification to specific distributors."""
        from app.distributor_mgmt.notification_service import NotificationService

        dist = _make_distributor()

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = NotificationService()
        result = await svc.send_custom_notification(
            message_type="test",
            text="Hello",
            distributor_ids=[str(dist.id)],
        )

        assert result["created"] == 1

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.notification_service.AuditRepository")
    @patch("app.distributor_mgmt.notification_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.notification_service.DistributorRepository")
    async def test_empty_audience_returns_zero(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """No active distributors — returns zero."""
        from app.distributor_mgmt.notification_service import NotificationService

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_active_distributors = AsyncMock(return_value=[])
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        svc = NotificationService()
        result = await svc.send_feature_release(
            feature_name="Test",
            description="Test desc",
        )

        assert result["created"] == 0

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.notification_service.AuditRepository")
    @patch("app.distributor_mgmt.notification_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.notification_service.DistributorRepository")
    async def test_maintenance_alert(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Maintenance alert sends with correct format."""
        from app.distributor_mgmt.notification_service import NotificationService

        dist = _make_distributor()

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_active_distributors = AsyncMock(return_value=[dist])
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = NotificationService()
        result = await svc.send_maintenance_alert(
            start_time="2025-01-20 02:00 UTC",
            duration="30 minutes",
            description="Database migration",
        )

        assert result["created"] == 1
        msg_data = mock_msg_repo.create.call_args[0][0]
        assert "Maintenance" in msg_data.message_payload["text"]


# ═══════════════════════════════════════════════════════════════════
# ONBOARDING SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestOnboardingService:
    """Tests for OnboardingService."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.AuditRepository")
    @patch("app.distributor_mgmt.onboarding_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.onboarding_service.DistributorRepository")
    async def test_start_onboarding(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """start_onboarding marks payment_confirmed and sends welcome."""
        from app.distributor_mgmt.onboarding_service import OnboardingService

        dist = _make_distributor(metadata={})

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = OnboardingService()
        await svc.start_onboarding(str(dist.id))

        # Should have sent a welcome message
        assert mock_msg_repo.create.called
        msg_data = mock_msg_repo.create.call_args[0][0]
        assert "welcome" in msg_data.message_type

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.AuditRepository")
    @patch("app.distributor_mgmt.onboarding_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.onboarding_service.DistributorRepository")
    async def test_already_onboarded_skips(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Already onboarded distributor — skip."""
        from app.distributor_mgmt.onboarding_service import OnboardingService

        dist = _make_distributor(onboarding_completed=True)

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        svc = OnboardingService()
        await svc.start_onboarding(str(dist.id))

        mock_dist_repo.update.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.AuditRepository")
    @patch("app.distributor_mgmt.onboarding_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.onboarding_service.DistributorRepository")
    async def test_advance_onboarding(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """advance_onboarding returns the next step."""
        from app.distributor_mgmt.onboarding_service import (
            OnboardingService,
            OnboardingStep,
        )

        dist = _make_distributor(metadata={
            "onboarding": {"completed_steps": ["payment_confirmed", "welcome_sent"]}
        })

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = OnboardingService()
        next_step = await svc.advance_onboarding(
            str(dist.id),
            OnboardingStep.SETUP_GUIDE_SENT,
        )

        assert next_step == OnboardingStep.TEST_ORDER_SENT

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.AuditRepository")
    @patch("app.distributor_mgmt.onboarding_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.onboarding_service.DistributorRepository")
    async def test_advance_to_go_live_completes(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Completing GO_LIVE step finalizes onboarding."""
        from app.distributor_mgmt.onboarding_service import (
            OnboardingService,
            OnboardingStep,
        )

        dist = _make_distributor(metadata={
            "onboarding": {
                "completed_steps": [
                    "payment_confirmed", "welcome_sent",
                    "setup_guide_sent", "test_order_sent",
                    "catalog_upload_prompted",
                ]
            }
        })

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = OnboardingService()
        next_step = await svc.advance_onboarding(
            str(dist.id),
            OnboardingStep.GO_LIVE,
        )

        # Should return None (completed)
        assert next_step is None
        # Should have set onboarding_completed=True
        update_calls = mock_dist_repo.update.call_args_list
        found_completion = any(
            getattr(call.args[1], "onboarding_completed", None) is True
            for call in update_calls
        )
        assert found_completion

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.AuditRepository")
    @patch("app.distributor_mgmt.onboarding_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.onboarding_service.DistributorRepository")
    async def test_get_onboarding_progress(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Progress reports completed steps and current step."""
        from app.distributor_mgmt.onboarding_service import OnboardingService

        dist = _make_distributor(metadata={
            "onboarding": {"completed_steps": ["payment_confirmed", "welcome_sent"]}
        })

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        svc = OnboardingService()
        progress = await svc.get_onboarding_progress(str(dist.id))

        assert progress["completed_count"] == 2
        assert progress["current_step"] == "setup_guide_sent"
        assert progress["total_steps"] == 6

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.AuditRepository")
    @patch("app.distributor_mgmt.onboarding_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.onboarding_service.DistributorRepository")
    async def test_reset_onboarding(
        self,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Reset clears onboarding metadata and completed flag."""
        from app.distributor_mgmt.onboarding_service import OnboardingService

        dist = _make_distributor(
            onboarding_completed=True,
            metadata={"onboarding": {"completed_steps": ["a", "b"]}},
        )

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock(return_value=dist)
        mock_dist_repo.update = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = OnboardingService()
        await svc.reset_onboarding(str(dist.id))

        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.onboarding_completed is False
        assert "onboarding" not in update_data.metadata

    def test_get_next_step(self) -> None:
        """Correct next step resolution."""
        from app.distributor_mgmt.onboarding_service import (
            OnboardingService,
            OnboardingStep,
        )

        assert (
            OnboardingService._get_next_step(OnboardingStep.PAYMENT_CONFIRMED)
            == OnboardingStep.WELCOME_SENT
        )
        assert (
            OnboardingService._get_next_step(OnboardingStep.CATALOG_UPLOAD_PROMPTED)
            == OnboardingStep.GO_LIVE
        )
        assert OnboardingService._get_next_step(OnboardingStep.GO_LIVE) is None


# ═══════════════════════════════════════════════════════════════════
# SUPPORT SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSupportService:
    """Tests for SupportService."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.support_service.get_settings")
    @patch("app.distributor_mgmt.support_service.AuditRepository")
    @patch("app.distributor_mgmt.support_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.support_service.DistributorRepository")
    @patch("app.distributor_mgmt.support_service.SupportTicketRepository")
    async def test_create_ticket(
        self,
        mock_ticket_repo_cls: MagicMock,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Creates ticket, notifies owner, sends receipt."""
        from app.distributor_mgmt.support_service import SupportService
        from app.db.models.support_ticket import SupportTicket

        dist = _make_distributor()
        now = datetime.now(tz=timezone.utc)
        ticket = SupportTicket(
            id=uuid4(),
            ticket_number="TKT-20250120-1234",
            distributor_id=dist.id,
            description="Bot not responding",
            category=SupportTicketCategory.BOT_ISSUE,
            status=SupportTicketStatus.OPEN,
            priority=ComplaintPriority.HIGH,
            metadata={},
            created_at=now,
            updated_at=now,
        )

        mock_ticket_repo = MagicMock()
        mock_ticket_repo.create = AsyncMock(return_value=ticket)
        mock_ticket_repo_cls.return_value = mock_ticket_repo

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        settings = MagicMock()
        settings.owner_whatsapp_number = "+923000000000"
        mock_settings.return_value = settings

        svc = SupportService()
        result = await svc.create_ticket(
            distributor_id=str(dist.id),
            description="Bot not responding",
            category=SupportTicketCategory.BOT_ISSUE,
            priority=ComplaintPriority.HIGH,
        )

        assert result.ticket_number == "TKT-20250120-1234"
        # Owner notification + receipt = 2 messages
        assert mock_msg_repo.create.call_count == 2

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.support_service.AuditRepository")
    @patch("app.distributor_mgmt.support_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.support_service.DistributorRepository")
    @patch("app.distributor_mgmt.support_service.SupportTicketRepository")
    async def test_resolve_ticket(
        self,
        mock_ticket_repo_cls: MagicMock,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Resolving sends notification to distributor."""
        from app.distributor_mgmt.support_service import SupportService
        from app.db.models.support_ticket import SupportTicket

        dist = _make_distributor()
        now = datetime.now(tz=timezone.utc)
        ticket = SupportTicket(
            id=uuid4(),
            ticket_number="TKT-20250120-1234",
            distributor_id=dist.id,
            description="Bot not responding",
            status=SupportTicketStatus.IN_PROGRESS,
            priority=ComplaintPriority.NORMAL,
            metadata={},
            created_at=now,
            updated_at=now,
        )
        resolved_ticket = SupportTicket(
            id=ticket.id,
            ticket_number=ticket.ticket_number,
            distributor_id=dist.id,
            description=ticket.description,
            status=SupportTicketStatus.RESOLVED,
            priority=ComplaintPriority.NORMAL,
            owner_response="Restarted the bot service.",
            resolved_at=now,
            metadata={},
            created_at=now,
            updated_at=now,
        )

        mock_ticket_repo = MagicMock()
        mock_ticket_repo.get_by_id_or_raise = AsyncMock(return_value=ticket)
        mock_ticket_repo.update = AsyncMock(return_value=resolved_ticket)
        mock_ticket_repo_cls.return_value = mock_ticket_repo

        mock_dist_repo = MagicMock()
        mock_dist_repo.get_by_id = AsyncMock(return_value=dist)
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo.create = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = SupportService()
        result = await svc.resolve_ticket(
            str(ticket.id),
            response="Restarted the bot service.",
        )

        assert result.status == SupportTicketStatus.RESOLVED
        # Resolution notification
        assert mock_msg_repo.create.called

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.support_service.AuditRepository")
    @patch("app.distributor_mgmt.support_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.support_service.DistributorRepository")
    @patch("app.distributor_mgmt.support_service.SupportTicketRepository")
    async def test_close_ticket(
        self,
        mock_ticket_repo_cls: MagicMock,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Closing a ticket changes status to CLOSED."""
        from app.distributor_mgmt.support_service import SupportService
        from app.db.models.support_ticket import SupportTicket

        now = datetime.now(tz=timezone.utc)
        dist_id = uuid4()
        ticket = SupportTicket(
            id=uuid4(),
            ticket_number="TKT-20250120-5678",
            distributor_id=dist_id,
            description="Issue resolved",
            status=SupportTicketStatus.RESOLVED,
            priority=ComplaintPriority.NORMAL,
            metadata={},
            created_at=now,
            updated_at=now,
        )
        closed_ticket = SupportTicket(
            **{**ticket.model_dump(), "status": SupportTicketStatus.CLOSED}
        )

        mock_ticket_repo = MagicMock()
        mock_ticket_repo.get_by_id_or_raise = AsyncMock(return_value=ticket)
        mock_ticket_repo.update = AsyncMock(return_value=closed_ticket)
        mock_ticket_repo_cls.return_value = mock_ticket_repo

        mock_dist_repo = MagicMock()
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = SupportService()
        result = await svc.close_ticket(str(ticket.id))

        assert result.status == SupportTicketStatus.CLOSED

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.support_service.AuditRepository")
    @patch("app.distributor_mgmt.support_service.ScheduledMessageRepository")
    @patch("app.distributor_mgmt.support_service.DistributorRepository")
    @patch("app.distributor_mgmt.support_service.SupportTicketRepository")
    async def test_update_priority(
        self,
        mock_ticket_repo_cls: MagicMock,
        mock_dist_repo_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
        mock_audit_cls: MagicMock,
    ) -> None:
        """Priority update changes ticket priority."""
        from app.distributor_mgmt.support_service import SupportService
        from app.db.models.support_ticket import SupportTicket

        now = datetime.now(tz=timezone.utc)
        dist_id = uuid4()
        ticket = SupportTicket(
            id=uuid4(),
            ticket_number="TKT-20250120-9999",
            distributor_id=dist_id,
            description="Upgrade priority",
            status=SupportTicketStatus.OPEN,
            priority=ComplaintPriority.NORMAL,
            metadata={},
            created_at=now,
            updated_at=now,
        )
        updated_ticket = SupportTicket(
            **{**ticket.model_dump(), "priority": ComplaintPriority.URGENT}
        )

        mock_ticket_repo = MagicMock()
        mock_ticket_repo.get_by_id_or_raise = AsyncMock(return_value=ticket)
        mock_ticket_repo.update = AsyncMock(return_value=updated_ticket)
        mock_ticket_repo_cls.return_value = mock_ticket_repo

        mock_dist_repo = MagicMock()
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_msg_repo = MagicMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        svc = SupportService()
        result = await svc.update_priority(
            str(ticket.id), ComplaintPriority.URGENT
        )

        assert result.priority == ComplaintPriority.URGENT

    def test_generate_ticket_number_format(self) -> None:
        """Ticket numbers follow TKT-YYYYMMDD-NNNN format."""
        from app.distributor_mgmt.support_service import SupportService

        number = SupportService._generate_ticket_number()
        assert number.startswith("TKT-")
        parts = number.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 4  # seq


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER JOBS TESTS
# ═══════════════════════════════════════════════════════════════════


class TestReminderJobs:
    """Tests for reminder scheduler jobs."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.reminder_service.reminder_service")
    @patch("app.distributor_mgmt.subscription_manager.subscription_manager")
    async def test_run_reminder_check(
        self,
        mock_sub_mgr: MagicMock,
        mock_rem_svc: MagicMock,
    ) -> None:
        """Reminder check job runs lifecycle and reminders."""
        from app.scheduler.jobs.reminder_jobs import run_reminder_check

        mock_sub_mgr.run_lifecycle_checks = AsyncMock(
            return_value={"expiring": 1, "suspended": 0, "cancelled": 0}
        )
        mock_rem_svc.generate_reminders_for_all = AsyncMock(
            return_value={"created": 2, "skipped": 1}
        )

        await run_reminder_check()

        mock_sub_mgr.run_lifecycle_checks.assert_called_once()
        mock_rem_svc.generate_reminders_for_all.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.db.repositories.scheduled_message_repo.ScheduledMessageRepository")
    @patch("app.notifications.whatsapp_notifier.WhatsAppNotifier")
    async def test_run_send_scheduled_messages(
        self,
        mock_notifier_cls: MagicMock,
        mock_msg_repo_cls: MagicMock,
    ) -> None:
        """Message sender picks up due messages and sends them."""
        from app.scheduler.jobs.reminder_jobs import run_send_scheduled_messages
        from app.db.models.audit import ScheduledMessage

        now = datetime.now(tz=timezone.utc)
        msg = ScheduledMessage(
            id=uuid4(),
            recipient_number="+923001234567",
            recipient_type=RecipientType.DISTRIBUTOR,
            message_type="test",
            message_payload={"text": "Hello"},
            scheduled_for=now - timedelta(minutes=5),
            status=ScheduledMessageStatus.PENDING,
            distributor_id=uuid4(),
            created_at=now,
        )

        mock_msg_repo = MagicMock()
        mock_msg_repo.get_due_messages = AsyncMock(return_value=[msg])
        mock_msg_repo.mark_sent = AsyncMock()
        mock_msg_repo_cls.return_value = mock_msg_repo

        mock_notifier = MagicMock()
        mock_notifier.send_text = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        await run_send_scheduled_messages()

        mock_notifier.send_text.assert_called_once()
        mock_msg_repo.mark_sent.assert_called_once()


class TestCleanupJobs:
    """Tests for cleanup scheduler jobs."""

    @pytest.mark.asyncio
    @patch("app.db.repositories.session_repo.SessionRepository")
    async def test_run_session_cleanup(
        self,
        mock_session_repo_cls: MagicMock,
    ) -> None:
        """Session cleanup deletes expired sessions."""
        from app.scheduler.jobs.cleanup_jobs import run_session_cleanup

        mock_session = MagicMock()
        mock_session.id = uuid4()

        mock_repo = MagicMock()
        mock_repo.get_expired_sessions = AsyncMock(
            return_value=[mock_session]
        )
        mock_repo.delete_session = AsyncMock(return_value=True)
        mock_session_repo_cls.return_value = mock_repo

        await run_session_cleanup()

        mock_repo.delete_session.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.payments.service.payment_service")
    async def test_run_expired_payment_cleanup(
        self,
        mock_pay_svc: MagicMock,
    ) -> None:
        """Payment cleanup calls expire_stale_payments."""
        from app.scheduler.jobs.cleanup_jobs import run_expired_payment_cleanup

        mock_pay_svc.expire_stale_payments = AsyncMock(return_value=3)

        await run_expired_payment_cleanup()

        mock_pay_svc.expire_stale_payments.assert_called_once()


class TestHealthJobs:
    """Tests for health check scheduler jobs."""

    @pytest.mark.asyncio
    @patch(
        "app.scheduler.jobs.health_jobs._check_database_health",
        new_callable=AsyncMock,
    )
    @patch(
        "app.scheduler.jobs.health_jobs._check_gateway_health",
        new_callable=AsyncMock,
    )
    @patch(
        "app.scheduler.jobs.health_jobs._check_ai_health",
        new_callable=AsyncMock,
    )
    async def test_run_system_health_check(
        self,
        mock_ai: AsyncMock,
        mock_gw: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """System health check reports all components."""
        from app.scheduler.jobs.health_jobs import run_system_health_check

        mock_ai.return_value = {"healthy": True, "provider": "GeminiProvider"}
        mock_gw.return_value = {"healthy": True, "gateways": {"dummy": True}}
        mock_db.return_value = {"healthy": True, "latency_ms": 5.2}

        await run_system_health_check()

        mock_ai.assert_called_once()
        mock_gw.assert_called_once()
        mock_db.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.ai.factory.get_ai_provider")
    async def test_ai_health_check(
        self,
        mock_get_provider: MagicMock,
    ) -> None:
        """AI health check returns provider name."""
        from app.scheduler.jobs.health_jobs import _check_ai_health

        mock_provider = MagicMock()
        mock_provider.__class__.__name__ = "GeminiProvider"
        mock_get_provider.return_value = mock_provider

        result = await _check_ai_health()

        assert result["healthy"] is True
        assert "provider" in result

    @pytest.mark.asyncio
    @patch("app.db.client.get_db_client")
    async def test_db_health_check(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """DB health check returns latency."""
        from app.scheduler.jobs.health_jobs import _check_database_health

        mock_client = _mock_supabase_chain()
        mock_result = MagicMock()
        mock_result.count = 5
        mock_client.execute.return_value = mock_result
        mock_db_client.return_value = mock_client

        result = await _check_database_health()

        assert result["healthy"] is True
        assert "latency_ms" in result


# ═══════════════════════════════════════════════════════════════════
# FULL LIFECYCLE INTEGRATION TEST
# ═══════════════════════════════════════════════════════════════════


class TestSubscriptionLifecycleIntegration:
    """End-to-end subscription lifecycle: trial → active → expiring →
    suspended → cancelled, verifying reminders at each stage."""

    @pytest.mark.asyncio
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_full_lifecycle(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """Trial → Active → Expiring → Suspended → Cancelled."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        now = datetime.now(tz=timezone.utc)

        # Track state changes
        current_status = SubscriptionStatus.TRIAL

        def make_dist_with_status():
            return _make_distributor(
                subscription_status=current_status,
                subscription_end=now + timedelta(days=5),
                grace_period_days=3,
            )

        mock_dist_repo = MagicMock()
        mock_dist_repo.update = AsyncMock()
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(data=[])
        mock_db_client.return_value = mock_client

        mgr = SubscriptionManager()

        # Step 1: Trial → Active
        mock_dist_repo.get_by_id_or_raise = AsyncMock(
            return_value=make_dist_with_status()
        )
        await mgr.activate_subscription("test-id")
        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.ACTIVE
        current_status = SubscriptionStatus.ACTIVE

        # Step 2: Active → Expiring
        mock_dist_repo.get_by_id_or_raise = AsyncMock(
            return_value=make_dist_with_status()
        )
        await mgr.mark_expiring("test-id")
        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.EXPIRING
        current_status = SubscriptionStatus.EXPIRING

        # Step 3: Expiring → Suspended
        mock_dist_repo.get_by_id_or_raise = AsyncMock(
            return_value=make_dist_with_status()
        )
        await mgr.suspend("test-id")
        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.SUSPENDED
        current_status = SubscriptionStatus.SUSPENDED

        # Step 4: Suspended → Cancelled
        mock_dist_repo.get_by_id_or_raise = AsyncMock(
            return_value=make_dist_with_status()
        )
        await mgr.cancel("test-id")
        update_data = mock_dist_repo.update.call_args[0][1]
        assert update_data.subscription_status == SubscriptionStatus.CANCELLED

    @pytest.mark.asyncio
    @patch("app.db.client.get_db_client")
    @patch("app.distributor_mgmt.subscription_manager.AuditRepository")
    @patch("app.distributor_mgmt.subscription_manager.DistributorRepository")
    async def test_grace_period_flow(
        self, mock_dist_repo_cls: MagicMock, mock_audit_cls: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """Suspended distributor within grace period stays suspended,
        past grace period gets cancelled."""
        from app.distributor_mgmt.subscription_manager import SubscriptionManager

        now = datetime.now(tz=timezone.utc)

        # Distributor suspended, grace NOT expired (sub_end was 1 day ago,
        # grace 3 days → grace_end is 2 days in future)
        dist_within_grace = _make_distributor(
            subscription_status=SubscriptionStatus.SUSPENDED,
            subscription_end=now - timedelta(days=1),
            grace_period_days=3,
        )

        # Distributor suspended, grace EXPIRED (sub_end was 5 days ago,
        # grace 3 days → grace_end was 2 days ago)
        dist_past_grace = _make_distributor(
            subscription_status=SubscriptionStatus.SUSPENDED,
            subscription_end=now - timedelta(days=5),
            grace_period_days=3,
        )

        mock_dist_repo = MagicMock()
        mock_dist_repo.update = AsyncMock()
        mock_dist_repo.get_by_id_or_raise = AsyncMock()
        mock_dist_repo_cls.return_value = mock_dist_repo

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        # Mock _get_suspended_distributors
        mock_client = _mock_supabase_chain()
        mock_client.execute.return_value = MagicMock(data=[
            dist_within_grace.model_dump(mode="json"),
            dist_past_grace.model_dump(mode="json"),
        ])
        mock_db_client.return_value = mock_client

        mgr = SubscriptionManager()

        # For the cancel call, we need get_by_id_or_raise to return dist_past_grace
        mock_dist_repo.get_by_id_or_raise = AsyncMock(
            return_value=dist_past_grace
        )

        cancelled = await mgr.check_and_cancel_grace_expired()

        # Only the past-grace distributor should be cancelled
        assert cancelled == 1
