"""Comprehensive unit tests for Channel A and B state machines.

Tests transition validation, universal interrupts, state group
helpers, and initial state selection for both FSMs.
"""

from __future__ import annotations

import pytest

from app.channels.channel_a.state_machine import (
    COMPLAINT_STATES,
    ONBOARDING_STATES,
    ORDER_STATES,
    PROFILE_STATES,
    TransitionResult,
    can_transition,
    get_allowed_transitions,
    get_initial_state,
    is_onboarding_state,
    is_order_state,
    transition,
)
from app.channels.channel_a.state_machine import (
    can_transition as can_transition_a,
)
from app.channels.channel_b.state_machine import (
    QUALIFICATION_STATES,
    SALES_FUNNEL_STATES,
    can_transition as can_transition_b,
    get_allowed_transitions as get_allowed_transitions_b,
    get_initial_state as get_initial_state_b,
    is_qualification_state,
    is_sales_funnel_state,
    transition as transition_b,
)
from app.core.constants import SessionStateA, SessionStateB


# ═══════════════════════════════════════════════════════════════════
# CHANNEL A FSM TESTS
# ═══════════════════════════════════════════════════════════════════


class TestChannelATransitions:
    """Test Channel A state transition validation."""

    def test_idle_to_onboarding(self):
        result = can_transition("idle", "onboarding_name")
        assert result.allowed is True

    def test_idle_to_main_menu(self):
        result = can_transition("idle", "main_menu")
        assert result.allowed is True

    def test_onboarding_flow(self):
        """Test full onboarding sub-flow."""
        assert can_transition("onboarding_name", "onboarding_shop").allowed
        assert can_transition("onboarding_shop", "onboarding_address").allowed
        assert can_transition("onboarding_address", "onboarding_confirm").allowed
        assert can_transition("onboarding_confirm", "main_menu").allowed

    def test_order_flow(self):
        """Test order lifecycle transitions."""
        assert can_transition("main_menu", "order_item_collection").allowed
        assert can_transition("order_item_collection", "order_item_confirmation").allowed
        assert can_transition("order_item_confirmation", "order_bill_preview").allowed
        assert can_transition("order_bill_preview", "order_final_confirmation").allowed

    def test_order_ambiguity_resolution(self):
        assert can_transition(
            "order_item_collection", "order_ambiguity_resolution"
        ).allowed
        assert can_transition(
            "order_ambiguity_resolution", "order_item_collection"
        ).allowed

    def test_order_discount_flow(self):
        assert can_transition("order_bill_preview", "order_discount_request").allowed
        assert can_transition("order_discount_request", "order_bill_preview").allowed
        assert can_transition(
            "order_discount_request", "order_final_confirmation"
        ).allowed

    def test_complaint_flow(self):
        assert can_transition("main_menu", "complaint_description").allowed
        assert can_transition("complaint_description", "complaint_category").allowed
        assert can_transition("complaint_category", "complaint_confirm").allowed
        assert can_transition("complaint_confirm", "main_menu").allowed

    def test_profile_flow(self):
        assert can_transition("main_menu", "profile_view").allowed
        assert can_transition("profile_view", "profile_edit").allowed
        assert can_transition("profile_edit", "profile_view").allowed

    def test_invalid_transition_denied(self):
        """Test that invalid transitions are rejected."""
        result = can_transition("onboarding_name", "order_bill_preview")
        assert result.allowed is False
        assert "not allowed" in result.reason

    def test_invalid_state_names(self):
        result = can_transition("nonexistent", "also_nonexistent")
        assert result.allowed is False
        assert "Invalid state name" in result.reason


class TestChannelAUniversalInterrupts:
    """Test that universal interrupts are reachable from any state."""

    @pytest.mark.parametrize(
        "current",
        [s.value for s in SessionStateA if s != SessionStateA.IDLE],
    )
    def test_can_reach_main_menu(self, current: str):
        result = can_transition(current, "main_menu")
        assert result.allowed is True

    @pytest.mark.parametrize(
        "current",
        [s.value for s in SessionStateA if s != SessionStateA.IDLE],
    )
    def test_can_reach_idle(self, current: str):
        result = can_transition(current, "idle")
        assert result.allowed is True

    @pytest.mark.parametrize(
        "current",
        [s.value for s in SessionStateA if s != SessionStateA.HANDOFF],
    )
    def test_can_reach_handoff(self, current: str):
        result = can_transition(current, "handoff")
        assert result.allowed is True


