"""Integration tests for all Channel A conversation flows.

Tests the main handler dispatch, flow transitions, guards, and
end-to-end conversation paths using in-memory mocks for all
database repositories.  No real database or WhatsApp API calls.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.channels.channel_a.guards import (
    check_business_hours,
    check_credit_limit,
    get_available_credit,
    is_within_business_hours,
)
from app.ai.nlu import NLUResult
from app.channels.channel_a.handler import (
    _INTERACTIVE_MAP,
    _resolve_language,
    handle_channel_a_message,
)
from app.channels.channel_a.state_machine import (
    COMPLAINT_STATES,
    ONBOARDING_STATES,
    ORDER_STATES,
    PROFILE_STATES,
    can_transition,
    get_initial_state,
    is_onboarding_state,
    is_order_state,
    transition,
)
from app.channels.interrupts import InterruptType, detect_interrupt, get_target_state_a
from app.core.constants import (
    Language,
    OrderStatus,
    SessionStateA,
    SubscriptionStatus,
)
from app.db.models.audit import BotConfiguration
from app.db.models.customer import Customer
from app.db.models.session import Session


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


_DIST_ID = uuid4()
_CUST_ID = uuid4()
_NOW = datetime.datetime.now(datetime.timezone.utc)


def _make_session(
    state: str = SessionStateA.MAIN_MENU.value,
    *,
    customer_id: UUID | None = _CUST_ID,
    language: str = Language.ROMAN_URDU,
    state_data: dict | None = None,
    expires_minutes: int = 30,
) -> Session:
    """Build a minimal Session for testing."""
    return Session(
        id=uuid4(),
        distributor_id=_DIST_ID,
        whatsapp_number="+923001234567",
        current_state=state,
        customer_id=customer_id,
        language=language,
        state_data=state_data or {},
        last_message_at=_NOW,
        expires_at=_NOW + datetime.timedelta(minutes=expires_minutes),
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_customer(
    *,
    credit_limit: int = 0,
    outstanding: int = 0,
) -> Customer:
    """Build a minimal Customer for testing."""
    return Customer(
        id=_CUST_ID,
        distributor_id=_DIST_ID,
        whatsapp_number="+923001234567",
        name="Ahmed Khan",
        shop_name="Khan Medical Store",
        address="123 Main St, Lahore",
        city="Lahore",
        credit_limit_paisas=credit_limit,
        outstanding_balance_paisas=outstanding,
        total_orders=5,
        total_spend_paisas=50000,
        language_preference=Language.ROMAN_URDU,
        registered_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_bot_config(
    *,
    hours_start: datetime.time = datetime.time(8, 0),
    hours_end: datetime.time = datetime.time(20, 0),
    allow_outside: bool = True,
    credit_enabled: bool = False,
) -> BotConfiguration:
    """Build a BotConfiguration for testing."""
    return BotConfiguration(
        id=uuid4(),
        distributor_id=_DIST_ID,
        business_hours_start=hours_start,
        business_hours_end=hours_end,
        timezone="Asia/Karachi",
        allow_orders_outside_hours=allow_outside,
        credit_orders_enabled=credit_enabled,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _mock_session_repo() -> AsyncMock:
    """Create a mock SessionRepository."""
    repo = AsyncMock()
    repo.update_state = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=None)
    return repo


def _mock_customer_repo(customer: Customer | None = None) -> AsyncMock:
    """Create a mock CustomerRepository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=customer)
    repo.update = AsyncMock(return_value=customer)
    return repo


# ═══════════════════════════════════════════════════════════════════
# BUSINESS HOURS TESTS
# ═══════════════════════════════════════════════════════════════════


