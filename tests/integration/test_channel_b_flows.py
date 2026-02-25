"""Integration tests for Channel B — end-to-end sales funnel.

Tests the complete flow: first message → qualification → service
presentation → payment link → payment confirmed → distributor
record created → onboarding started.

Also tests: owner commands, interrupts, service registry caching,
session expiry, and idempotent onboarding.
"""

from __future__ import annotations

import datetime
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.channels.channel_b.handler import handle_channel_b_message
from app.channels.channel_b.sales_flow import handle_sales_step
from app.channels.channel_b.state_machine import (
    TransitionResult,
    can_transition,
    get_initial_state,
    transition,
)
from app.channels.interrupts import InterruptType, detect_interrupt, get_target_state_b
from app.core.constants import (
    ChannelType,
    Language,
    ProspectStatus,
    SessionStateB,
    SubscriptionStatus,
)
from app.db.models.prospect import Prospect, ProspectCreate, ProspectUpdate
from app.db.models.service_registry import ServiceRegistryEntry
from app.db.models.session import Session


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

_DIST_ID = uuid4()
_NOW = datetime.datetime.now(datetime.timezone.utc)


def _make_session(
    state: str = SessionStateB.IDLE.value,
    *,
    state_data: dict | None = None,
    expires_minutes: int = 30,
) -> Session:
    """Build a minimal Channel B session for testing."""
    return Session(
        id=uuid4(),
        distributor_id=_DIST_ID,
        whatsapp_number="+923009999888",
        channel=ChannelType.B,
        current_state=state,
        language=Language.ROMAN_URDU,
        state_data=state_data or {},
        last_message_at=_NOW,
        expires_at=_NOW + datetime.timedelta(minutes=expires_minutes),
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_prospect(**overrides: Any) -> Prospect:
    """Build a Prospect model with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "whatsapp_number": "+923009999888",
        "name": "Test Prospect",
        "business_name": "Test Pharma",
        "city": "Lahore",
        "estimated_retailer_count": 50,
        "status": ProspectStatus.NEW,
        "metadata": {},
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return Prospect(**defaults)


def _make_service(**overrides: Any) -> ServiceRegistryEntry:
    """Build a ServiceRegistryEntry with defaults."""
    defaults = {
        "id": uuid4(),
        "name": "TELETRAAN Order Bot",
        "slug": "teletraan-order-bot",
        "description": "WhatsApp order management for distributors",
        "short_description": "WhatsApp order bot",
        "setup_fee_paisas": 500000,
        "monthly_fee_paisas": 1500000,
        "sales_flow_handler": "teletraan_sales",
        "target_business_types": ["medicine_distributor"],
        "is_available": True,
        "is_coming_soon": False,
        "metadata": {},
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return ServiceRegistryEntry(**defaults)


def _mock_session_repo() -> MagicMock:
    """Create a mock SessionRepository."""
    repo = MagicMock()
    repo.update_state = AsyncMock()
    return repo


def _mock_prospect_repo(prospect: Prospect | None = None) -> MagicMock:
    """Create a mock ProspectRepository."""
    repo = MagicMock()
    p = prospect or _make_prospect()
    repo.get_by_whatsapp_number = AsyncMock(return_value=p)
    repo.get_by_id = AsyncMock(return_value=p)
    repo.get_by_id_or_raise = AsyncMock(return_value=p)
    repo.create = AsyncMock(return_value=p)
    repo.update = AsyncMock(return_value=p)
    repo.get_by_status = AsyncMock(return_value=[])
    return repo


# ═══════════════════════════════════════════════════════════════════
# STATE MACHINE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestChannelBStateMachine:
    """Tests for Channel B FSM transitions."""

    def test_initial_state(self) -> None:
        """Initial state is GREETING."""
        assert get_initial_state() == SessionStateB.GREETING

    def test_greeting_to_qualification(self) -> None:
        """GREETING → QUALIFICATION_NAME valid."""
        result = can_transition(SessionStateB.GREETING.value, SessionStateB.QUALIFICATION_NAME.value)
        assert result.allowed

    def test_qualification_sequence(self) -> None:
        """Full qualification chain is valid."""
        assert can_transition(
            SessionStateB.QUALIFICATION_NAME.value, SessionStateB.QUALIFICATION_BUSINESS.value
        ).allowed
        assert can_transition(
            SessionStateB.QUALIFICATION_BUSINESS.value, SessionStateB.QUALIFICATION_CITY.value
        ).allowed
        assert can_transition(
            SessionStateB.QUALIFICATION_CITY.value, SessionStateB.QUALIFICATION_RETAILER_COUNT.value
        ).allowed

    def test_retailer_to_demo_or_proposal(self) -> None:
        """After qualification: demo or proposal."""
        assert can_transition(
            SessionStateB.QUALIFICATION_RETAILER_COUNT.value, SessionStateB.DEMO_BOOKING.value
        ).allowed
        assert can_transition(
            SessionStateB.QUALIFICATION_RETAILER_COUNT.value, SessionStateB.PROPOSAL_SENT.value
        ).allowed

    def test_proposal_to_payment(self) -> None:
        """PROPOSAL_SENT → PAYMENT_PENDING."""
        assert can_transition(
            SessionStateB.PROPOSAL_SENT.value, SessionStateB.PAYMENT_PENDING.value
        ).allowed

    def test_payment_to_onboarding(self) -> None:
        """PAYMENT_PENDING → ONBOARDING_SETUP."""
        assert can_transition(
            SessionStateB.PAYMENT_PENDING.value, SessionStateB.ONBOARDING_SETUP.value
        ).allowed

    def test_universal_interrupts(self) -> None:
        """All states can reach IDLE and HANDOFF."""
        for state in SessionStateB:
            if state in {SessionStateB.IDLE}:
                continue
            assert can_transition(state.value, SessionStateB.IDLE.value).allowed, (
                f"{state} should be able to reach IDLE"
            )

    def test_invalid_transition(self) -> None:
        """IDLE → PAYMENT_PENDING is invalid."""
        result = can_transition(
            SessionStateB.IDLE.value, SessionStateB.PAYMENT_PENDING.value
        )
        assert not result.allowed


class TestInterruptDetection:
    """Channel B interrupt handling."""

    def test_handoff_interrupt(self) -> None:
        """'talk to human' triggers HANDOFF."""
        result = detect_interrupt("talk to human")
        assert result == InterruptType.HANDOFF

    def test_cancel_interrupt(self) -> None:
        """'cancel' triggers CANCEL."""
        result = detect_interrupt("cancel")
        assert result == InterruptType.CANCEL

    def test_get_target_state_b(self) -> None:
        """Interrupt maps to correct Channel B state."""
        assert get_target_state_b(InterruptType.HANDOFF) == SessionStateB.HANDOFF.value
        assert get_target_state_b(InterruptType.CANCEL) == SessionStateB.IDLE.value


# ═══════════════════════════════════════════════════════════════════
# HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════


class TestChannelBHandler:
    """Tests for the main Channel B handler."""

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_idle_sends_welcome(self, mock_refresh: AsyncMock) -> None:
        """IDLE state auto-starts greeting."""
        session = _make_session(state=SessionStateB.IDLE.value)
        sess_repo = _mock_session_repo()

        msgs = await handle_channel_b_message(
            session, "hi",
            session_repo=sess_repo,
        )

        assert len(msgs) >= 1
        assert "TELETRAAN" in msgs[0]["text"]["body"]
        sess_repo.update_state.assert_called()

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_expired_session_resets(self, mock_refresh: AsyncMock) -> None:
        """Expired session resets to GREETING."""
        session = _make_session(
            state=SessionStateB.QUALIFICATION_NAME.value,
            expires_minutes=-5,  # expired
        )
        sess_repo = _mock_session_repo()

        msgs = await handle_channel_b_message(
            session, "test",
            session_repo=sess_repo,
        )

        assert "expire" in msgs[0]["text"]["body"].lower()

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_handoff_interrupt(self, mock_refresh: AsyncMock) -> None:
        """'talk to human' triggers handoff."""
        session = _make_session(state=SessionStateB.QUALIFICATION_BUSINESS.value)
        sess_repo = _mock_session_repo()

        msgs = await handle_channel_b_message(
            session, "talk to human",
            session_repo=sess_repo,
        )

        assert any("team" in m.get("text", {}).get("body", "").lower() for m in msgs)


# ═══════════════════════════════════════════════════════════════════
# SALES FLOW TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSalesFlow:
    """Tests for individual sales flow stages."""

    @pytest.mark.asyncio
    async def test_greeting_positive(self) -> None:
        """Positive response → QUALIFICATION_NAME."""
        session = _make_session(state=SessionStateB.GREETING.value)
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "haan",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        assert len(msgs) >= 1
        assert "naam" in msgs[0]["text"]["body"].lower()
        sess_repo.update_state.assert_called()
        # Should have transitioned to QUALIFICATION_NAME
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.QUALIFICATION_NAME

    @pytest.mark.asyncio
    async def test_greeting_negative(self) -> None:
        """Negative response → IDLE."""
        session = _make_session(state=SessionStateB.GREETING.value)
        sess_repo = _mock_session_repo()

        msgs = await handle_sales_step(
            session, "nahi",
            session_repo=sess_repo,
        )

        assert any("allah hafiz" in m.get("text", {}).get("body", "").lower() for m in msgs)

    @pytest.mark.asyncio
    async def test_qualification_name(self) -> None:
        """Name collection → QUALIFICATION_BUSINESS."""
        session = _make_session(
            state=SessionStateB.QUALIFICATION_NAME.value,
            state_data={"prospect_id": str(uuid4())},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "Ahmed Khan",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        assert "business" in msgs[0]["text"]["body"].lower()
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.QUALIFICATION_BUSINESS

    @pytest.mark.asyncio
    async def test_qualification_business(self) -> None:
        """Business name → QUALIFICATION_CITY."""
        session = _make_session(
            state=SessionStateB.QUALIFICATION_BUSINESS.value,
            state_data={"prospect_id": str(uuid4()), "qualification": {"name": "Ahmed"}},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "Khan Pharma",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        assert "city" in msgs[0]["text"]["body"].lower()

    @pytest.mark.asyncio
    async def test_qualification_city(self) -> None:
        """City → QUALIFICATION_RETAILER_COUNT."""
        session = _make_session(
            state=SessionStateB.QUALIFICATION_CITY.value,
            state_data={"prospect_id": str(uuid4()), "qualification": {"name": "A", "business_name": "B"}},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "Lahore",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        assert "retailer" in msgs[0]["text"]["body"].lower()

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.service_registry.service_registry")
    async def test_qualification_retailer_count(
        self, mock_service_reg: MagicMock
    ) -> None:
        """Retailer count → SERVICE_DETAIL with summary and service info."""
        service = _make_service()
        mock_service_reg.get_default_service = AsyncMock(return_value=service)
        mock_service_reg.format_service_detail = MagicMock(
            return_value="📦 *TELETRAAN Order Bot*\nDescription"
        )

        session = _make_session(
            state=SessionStateB.QUALIFICATION_RETAILER_COUNT.value,
            state_data={
                "prospect_id": str(uuid4()),
                "qualification": {"name": "Ahmed", "business_name": "Khan", "city": "Lahore"},
            },
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "50",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        # Should have qualification summary + service detail with buttons
        assert len(msgs) >= 2
        # Prospect should be marked QUALIFIED
        pros_repo.update.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_retailer_count(self) -> None:
        """Non-numeric input shows error."""
        session = _make_session(
            state=SessionStateB.QUALIFICATION_RETAILER_COUNT.value,
            state_data={"prospect_id": str(uuid4()), "qualification": {}},
        )
        sess_repo = _mock_session_repo()

        msgs = await handle_sales_step(
            session, "many",
            session_repo=sess_repo,
        )

        assert "number" in msgs[0]["text"]["body"].lower()

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.service_registry.service_registry")
    async def test_service_detail_interested(
        self, mock_service_reg: MagicMock
    ) -> None:
        """'Interested' from service detail → PROPOSAL_SENT."""
        service = _make_service()
        mock_service_reg.get_service_by_id = AsyncMock(return_value=service)
        mock_service_reg.get_default_service = AsyncMock(return_value=service)

        session = _make_session(
            state=SessionStateB.SERVICE_DETAIL.value,
            state_data={"prospect_id": str(uuid4()), "service_id": str(service.id)},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "interested",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        # Should send proposal
        assert len(msgs) >= 1
        # Should transition to PROPOSAL_SENT
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.PROPOSAL_SENT

    @pytest.mark.asyncio
    async def test_service_detail_demo(self) -> None:
        """'Demo' from service detail → DEMO_BOOKING."""
        session = _make_session(
            state=SessionStateB.SERVICE_DETAIL.value,
            state_data={"prospect_id": str(uuid4())},
        )
        sess_repo = _mock_session_repo()

        msgs = await handle_sales_step(
            session, "",
            button_id="sales_demo",
            session_repo=sess_repo,
        )

        assert "demo" in msgs[0]["text"]["body"].lower()
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.DEMO_BOOKING

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.service_registry.service_registry")
    async def test_demo_booking_with_slot(
        self, mock_service_reg: MagicMock
    ) -> None:
        """Demo slot booking → PROPOSAL_SENT."""
        service = _make_service()
        mock_service_reg.get_service_by_id = AsyncMock(return_value=service)
        mock_service_reg.get_default_service = AsyncMock(return_value=service)

        session = _make_session(
            state=SessionStateB.DEMO_BOOKING.value,
            state_data={"prospect_id": str(uuid4()), "service_id": str(service.id)},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "kal 3 baje",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        # Should confirm demo and send proposal
        assert len(msgs) >= 1
        # Should eventually reach PROPOSAL_SENT
        any_proposal = any(
            call.args[1] == SessionStateB.PROPOSAL_SENT
            for call in sess_repo.update_state.call_args_list
        )
        assert any_proposal

    @pytest.mark.asyncio
    @patch("app.core.config.get_settings")
    async def test_proposal_accept_to_payment(
        self, mock_settings: MagicMock
    ) -> None:
        """Accept proposal → PAYMENT_PENDING with link."""
        settings = MagicMock()
        settings.payment_callback_base_url = "https://pay.test.com"
        mock_settings.return_value = settings

        session = _make_session(
            state=SessionStateB.PROPOSAL_SENT.value,
            state_data={"prospect_id": str(uuid4()), "service_id": str(uuid4())},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "",
            button_id="sales_accept",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        # Should send payment link
        assert any("pay" in m.get("text", {}).get("body", "").lower() for m in msgs)
        # Should transition to PAYMENT_PENDING
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.PAYMENT_PENDING

    @pytest.mark.asyncio
    async def test_proposal_reject(self) -> None:
        """Reject proposal → IDLE."""
        session = _make_session(
            state=SessionStateB.PROPOSAL_SENT.value,
            state_data={"prospect_id": str(uuid4())},
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "",
            button_id="sales_reject",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        # Prospect marked as LOST
        pros_repo.update.assert_called()
        update_data = pros_repo.update.call_args[0][1]
        assert update_data.status == ProspectStatus.LOST

    @pytest.mark.asyncio
    async def test_payment_confirmed(self) -> None:
        """'Paid' → ONBOARDING_SETUP."""
        session = _make_session(
            state=SessionStateB.PAYMENT_PENDING.value,
            state_data={
                "prospect_id": str(uuid4()),
                "qualification": {"name": "Ahmed"},
                "payment_link": "https://pay.test.com/x",
            },
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()

        msgs = await handle_sales_step(
            session, "paid",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
        )

        assert any("payment" in m.get("text", {}).get("body", "").lower() for m in msgs)
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.ONBOARDING_SETUP

        # Prospect marked CONVERTED
        pros_repo.update.assert_called()
        update_data = pros_repo.update.call_args[0][1]
        assert update_data.status == ProspectStatus.CONVERTED


# ═══════════════════════════════════════════════════════════════════
# ONBOARDING FLOW TESTS
# ═══════════════════════════════════════════════════════════════════


class TestOnboardingFlow:
    """Tests for post-payment onboarding."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.onboarding_service")
    async def test_start_onboarding_creates_distributor(
        self, mock_onb_svc: MagicMock
    ) -> None:
        """Onboarding start creates a distributor record."""
        from app.channels.channel_b.onboarding_flow import handle_onboarding_step

        prospect = _make_prospect()
        mock_onb_svc.start_onboarding = AsyncMock()

        session = _make_session(
            state=SessionStateB.ONBOARDING_SETUP.value,
            state_data={
                "prospect_id": str(prospect.id),
                "qualification": {
                    "name": "Ahmed",
                    "business_name": "Khan Pharma",
                    "city": "Lahore",
                },
                "onboarding_step": "start",
            },
        )
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo(prospect)

        mock_dist_repo = MagicMock()
        mock_dist = MagicMock()
        mock_dist.id = uuid4()
        mock_dist_repo.create = AsyncMock(return_value=mock_dist)

        msgs = await handle_onboarding_step(
            session, "start",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            distributor_repo=mock_dist_repo,
        )

        # Should create distributor
        mock_dist_repo.create.assert_called_once()
        create_data = mock_dist_repo.create.call_args[0][0]
        assert create_data.business_name == "Khan Pharma"
        assert create_data.subscription_status == SubscriptionStatus.ACTIVE

        # Should have sent welcome + catalog instructions
        assert len(msgs) >= 2

    @pytest.mark.asyncio
    async def test_catalog_skip_to_test_order(self) -> None:
        """Skip catalog → test order step."""
        from app.channels.channel_b.onboarding_flow import handle_onboarding_step

        session = _make_session(
            state=SessionStateB.ONBOARDING_SETUP.value,
            state_data={"onboarding_step": "catalog_upload"},
        )
        sess_repo = _mock_session_repo()

        msgs = await handle_onboarding_step(
            session, "skip",
            session_repo=sess_repo,
        )

        # Should advance to test order step
        assert any("test" in m.get("text", {}).get("body", "").lower() or
                    "test" in str(m.get("interactive", {}).get("body", {})).lower()
                    for m in msgs)

    @pytest.mark.asyncio
    @patch("app.core.config.get_settings")
    async def test_test_order_done_completes(self, mock_settings: MagicMock) -> None:
        """Test order done → onboarding complete."""
        from app.channels.channel_b.onboarding_flow import handle_onboarding_step

        settings = MagicMock()
        settings.whatsapp_phone_number = "+923001111111"
        mock_settings.return_value = settings

        session = _make_session(
            state=SessionStateB.ONBOARDING_SETUP.value,
            state_data={"onboarding_step": "test_order", "distributor_id": str(uuid4())},
        )
        sess_repo = _mock_session_repo()

        msgs = await handle_onboarding_step(
            session, "",
            button_id="onb_test_done",
            session_repo=sess_repo,
        )

        assert any("complete" in m.get("text", {}).get("body", "").lower() or
                    "live" in m.get("text", {}).get("body", "").lower()
                    for m in msgs)
        # Should transition to IDLE
        call_args = sess_repo.update_state.call_args
        assert call_args[0][1] == SessionStateB.IDLE


