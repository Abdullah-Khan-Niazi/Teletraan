"""Unit tests for session expiry helpers and interrupt detection."""

from __future__ import annotations

import datetime
from uuid import uuid4

import pytest

from app.channels.interrupts import (
    InterruptType,
    detect_interrupt,
    get_interrupt_response,
    get_target_state_a,
    get_target_state_b,
)
from app.channels.session_expiry import (
    is_session_expired,
    minutes_until_expiry,
    should_warn,
)
from app.core.constants import SessionStateA, SessionStateB
from app.db.models.session import Session


def _make_session(
    expires_at: datetime.datetime,
    current_state: str = "main_menu",
) -> Session:
    """Build a minimal Session for expiry tests."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return Session(
        id=uuid4(),
        distributor_id=uuid4(),
        whatsapp_number="+923001234567",
        current_state=current_state,
        last_message_at=now,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )


# ═══════════════════════════════════════════════════════════════════
# SESSION EXPIRY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSessionExpiry:
    """Test session timeout logic."""

    def test_fresh_session_not_expired(self):
        expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=60,
        )
        session = _make_session(expires_at=expires)
        assert is_session_expired(session) is False

    def test_old_session_expired(self):
        expires = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=1,
        )
        session = _make_session(expires_at=expires)
        assert is_session_expired(session) is True

    def test_exactly_at_boundary(self):
        # Already 1 second past → expired
        expires = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=1,
        )
        session = _make_session(expires_at=expires)
        assert is_session_expired(session) is True

    def test_minutes_until_expiry_fresh(self):
        expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=30,
        )
        session = _make_session(expires_at=expires)
        remaining = minutes_until_expiry(session)
        assert 29.0 <= remaining <= 30.5

    def test_minutes_until_expiry_expired(self):
        expires = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=10,
        )
        session = _make_session(expires_at=expires)
        remaining = minutes_until_expiry(session)
        assert remaining < 0

    def test_should_warn_in_window(self):
        """5 minutes left → should warn (0-10 min remaining window)."""
        expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=5,
        )
        session = _make_session(expires_at=expires)
        assert should_warn(session) is True

    def test_should_not_warn_too_early(self):
        """40 minutes left → no warning yet."""
        expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=40,
        )
        session = _make_session(expires_at=expires)
        assert should_warn(session) is False

    def test_should_not_warn_already_expired(self):
        """Already expired → no warning."""
        expires = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=10,
        )
        session = _make_session(expires_at=expires)
        assert should_warn(session) is False

    def test_should_not_warn_idle_session(self):
        """Idle sessions should not be warned."""
        expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=5,
        )
        session = _make_session(expires_at=expires, current_state="idle")
        assert should_warn(session) is False


# ═══════════════════════════════════════════════════════════════════
# INTERRUPT DETECTION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestInterruptDetection:
    """Test bilingual interrupt keyword detection."""

    def test_cancel_english(self):
        result = detect_interrupt("cancel order")
        assert result == InterruptType.CANCEL

    def test_cancel_urdu(self):
        result = detect_interrupt("order cancel karo")
        assert result == InterruptType.CANCEL

    def test_menu_english(self):
        result = detect_interrupt("main menu")
        assert result == InterruptType.MENU

    def test_menu_urdu(self):
        result = detect_interrupt("menu dikhao")
        assert result == InterruptType.MENU

    def test_help_english(self):
        result = detect_interrupt("help me")
        assert result == InterruptType.HELP

    def test_handoff_english(self):
        result = detect_interrupt("talk to human")
        assert result == InterruptType.HANDOFF

    def test_handoff_urdu(self):
        result = detect_interrupt("insaan se baat karo")
        assert result == InterruptType.HANDOFF

    def test_goodbye_english(self):
        result = detect_interrupt("bye")
        assert result == InterruptType.GOODBYE

    def test_goodbye_urdu(self):
        result = detect_interrupt("allah hafiz")
        assert result == InterruptType.GOODBYE

    def test_no_interrupt(self):
        result = detect_interrupt("mujhe paracetamol chahiye 2 packet")
        assert result is None

    def test_handoff_priority_over_cancel(self):
        """Handoff should take priority over cancel."""
        result = detect_interrupt("cancel and talk to human")
        assert result == InterruptType.HANDOFF

    def test_case_insensitive(self):
        result = detect_interrupt("CANCEL ORDER")
        assert result == InterruptType.CANCEL


class TestInterruptTargetStates:
    """Test interrupt → target state mapping."""

    def test_cancel_target_a(self):
        state = get_target_state_a(InterruptType.CANCEL)
        assert state == SessionStateA.MAIN_MENU.value

    def test_menu_target_a(self):
        state = get_target_state_a(InterruptType.MENU)
        assert state == SessionStateA.MAIN_MENU.value

    def test_handoff_target_a(self):
        state = get_target_state_a(InterruptType.HANDOFF)
        assert state == SessionStateA.HANDOFF.value

    def test_goodbye_target_a(self):
        state = get_target_state_a(InterruptType.GOODBYE)
        assert state == SessionStateA.IDLE.value

    def test_cancel_target_b(self):
        state = get_target_state_b(InterruptType.CANCEL)
        assert state == SessionStateB.IDLE.value

    def test_handoff_target_b(self):
        state = get_target_state_b(InterruptType.HANDOFF)
        assert state == SessionStateB.HANDOFF.value

    def test_goodbye_target_b(self):
        state = get_target_state_b(InterruptType.GOODBYE)
        assert state == SessionStateB.IDLE.value


class TestInterruptResponses:
    """Test bilingual interrupt response generation."""

    def test_cancel_response_english(self):
        msg = get_interrupt_response(InterruptType.CANCEL, language="english")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_cancel_response_roman_urdu(self):
        msg = get_interrupt_response(InterruptType.CANCEL, language="roman_urdu")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_help_response(self):
        msg = get_interrupt_response(InterruptType.HELP, language="english")
        assert isinstance(msg, str)

    def test_goodbye_response(self):
        msg = get_interrupt_response(InterruptType.GOODBYE, language="english")
        assert isinstance(msg, str)

    def test_default_language_is_roman_urdu(self):
        msg = get_interrupt_response(InterruptType.MENU)
        assert "menu" in msg.lower() or "wapas" in msg.lower()