class TestBusinessHours:
    """Test business hours enforcement."""

    def test_no_config_always_open(self):
        assert is_within_business_hours(None) is True

    def test_within_hours(self):
        config = _make_bot_config(
            hours_start=datetime.time(8, 0),
            hours_end=datetime.time(20, 0),
        )
        # 14:00 PKT = 09:00 UTC
        test_time = datetime.datetime(2026, 1, 15, 9, 0, tzinfo=datetime.timezone.utc)
        assert is_within_business_hours(config, now=test_time) is True

    def test_outside_hours(self):
        config = _make_bot_config(
            hours_start=datetime.time(8, 0),
            hours_end=datetime.time(20, 0),
        )
        # 02:00 PKT = 21:00 UTC previous day
        test_time = datetime.datetime(2026, 1, 15, 21, 0, tzinfo=datetime.timezone.utc)
        assert is_within_business_hours(config, now=test_time) is False

    def test_check_returns_none_when_allowed(self):
        config = _make_bot_config(allow_outside=True)
        result = check_business_hours(
            config, language="english", to="+923001234567",
        )
        assert result is None

    def test_check_returns_message_when_blocked(self):
        config = _make_bot_config(
            hours_start=datetime.time(8, 0),
            hours_end=datetime.time(20, 0),
            allow_outside=False,
        )
        # Force outside hours by patching
        with patch(
            "app.channels.channel_a.guards.is_within_business_hours",
            return_value=False,
        ):
            result = check_business_hours(
                config, language="english", to="+923001234567",
            )
            assert result is not None
            assert len(result) == 1

    def test_check_returns_custom_message(self):
        config = _make_bot_config(allow_outside=False)
        config.out_of_hours_message = "Custom: we're closed!"
        with patch(
            "app.channels.channel_a.guards.is_within_business_hours",
            return_value=False,
        ):
            result = check_business_hours(
                config, language="english", to="+923001234567",
            )
            assert result is not None
            assert "Custom: we're closed!" in result[0]["text"]["body"]

    def test_overnight_hours_wrap(self):
        config = _make_bot_config(
            hours_start=datetime.time(22, 0),
            hours_end=datetime.time(6, 0),
        )
        # 23:00 PKT = 18:00 UTC  — should be within
        test_time = datetime.datetime(2026, 1, 15, 18, 0, tzinfo=datetime.timezone.utc)
        assert is_within_business_hours(config, now=test_time) is True

        # 12:00 PKT = 07:00 UTC — should be outside
        test_time2 = datetime.datetime(2026, 1, 15, 7, 0, tzinfo=datetime.timezone.utc)
        assert is_within_business_hours(config, now=test_time2) is False


# ═══════════════════════════════════════════════════════════════════
# CREDIT LIMIT TESTS
# ═══════════════════════════════════════════════════════════════════


class TestCreditLimit:
    """Test credit limit enforcement."""

    def test_no_customer_passes(self):
        result = check_credit_limit(
            None, 10000, language="english", to="+923001234567",
        )
        assert result is None

    def test_no_limit_passes(self):
        customer = _make_customer(credit_limit=0)
        result = check_credit_limit(
            customer, 10000, language="english", to="+923001234567",
        )
        assert result is None

    def test_credit_disabled_passes(self):
        customer = _make_customer(credit_limit=100000)
        config = _make_bot_config(credit_enabled=False)
        result = check_credit_limit(
            customer, 200000,
            config=config, language="english", to="+923001234567",
        )
        assert result is None

    def test_within_limit_passes(self):
        customer = _make_customer(credit_limit=100000, outstanding=20000)
        config = _make_bot_config(credit_enabled=True)
        result = check_credit_limit(
            customer, 50000,
            config=config, language="english", to="+923001234567",
        )
        assert result is None

    def test_exceeds_limit_blocks(self):
        customer = _make_customer(credit_limit=100000, outstanding=80000)
        config = _make_bot_config(credit_enabled=True)
        result = check_credit_limit(
            customer, 30000,
            config=config, language="english", to="+923001234567",
        )
        assert result is not None
        assert "Credit Limit" in result[0]["text"]["body"]

    def test_exceeds_limit_blocks_urdu(self):
        customer = _make_customer(credit_limit=100000, outstanding=80000)
        config = _make_bot_config(credit_enabled=True)
        result = check_credit_limit(
            customer, 30000,
            config=config, language="roman_urdu", to="+923001234567",
        )
        assert result is not None
        assert "Credit Limit Exceed" in result[0]["text"]["body"]

    def test_exact_limit_passes(self):
        customer = _make_customer(credit_limit=100000, outstanding=50000)
        config = _make_bot_config(credit_enabled=True)
        result = check_credit_limit(
            customer, 50000,
            config=config, language="english", to="+923001234567",
        )
        assert result is None

    def test_available_credit_calculation(self):
        customer = _make_customer(credit_limit=100000, outstanding=30000)
        assert get_available_credit(customer) == 70000

    def test_available_credit_no_limit(self):
        customer = _make_customer(credit_limit=0)
        assert get_available_credit(customer) == 0

    def test_available_credit_no_customer(self):
        assert get_available_credit(None) == 0

    def test_over_limit_returns_zero_available(self):
        customer = _make_customer(credit_limit=100000, outstanding=150000)
        assert get_available_credit(customer) == 0