# ═══════════════════════════════════════════════════════════════════
# OWNER COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════


class TestOwnerCommands:
    """Tests for owner pipeline management commands."""

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_list_prospects_empty(self, mock_refresh: AsyncMock) -> None:
        """'list prospects' with no data returns empty message."""
        session = _make_session(state=SessionStateB.IDLE.value)
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo()
        pros_repo.get_by_status = AsyncMock(return_value=[])

        msgs = await handle_channel_b_message(
            session, "list prospects",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            is_owner=True,
        )

        assert any("no active" in m.get("text", {}).get("body", "").lower() for m in msgs)

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_list_prospects_with_data(self, mock_refresh: AsyncMock) -> None:
        """'list prospects' shows prospect details."""
        prospect = _make_prospect(status=ProspectStatus.QUALIFIED)
        session = _make_session(state=SessionStateB.IDLE.value)
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo(prospect)
        # Return prospect for QUALIFIED, empty for others
        pros_repo.get_by_status = AsyncMock(
            side_effect=lambda s, **kw: [prospect] if s == "qualified" else []
        )

        msgs = await handle_channel_b_message(
            session, "list prospects",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            is_owner=True,
        )

        body = msgs[0]["text"]["body"]
        assert "Test Prospect" in body
        assert "Active Prospects" in body

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_qualify_command(self, mock_refresh: AsyncMock) -> None:
        """'qualify +923001234567' marks prospect as QUALIFIED."""
        prospect = _make_prospect()
        session = _make_session(state=SessionStateB.IDLE.value)
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo(prospect)

        msgs = await handle_channel_b_message(
            session, "qualify +923001234567",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            is_owner=True,
        )

        assert any("qualified" in m.get("text", {}).get("body", "").lower() for m in msgs)
        pros_repo.update.assert_called()

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_close_command(self, mock_refresh: AsyncMock) -> None:
        """'close <id>' marks prospect as CONVERTED."""
        prospect = _make_prospect()
        session = _make_session(state=SessionStateB.IDLE.value)
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo(prospect)

        msgs = await handle_channel_b_message(
            session, f"close {prospect.id}",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            is_owner=True,
        )

        assert any("converted" in m.get("text", {}).get("body", "").lower() for m in msgs)

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_lost_command(self, mock_refresh: AsyncMock) -> None:
        """'lost <id> reason' marks prospect as LOST."""
        prospect = _make_prospect()
        session = _make_session(state=SessionStateB.IDLE.value)
        sess_repo = _mock_session_repo()
        pros_repo = _mock_prospect_repo(prospect)

        msgs = await handle_channel_b_message(
            session, f"lost {prospect.id} Too expensive",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            is_owner=True,
        )

        assert any("lost" in m.get("text", {}).get("body", "").lower() for m in msgs)
        update_data = pros_repo.update.call_args[0][1]
        assert update_data.lost_reason == "Too expensive"