class TestChannelAHelpers:
    def test_get_allowed_transitions_from_idle(self):
        allowed = get_allowed_transitions("idle")
        assert "main_menu" in allowed
        assert "onboarding_name" in allowed
        assert "handoff" in allowed
        assert "idle" in allowed  # universal

    def test_get_allowed_transitions_invalid(self):
        assert get_allowed_transitions("nonexistent") == []

    def test_is_order_state(self):
        assert is_order_state("order_item_collection") is True
        assert is_order_state("order_bill_preview") is True
        assert is_order_state("main_menu") is False
        assert is_order_state("invalid") is False

    def test_is_onboarding_state(self):
        assert is_onboarding_state("onboarding_name") is True
        assert is_onboarding_state("onboarding_confirm") is True
        assert is_onboarding_state("main_menu") is False

    def test_initial_state_new_customer(self):
        assert get_initial_state(is_new_customer=True) == SessionStateA.ONBOARDING_NAME

    def test_initial_state_returning_customer(self):
        assert get_initial_state(is_new_customer=False) == SessionStateA.MAIN_MENU

    def test_transition_logs_and_returns(self):
        result = transition("idle", "main_menu")
        assert result.allowed is True
        assert result.current_state == SessionStateA.IDLE
        assert result.target_state == SessionStateA.MAIN_MENU

    def test_state_groups_complete(self):
        """Verify state groups match expected membership."""
        assert len(ONBOARDING_STATES) == 4
        assert len(ORDER_STATES) == 6
        assert len(COMPLAINT_STATES) == 3
        assert len(PROFILE_STATES) == 2


# ═══════════════════════════════════════════════════════════════════
# CHANNEL B FSM TESTS
# ═══════════════════════════════════════════════════════════════════


class TestChannelBTransitions:
    """Test Channel B state transition validation."""

    def test_idle_to_greeting(self):
        result = can_transition_b("idle", "greeting")
        assert result.allowed is True

    def test_greeting_flow(self):
        assert can_transition_b("greeting", "service_selection").allowed
        assert can_transition_b("greeting", "qualification_name").allowed

    def test_qualification_flow(self):
        assert can_transition_b("qualification_name", "qualification_business").allowed
        assert can_transition_b("qualification_business", "qualification_city").allowed
        assert can_transition_b(
            "qualification_city", "qualification_retailer_count"
        ).allowed
        assert can_transition_b(
            "qualification_retailer_count", "demo_booking"
        ).allowed

    def test_demo_to_proposal(self):
        assert can_transition_b("demo_booking", "proposal_sent").allowed

    def test_proposal_to_payment(self):
        assert can_transition_b("proposal_sent", "payment_pending").allowed

    def test_payment_to_onboarding(self):
        assert can_transition_b("payment_pending", "onboarding_setup").allowed

    def test_follow_up_flow(self):
        assert can_transition_b("onboarding_setup", "follow_up").allowed
        assert can_transition_b("follow_up", "payment_pending").allowed

    def test_invalid_transition_denied(self):
        result = can_transition_b("idle", "payment_pending")
        assert result.allowed is False

    def test_invalid_state_names(self):
        result = can_transition_b("fake", "also_fake")
        assert result.allowed is False


class TestChannelBUniversalInterrupts:
    """Test that universal interrupts work from any state."""

    @pytest.mark.parametrize(
        "current",
        [s.value for s in SessionStateB if s != SessionStateB.IDLE],
    )
    def test_can_reach_idle(self, current: str):
        result = can_transition_b(current, "idle")
        assert result.allowed is True

    @pytest.mark.parametrize(
        "current",
        [s.value for s in SessionStateB if s != SessionStateB.HANDOFF],
    )
    def test_can_reach_handoff(self, current: str):
        result = can_transition_b(current, "handoff")
        assert result.allowed is True

    @pytest.mark.parametrize(
        "current",
        [s.value for s in SessionStateB if s != SessionStateB.SUPPORT],
    )
    def test_can_reach_support(self, current: str):
        result = can_transition_b(current, "support")
        assert result.allowed is True


class TestChannelBHelpers:
    def test_get_allowed_transitions_from_idle(self):
        allowed = get_allowed_transitions_b("idle")
        assert "greeting" in allowed
        assert "handoff" in allowed
        assert "idle" in allowed  # universal

    def test_is_qualification_state(self):
        assert is_qualification_state("qualification_name") is True
        assert is_qualification_state("qualification_city") is True
        assert is_qualification_state("greeting") is False

    def test_is_sales_funnel_state(self):
        assert is_sales_funnel_state("demo_booking") is True
        assert is_sales_funnel_state("proposal_sent") is True
        assert is_sales_funnel_state("support") is False

    def test_initial_state(self):
        assert get_initial_state_b() == SessionStateB.GREETING

    def test_transition_logs(self):
        result = transition_b("idle", "greeting")
        assert result.allowed is True

    def test_state_groups_complete(self):
        assert len(QUALIFICATION_STATES) == 4
        assert len(SALES_FUNNEL_STATES) == 7