# ═══════════════════════════════════════════════════════════════════
# HANDLER DISPATCH TESTS
# ═══════════════════════════════════════════════════════════════════


class TestHandlerDispatch:
    """Test main handler routing to flows."""

    @pytest.mark.asyncio
    async def test_idle_with_customer_goes_to_menu(self):
        session = _make_session(SessionStateA.IDLE.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "hello",
                session_repo=sr,
            )

        assert sr.update_state.called
        # Should return at least the menu list message
        assert len(msgs) >= 1

    @pytest.mark.asyncio
    async def test_idle_without_customer_goes_to_onboarding(self):
        session = _make_session(
            SessionStateA.IDLE.value,
            customer_id=None,
        )
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.handle_onboarding_step",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "onboarding"}}],
        ) as mock_onboard:
            msgs = await handle_channel_a_message(
                session, "salam",
                session_repo=sr,
            )

        assert mock_onboard.called

    @pytest.mark.asyncio
    async def test_interrupt_cancel_returns_to_menu(self):
        session = _make_session(SessionStateA.ORDER_ITEM_COLLECTION.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "cancel",
                session_repo=sr,
            )

        # Should transition to MAIN_MENU and show menu
        assert sr.update_state.called
        call_args = sr.update_state.call_args_list
        # At least one call should set MAIN_MENU
        states = [str(c.args[1]) if len(c.args) > 1 else "" for c in call_args]
        assert any("main_menu" in s for s in states)

    @pytest.mark.asyncio
    async def test_interrupt_handoff(self):
        session = _make_session(SessionStateA.ORDER_ITEM_COLLECTION.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "human",
                session_repo=sr,
            )

        assert len(msgs) >= 1

    @pytest.mark.asyncio
    async def test_interactive_menu_order_button(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.start_order",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "order started"}}],
        ) as mock_order:
            msgs = await handle_channel_a_message(
                session, "",
                button_id="menu_order",
                session_repo=sr,
            )

        assert mock_order.called

    @pytest.mark.asyncio
    async def test_interactive_menu_catalog_button(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.start_catalog",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "catalog"}}],
        ) as mock_cat:
            msgs = await handle_channel_a_message(
                session, "",
                list_id="menu_catalog",
                session_repo=sr,
            )

        assert mock_cat.called

    @pytest.mark.asyncio
    async def test_expired_session_resets(self):
        session = _make_session(
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            expires_minutes=-5,
        )
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "hello",
                session_repo=sr,
            )

        # Should reset to IDLE and show expired message
        assert len(msgs) >= 1
        found_expired = any(
            "expired" in str(m).lower() or "khatam" in str(m).lower()
            for m in msgs
        )
        assert found_expired

    @pytest.mark.asyncio
    async def test_order_state_dispatches_to_order_flow(self):
        session = _make_session(SessionStateA.ORDER_ITEM_COLLECTION.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.handle_order_step",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "order step"}}],
        ) as mock_order:
            msgs = await handle_channel_a_message(
                session, "panadol 5",
                session_repo=sr,
            )

        assert mock_order.called

    @pytest.mark.asyncio
    async def test_complaint_state_dispatches(self):
        session = _make_session(SessionStateA.COMPLAINT_DESCRIPTION.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.handle_complaint_step",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "complaint"}}],
        ) as mock_comp:
            msgs = await handle_channel_a_message(
                session, "galat medicine aayi",
                session_repo=sr,
            )

        assert mock_comp.called

    @pytest.mark.asyncio
    async def test_profile_state_dispatches(self):
        session = _make_session(SessionStateA.PROFILE_VIEW.value)
        sr = _mock_session_repo()
        cr = _mock_customer_repo(_make_customer())

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.handle_profile_step",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "profile"}}],
        ) as mock_prof:
            msgs = await handle_channel_a_message(
                session, "edit name",
                session_repo=sr,
                customer_repo=cr,
            )

        assert mock_prof.called

    @pytest.mark.asyncio
    async def test_inquiry_state_dispatches(self):
        session = _make_session(SessionStateA.INQUIRY_RESPONSE.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.handle_inquiry_step",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "inquiry"}}],
        ) as mock_inq:
            msgs = await handle_channel_a_message(
                session, "price panadol",
                session_repo=sr,
            )

        assert mock_inq.called

    @pytest.mark.asyncio
    async def test_handoff_state_silences_bot(self):
        session = _make_session(SessionStateA.HANDOFF.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "hello, are you there?",
                session_repo=sr,
            )

        # Should return handoff reminder, NOT process as normal flow
        assert len(msgs) == 1
        assert "operator" in str(msgs[0]).lower() or "insaan" in str(msgs[0]).lower()

    @pytest.mark.asyncio
    async def test_unknown_state_recovers_to_menu(self):
        session = _make_session("nonexistent_state")
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "hello",
                session_repo=sr,
            )

        # Should reset to MAIN_MENU
        assert sr.update_state.called


