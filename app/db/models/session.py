"""Pydantic models for the sessions table.

Maps the ``sessions`` table defined in migration 008 to typed
Pydantic v2 models.  Three variants:

* **Session** — full row returned from the database.
* **SessionCreate** — fields required (or optional) for INSERT.
* **SessionUpdate** — all-Optional payload for PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import ChannelType, Language


class Session(BaseModel):
    """Full session row returned from DB.

    Attributes:
        id: Primary key UUID.
        distributor_id: FK to distributors — tenant boundary.
        whatsapp_number: E.164 WhatsApp number for this session.
        customer_id: FK to customers (set after onboarding).
        channel: Which channel this session belongs to (A or B).
        current_state: Current FSM state name.
        previous_state: Previous FSM state name.
        state_data: Arbitrary state-specific data.
        conversation_history: List of conversation turns.
        pending_order_draft: In-progress order context snapshot.
        language: Active conversation language.
        retry_count: Consecutive failed-understanding retries.
        handoff_mode: Whether session is handed off to a human.
        last_message_at: Timestamp of most recent message.
        expires_at: Session expiry timestamp.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    id: UUID
    distributor_id: UUID
    whatsapp_number: str
    customer_id: Optional[UUID] = None
    channel: ChannelType = ChannelType.A
    current_state: str = "idle"
    previous_state: Optional[str] = None
    state_data: dict = Field(default_factory=dict)
    conversation_history: list = Field(default_factory=list)
    pending_order_draft: dict = Field(default_factory=dict)
    language: Language = Language.ROMAN_URDU
    retry_count: int = 0
    handoff_mode: bool = False
    last_message_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    """Fields for creating a new session.

    Attributes:
        distributor_id: FK to distributors — tenant boundary.
        whatsapp_number: E.164 WhatsApp number.
        customer_id: FK to customers (optional at creation).
        channel: Channel A or B.
        current_state: Initial FSM state.
        language: Conversation language.
    """

    distributor_id: UUID
    whatsapp_number: str
    customer_id: Optional[UUID] = None
    channel: ChannelType = ChannelType.A
    current_state: str = "idle"
    language: Language = Language.ROMAN_URDU


class SessionUpdate(BaseModel):
    """Fields for updating a session (all optional).

    Only non-``None`` fields are written to the database.

    Attributes:
        customer_id: Updated customer link.
        channel: Updated channel.
        current_state: Updated FSM state.
        previous_state: Updated previous state.
        state_data: Updated state-specific data.
        conversation_history: Updated conversation turns.
        pending_order_draft: Updated order context draft.
        language: Updated language.
        retry_count: Updated retry count.
        handoff_mode: Updated handoff flag.
        last_message_at: Updated last-message timestamp.
        expires_at: Updated expiry timestamp.
    """

    customer_id: Optional[UUID] = None
    channel: Optional[ChannelType] = None
    current_state: Optional[str] = None
    previous_state: Optional[str] = None
    state_data: Optional[dict] = None
    conversation_history: Optional[list] = None
    pending_order_draft: Optional[dict] = None
    language: Optional[Language] = None
    retry_count: Optional[int] = None
    handoff_mode: Optional[bool] = None
    last_message_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