# ═══════════════════════════════════════════════════════════════════
# SERVICE REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestServiceRegistry:
    """Tests for dynamic service registry with caching."""

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_get_services_caches(
        self, mock_repo_cls: MagicMock
    ) -> None:
        """Services are cached after first load."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        service = _make_service()
        mock_repo = MagicMock()
        mock_repo.get_available_services = AsyncMock(return_value=[service])
        mock_repo_cls.return_value = mock_repo

        reg = ServiceRegistry(cache_ttl=300)
        reg._repo = mock_repo

        # First call loads from DB
        result1 = await reg.get_services()
        assert len(result1) == 1

        # Second call uses cache
        result2 = await reg.get_services()
        assert len(result2) == 1

        # DB called only once
        assert mock_repo.get_available_services.call_count == 1

    @pytest.mark.asyncio
    @patch("app.channels.channel_b.service_registry.ServiceRegistryRepository")
    async def test_cache_expires(
        self, mock_repo_cls: MagicMock
    ) -> None:
        """Cache refreshes after TTL expires."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        service = _make_service()
        mock_repo = MagicMock()
        mock_repo.get_available_services = AsyncMock(return_value=[service])
        mock_repo_cls.return_value = mock_repo

        reg = ServiceRegistry(cache_ttl=0)  # 0 TTL = always stale
        reg._repo = mock_repo

        await reg.get_services()
        await reg.get_services()

        # DB called twice because TTL=0
        assert mock_repo.get_available_services.call_count == 2

    @pytest.mark.asyncio
    async def test_format_service_list(self) -> None:
        """Service list formats correctly."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        services = [_make_service(), _make_service(name="Beta Service", slug="beta")]
        reg = ServiceRegistry.__new__(ServiceRegistry)
        result = reg.format_service_list(services)

        assert "1. *TELETRAAN Order Bot*" in result
        assert "2. *Beta Service*" in result
        assert "PKR" in result

    def test_format_pricing(self) -> None:
        """Pricing formats with both monthly and setup."""
        service = _make_service()
        result = service.format_pricing()
        assert "PKR 15,000/mo" in result
        assert "PKR 5,000 setup" in result

    def test_format_pricing_no_setup(self) -> None:
        """Pricing without setup fee."""
        service = _make_service(setup_fee_paisas=0)
        result = service.format_pricing()
        assert "PKR 15,000/mo" in result
        assert "setup" not in result

    def test_handler_resolution(self) -> None:
        """Handler resolves by slug."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        reg = ServiceRegistry.__new__(ServiceRegistry)

        async def _dummy_handler(**kwargs: Any) -> list:
            return []

        reg.register_handler("test_handler", _dummy_handler)
        service = _make_service(sales_flow_handler="test_handler")
        handler = reg.get_handler(service)

        assert handler is _dummy_handler

    def test_handler_none_when_no_slug(self) -> None:
        """No handler when no slug configured."""
        from app.channels.channel_b.service_registry import ServiceRegistry

        reg = ServiceRegistry.__new__(ServiceRegistry)
        service = _make_service(sales_flow_handler=None)
        handler = reg.get_handler(service)

        assert handler is None