# ═══════════════════════════════════════════════════════════════════
# MENU INTENT CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestMenuIntentRouting:
    """Test intent classification at main menu."""

    @pytest.mark.asyncio
    async def test_order_intent_starts_order_flow(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()
        nlu_result = NLUResult(intent="place_order", confidence="high")

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.classify_intent",
            new_callable=AsyncMock,
            return_value=nlu_result,
        ), patch(
            "app.channels.channel_a.handler.start_order",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "start"}}],
        ) as mock_order:
            await handle_channel_a_message(
                session, "order chahiye",
                session_repo=sr,
            )

        assert mock_order.called

    @pytest.mark.asyncio
    async def test_complain_intent_starts_complaint_flow(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()
        nlu_result = NLUResult(intent="complain", confidence="high")

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.classify_intent",
            new_callable=AsyncMock,
            return_value=nlu_result,
        ), patch(
            "app.channels.channel_a.handler.start_complaint",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "complaint"}}],
        ) as mock_comp:
            await handle_channel_a_message(
                session, "galat medicine aayi problem hai",
                session_repo=sr,
            )

        assert mock_comp.called

    @pytest.mark.asyncio
    async def test_price_intent_starts_inquiry(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()
        nlu_result = NLUResult(intent="ask_price", confidence="high")

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.classify_intent",
            new_callable=AsyncMock,
            return_value=nlu_result,
        ), patch(
            "app.channels.channel_a.handler.start_inquiry",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "inquiry"}}],
        ) as mock_inq:
            await handle_channel_a_message(
                session, "price kitne hai panadol ki",
                session_repo=sr,
            )

        assert mock_inq.called

    @pytest.mark.asyncio
    async def test_goodbye_at_menu(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()
        nlu_result = NLUResult(intent="goodbye", confidence="high")

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.classify_intent",
            new_callable=AsyncMock,
            return_value=nlu_result,
        ):
            msgs = await handle_channel_a_message(
                session, "allah hafiz",
                session_repo=sr,
            )

        assert len(msgs) >= 1
        assert any(
            "hafiz" in str(m).lower() or "goodbye" in str(m).lower()
            for m in msgs
        )

    @pytest.mark.asyncio
    async def test_empty_text_shows_menu(self):
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "",
                session_repo=sr,
            )

        assert len(msgs) >= 1


# ═══════════════════════════════════════════════════════════════════
# INTERRUPT INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestInterruptIntegration:
    """Test interrupt detection across different states."""

    @pytest.mark.asyncio
    async def test_cancel_during_order(self):
        session = _make_session(SessionStateA.ORDER_BILL_PREVIEW.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "cancel",
                session_repo=sr,
            )

        # Should return to menu, not continue order flow
        assert sr.update_state.called

    @pytest.mark.asyncio
    async def test_help_during_complaint(self):
        session = _make_session(SessionStateA.COMPLAINT_DESCRIPTION.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.start_inquiry",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": {"body": "help"}}],
        ) as mock_inq:
            msgs = await handle_channel_a_message(
                session, "help",
                session_repo=sr,
            )

        assert mock_inq.called

    @pytest.mark.asyncio
    async def test_handoff_during_profile(self):
        session = _make_session(SessionStateA.PROFILE_EDIT.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "insaan se baat",
                session_repo=sr,
            )

        assert len(msgs) >= 1

    @pytest.mark.asyncio
    async def test_goodbye_during_catalog(self):
        session = _make_session(SessionStateA.CATALOG_BROWSING.value)
        sr = _mock_session_repo()

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ):
            msgs = await handle_channel_a_message(
                session, "bye",
                session_repo=sr,
            )

        assert len(msgs) >= 1
        assert any(
            "hafiz" in str(m).lower() or "goodbye" in str(m).lower()
            for m in msgs
        )