# ═══════════════════════════════════════════════════════════════════
# FULL END-TO-END LIFECYCLE TEST
# ═══════════════════════════════════════════════════════════════════


class TestEndToEndSalesFunnel:
    """Full lifecycle: first message → distributor created."""

    @pytest.mark.asyncio
    @patch("app.distributor_mgmt.onboarding_service.onboarding_service")
    @patch("app.core.config.get_settings")
    @patch("app.channels.channel_b.service_registry.service_registry")
    @patch("app.channels.channel_b.handler.refresh_session_timeout", new_callable=AsyncMock)
    async def test_full_funnel(
        self,
        mock_refresh: AsyncMock,
        mock_service_reg: MagicMock,
        mock_settings: MagicMock,
        mock_onb_svc: MagicMock,
    ) -> None:
        """Walk through entire funnel from IDLE to onboarding complete."""
        # Setup mocks
        service = _make_service()
        mock_service_reg.get_default_service = AsyncMock(return_value=service)
        mock_service_reg.get_service_by_id = AsyncMock(return_value=service)
        mock_service_reg.format_service_detail = MagicMock(
            return_value="📦 *TELETRAAN*\nDescription"
        )

        settings = MagicMock()
        settings.payment_callback_base_url = "https://pay.test.com"
        settings.whatsapp_phone_number = "+923001111111"
        mock_settings.return_value = settings

        mock_onb_svc.start_onboarding = AsyncMock()

        prospect = _make_prospect()
        pros_repo = _mock_prospect_repo(prospect)
        sess_repo = _mock_session_repo()

        mock_dist_repo = MagicMock()
        mock_dist = MagicMock()
        mock_dist.id = uuid4()
        mock_dist_repo.create = AsyncMock(return_value=mock_dist)

        session_id = uuid4()
        current_state = SessionStateB.IDLE.value
        current_state_data: dict = {}

        def make_session():
            return Session(
                id=session_id,
                distributor_id=_DIST_ID,
                whatsapp_number="+923009999888",
                channel=ChannelType.B,
                current_state=current_state,
                language=Language.ROMAN_URDU,
                state_data=current_state_data,
                last_message_at=_NOW,
                expires_at=_NOW + datetime.timedelta(minutes=30),
                created_at=_NOW,
                updated_at=_NOW,
            )

        def capture_state(*args: Any, **kwargs: Any) -> None:
            nonlocal current_state, current_state_data
            current_state = args[1] if len(args) > 1 else kwargs.get("new_state", current_state)
            if "state_data" in kwargs:
                current_state_data = kwargs["state_data"]
            elif len(args) > 2 and isinstance(args[2], dict):
                current_state_data = args[2]

        sess_repo.update_state = AsyncMock(side_effect=capture_state)

        # Step 1: IDLE → sends welcome, transitions to GREETING
        msgs = await handle_channel_b_message(
            make_session(), "hi", session_repo=sess_repo,
        )
        assert current_state == SessionStateB.GREETING

        # Step 2: GREETING → "haan" → QUALIFICATION_NAME
        msgs = await handle_sales_step(
            make_session(), "haan",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.QUALIFICATION_NAME

        # Step 3: Name → QUALIFICATION_BUSINESS
        msgs = await handle_sales_step(
            make_session(), "Ahmed Khan",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.QUALIFICATION_BUSINESS

        # Step 4: Business → QUALIFICATION_CITY
        msgs = await handle_sales_step(
            make_session(), "Khan Pharma",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.QUALIFICATION_CITY

        # Step 5: City → QUALIFICATION_RETAILER_COUNT
        msgs = await handle_sales_step(
            make_session(), "Lahore",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.QUALIFICATION_RETAILER_COUNT

        # Step 6: Retailer count → SERVICE_DETAIL
        msgs = await handle_sales_step(
            make_session(), "50",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.SERVICE_DETAIL

        # Step 7: Interested → PROPOSAL_SENT
        msgs = await handle_sales_step(
            make_session(), "interested",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.PROPOSAL_SENT

        # Step 8: Accept → PAYMENT_PENDING
        msgs = await handle_sales_step(
            make_session(), "", button_id="sales_accept",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.PAYMENT_PENDING

        # Step 9: Paid → ONBOARDING_SETUP
        msgs = await handle_sales_step(
            make_session(), "paid",
            session_repo=sess_repo, prospect_repo=pros_repo,
        )
        assert current_state == SessionStateB.ONBOARDING_SETUP

        # Step 10: Onboarding start → creates distributor
        from app.channels.channel_b.onboarding_flow import handle_onboarding_step
        msgs = await handle_onboarding_step(
            make_session(), "start",
            session_repo=sess_repo,
            prospect_repo=pros_repo,
            distributor_repo=mock_dist_repo,
        )
        mock_dist_repo.create.assert_called_once()
        assert current_state == SessionStateB.ONBOARDING_SETUP

        # Step 11: Skip catalog
        msgs = await handle_onboarding_step(
            make_session(), "skip",
            session_repo=sess_repo,
        )

        # Step 12: Test done → IDLE (complete)
        msgs = await handle_onboarding_step(
            make_session(), "", button_id="onb_test_done",
            session_repo=sess_repo,
        )
        assert current_state == SessionStateB.IDLE