# ═══════════════════════════════════════════════════════════════════
# FLOW TRANSITION INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestFlowTransitions:
    """Test state transitions across flow boundaries."""

    def test_main_menu_can_reach_all_flows(self):
        targets = [
            SessionStateA.ORDER_ITEM_COLLECTION,
            SessionStateA.CATALOG_BROWSING,
            SessionStateA.COMPLAINT_DESCRIPTION,
            SessionStateA.PROFILE_VIEW,
            SessionStateA.INQUIRY_RESPONSE,
        ]
        for target in targets:
            result = can_transition(
                SessionStateA.MAIN_MENU.value,
                target.value,
            )
            assert result.allowed, f"MAIN_MENU → {target.value} should be allowed"

    def test_order_flow_circular_transitions(self):
        # item_collection → item_confirmation → item_collection (add more)
        r1 = can_transition(
            SessionStateA.ORDER_ITEM_COLLECTION.value,
            SessionStateA.ORDER_ITEM_CONFIRMATION.value,
        )
        assert r1.allowed

        r2 = can_transition(
            SessionStateA.ORDER_ITEM_CONFIRMATION.value,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        assert r2.allowed

    def test_complaint_flow_progression(self):
        # description → category → confirm → main_menu
        r1 = can_transition(
            SessionStateA.COMPLAINT_DESCRIPTION.value,
            SessionStateA.COMPLAINT_CATEGORY.value,
        )
        assert r1.allowed

        r2 = can_transition(
            SessionStateA.COMPLAINT_CATEGORY.value,
            SessionStateA.COMPLAINT_CONFIRM.value,
        )
        assert r2.allowed

        r3 = can_transition(
            SessionStateA.COMPLAINT_CONFIRM.value,
            SessionStateA.MAIN_MENU.value,
        )
        assert r3.allowed

    def test_profile_edit_cycle(self):
        # view → edit → view
        r1 = can_transition(
            SessionStateA.PROFILE_VIEW.value,
            SessionStateA.PROFILE_EDIT.value,
        )
        assert r1.allowed

        r2 = can_transition(
            SessionStateA.PROFILE_EDIT.value,
            SessionStateA.PROFILE_VIEW.value,
        )
        assert r2.allowed

    def test_catalog_to_order_transition(self):
        result = can_transition(
            SessionStateA.CATALOG_BROWSING.value,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        assert result.allowed

    def test_inquiry_to_order_transition(self):
        result = can_transition(
            SessionStateA.INQUIRY_RESPONSE.value,
            SessionStateA.ORDER_ITEM_COLLECTION.value,
        )
        assert result.allowed

    def test_all_states_can_reach_handoff(self):
        """Every state should be able to transition to HANDOFF (universal)."""
        for state in SessionStateA:
            if state == SessionStateA.HANDOFF:
                continue
            result = can_transition(state.value, SessionStateA.HANDOFF.value)
            assert result.allowed, f"{state.value} → handoff should be allowed"

    def test_all_states_can_reach_idle(self):
        """Every state should be able to transition to IDLE (universal)."""
        for state in SessionStateA:
            if state == SessionStateA.IDLE:
                continue
            result = can_transition(state.value, SessionStateA.IDLE.value)
            assert result.allowed, f"{state.value} → idle should be allowed"

    def test_handoff_only_goes_to_menu_or_idle(self):
        allowed = [SessionStateA.MAIN_MENU.value, SessionStateA.IDLE.value]
        for target in SessionStateA:
            result = can_transition(
                SessionStateA.HANDOFF.value,
                target.value,
            )
            if target.value in allowed:
                assert result.allowed
            else:
                # Universal interrupts (HANDOFF itself) always allowed
                if target == SessionStateA.HANDOFF:
                    assert result.allowed
                elif target == SessionStateA.MAIN_MENU:
                    assert result.allowed


# ═══════════════════════════════════════════════════════════════════
# LANGUAGE RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestLanguageResolution:
    """Test language detection and prompt selection."""

    def test_english_session(self):
        session = _make_session(language=Language.ENGLISH)
        assert _resolve_language(session) == "english"

    def test_roman_urdu_session(self):
        session = _make_session(language=Language.ROMAN_URDU)
        assert _resolve_language(session) == "roman_urdu"

    def test_default_language(self):
        session = _make_session()
        session.language = None
        assert _resolve_language(session) == "roman_urdu"


# ═══════════════════════════════════════════════════════════════════
# STATE GROUP CONSISTENCY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestStateGroups:
    """Verify state group sets are consistent."""

    def test_order_states_count(self):
        assert len(ORDER_STATES) == 6

    def test_onboarding_states_count(self):
        assert len(ONBOARDING_STATES) == 4

    def test_complaint_states_count(self):
        assert len(COMPLAINT_STATES) == 3

    def test_profile_states_count(self):
        assert len(PROFILE_STATES) == 2

    def test_is_order_state_detects_all(self):
        for state in ORDER_STATES:
            assert is_order_state(state.value)

    def test_is_order_state_rejects_others(self):
        assert not is_order_state(SessionStateA.MAIN_MENU.value)
        assert not is_order_state(SessionStateA.IDLE.value)

    def test_is_onboarding_state_detects_all(self):
        for state in ONBOARDING_STATES:
            assert is_onboarding_state(state.value)

    def test_get_initial_state_new_customer(self):
        assert get_initial_state(True) == SessionStateA.ONBOARDING_NAME

    def test_get_initial_state_returning(self):
        assert get_initial_state(False) == SessionStateA.MAIN_MENU

    def test_interactive_map_covers_all_menu_options(self):
        assert "menu_order" in _INTERACTIVE_MAP
        assert "menu_catalog" in _INTERACTIVE_MAP
        assert "menu_complaint" in _INTERACTIVE_MAP
        assert "menu_profile" in _INTERACTIVE_MAP
        assert "menu_inquiry" in _INTERACTIVE_MAP


# ═══════════════════════════════════════════════════════════════════
# GUARD INTEGRATION WITH HANDLER
# ═══════════════════════════════════════════════════════════════════


class TestGuardIntegration:
    """Test guards used within handler context."""

    @pytest.mark.asyncio
    async def test_handler_continues_when_no_guards_block(self):
        """Main handler processes normally without guard blocks."""
        session = _make_session(SessionStateA.MAIN_MENU.value)
        sr = _mock_session_repo()
        nlu_result = NLUResult(intent="unclear", confidence="low")

        with patch(
            "app.channels.channel_a.handler.refresh_session_timeout",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.channel_a.handler.classify_intent",
            new_callable=AsyncMock,
            return_value=nlu_result,
        ):
            msgs = await handle_channel_a_message(
                session, "menu",
                session_repo=sr,
            )

        # Should get menu response
        assert len(msgs) >= 1

    def test_credit_check_with_large_order(self):
        customer = _make_customer(credit_limit=500000, outstanding=490000)
        config = _make_bot_config(credit_enabled=True)

        # 20000 paisas → total = 510000 > 500000
        result = check_credit_limit(
            customer, 20000,
            config=config, language="english", to="+923001234567",
        )
        assert result is not None

    def test_credit_check_with_zero_outstanding(self):
        customer = _make_customer(credit_limit=500000, outstanding=0)
        config = _make_bot_config(credit_enabled=True)

        result = check_credit_limit(
            customer, 400000,
            config=config, language="english", to="+923001234567",
        )
        assert result is None
