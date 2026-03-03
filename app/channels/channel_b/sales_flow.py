"""Channel B — Sales flow: prospect qualification through payment.

Handles the complete sales funnel from first contact through qualification,
service presentation, demo booking, proposal, and payment link generation.

Each stage corresponds to a ``SessionStateB`` constant and stores
intermediate data in ``session.state_data``.

State data shape::

    {
        "prospect_id": "uuid",
        "service_id": "uuid",
        "qualification": {
            "name": "...",
            "business_name": "...",
            "city": "...",
            "retailer_count": 50,
        },
        "demo_slot": "2025-02-01T10:00:00Z",
        "payment_link": "...",
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from app.channels.channel_b.state_machine import transition
from app.core.constants import ProspectStatus, SessionStateB
from app.db.models.prospect import ProspectCreate, ProspectUpdate
from app.db.models.session import Session
from app.db.repositories.prospect_repo import ProspectRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import (
    build_button_message,
    build_list_message,
    build_text_message,
)


# ═══════════════════════════════════════════════════════════════════
# PROMPTS (bilingual: Roman Urdu + English)
# ═══════════════════════════════════════════════════════════════════

_GREETING = (
    "Assalam o Alaikum! 👋 Main TELETRAAN hoon.\n"
    "Hum WhatsApp par medicine distributors ke liye order management system "
    "provide karte hain.\n\n"
    "Kya aap apne business ke liye interested hain? (Yes/Haan)"
)

_ASK_NAME = (
    "Bohat acha! 😊 Pehle apna naam bata dein taake hum aapko "
    "properly address kar sakein."
)

_ASK_BUSINESS = (
    "Shukriya {name}! 🏢\n"
    "Ab apne business ka naam batayein — kon si company / distribution house?"
)

_ASK_CITY = (
    "👍 {business_name}\n"
    "Aapka business kis city mein hai?"
)

_ASK_RETAILER_COUNT = (
    "📍 {city} — noted!\n"
    "Kitne retailers ko aap deliver karte hain? (Approx number)"
)

_QUALIFICATION_COMPLETE = (
    "✅ Shukriya! Aapki info:\n\n"
    "👤 {name}\n"
    "🏢 {business_name}\n"
    "📍 {city}\n"
    "🏪 ~{retailer_count} retailers\n\n"
    "Ab main aapko humara system detail mein batata hoon 👇"
)

_SERVICE_DETAIL = (
    "{service_detail}\n\n"
    "Kya aap isko try karna chahenge?"
)

_DEMO_ASK = (
    "📅 Demo ke liye kab free hain? Apna preferred time batayein "
    "(e.g., 'kal 3 baje', 'Monday 11am')\n\n"
    "Ya agar abhi confirm karna chahte hain toh 'skip' likhen."
)

_DEMO_BOOKED = (
    "✅ Demo booked: {slot}\n"
    "Hum aapko yaad dila denge. Ab main proposal bhejta hoon 👇"
)

_PROPOSAL = (
    "📋 *TELETRAAN Order Bot — Proposal*\n\n"
    "✅ {service_name}\n"
    "💰 Monthly: PKR {monthly_fee}\n"
    "💰 Setup: PKR {setup_fee}\n\n"
    "Features:\n"
    "• WhatsApp order management (voice + text)\n"
    "• Fuzzy medicine matching\n"
    "• Live billing & discount negotiation\n"
    "• Daily/weekly Excel reports\n"
    "• PDF catalog generation\n\n"
    "Total abhi: PKR {total_now}"
)

_PAYMENT_LINK = (
    "💳 Payment ka link:\n{payment_link}\n\n"
    "Payment hogaye toh humein batayein — hum turant setup shuru kar denge! 🚀"
)

_PAYMENT_CONFIRMED = (
    "🎉 Payment receive ho gaya! Shukriya {name}!\n\n"
    "Ab hum aapka TELETRAAN account setup karna shuru kar rahe hain.\n"
    "Agla step: Onboarding guide aayega kuch minutes mein."
)

_NOT_INTERESTED = (
    "Koi baat nahi! 👋 Agar baad mein interest ho toh message kar dein.\n"
    "Allah Hafiz!"
)

_INVALID_NUMBER = (
    "⚠️ Yeh number sahi nahi laga. Sirf number dein (jaise: 50)"
)


# ═══════════════════════════════════════════════════════════════════
# Main dispatcher
# ═══════════════════════════════════════════════════════════════════


async def handle_sales_step(
    session: Session,
    text: str,
    *,
    button_id: Optional[str] = None,
    list_id: Optional[str] = None,
    session_repo: Optional[SessionRepository] = None,
    prospect_repo: Optional[ProspectRepository] = None,
) -> list[dict]:
    """Route to the correct sales stage handler.

    Returns list of WhatsApp message payload dicts.
    """
    _sess_repo = session_repo or SessionRepository()
    _pros_repo = prospect_repo or ProspectRepository()
    to = session.whatsapp_number

    state = SessionStateB(session.current_state)

    if state == SessionStateB.GREETING:
        return await _handle_greeting(session, text, to, _sess_repo, _pros_repo)
    elif state == SessionStateB.QUALIFICATION_NAME:
        return await _handle_qualification_name(session, text, to, _sess_repo, _pros_repo)
    elif state == SessionStateB.QUALIFICATION_BUSINESS:
        return await _handle_qualification_business(session, text, to, _sess_repo, _pros_repo)
    elif state == SessionStateB.QUALIFICATION_CITY:
        return await _handle_qualification_city(session, text, to, _sess_repo, _pros_repo)
    elif state == SessionStateB.QUALIFICATION_RETAILER_COUNT:
        return await _handle_qualification_retailer_count(
            session, text, to, _sess_repo, _pros_repo
        )
    elif state == SessionStateB.SERVICE_DETAIL:
        return await _handle_service_detail(
            session, text, button_id, to, _sess_repo, _pros_repo
        )
    elif state == SessionStateB.DEMO_BOOKING:
        return await _handle_demo_booking(session, text, to, _sess_repo, _pros_repo)
    elif state == SessionStateB.PROPOSAL_SENT:
        return await _handle_proposal_response(
            session, text, button_id, to, _sess_repo, _pros_repo
        )
    elif state == SessionStateB.PAYMENT_PENDING:
        return await _handle_payment_pending(
            session, text, button_id, to, _sess_repo, _pros_repo
        )
    else:
        # Unknown state — show greeting
        return [build_text_message(to, _GREETING)]


# ═══════════════════════════════════════════════════════════════════
# Stage handlers
# ═══════════════════════════════════════════════════════════════════


async def _handle_greeting(
    session: Session,
    text: str,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """GREETING → QUALIFICATION_NAME or IDLE."""
    normalized = text.strip().lower()
    positive = {"yes", "haan", "han", "ji", "ok", "sure", "interested", "y"}

    if normalized in positive or any(kw in normalized for kw in positive):
        # Create or fetch prospect
        state_data = dict(session.state_data or {})
        prospect = await pros_repo.get_by_whatsapp_number(to)
        if not prospect:
            prospect = await pros_repo.create(
                ProspectCreate(whatsapp_number=to)
            )
        state_data["prospect_id"] = str(prospect.id)

        result = transition(SessionStateB.GREETING, SessionStateB.QUALIFICATION_NAME)
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.QUALIFICATION_NAME,
            previous_state=session.current_state,
            state_data=state_data,
        )
        logger.info(
            "sales.greeting_accepted",
            session_id=str(session.id),
            whatsapp=to[-4:],
        )
        return [build_text_message(to, _ASK_NAME)]
    else:
        # Not interested — go idle
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.IDLE,
            previous_state=session.current_state,
        )
        return [build_text_message(to, _NOT_INTERESTED)]


async def _handle_qualification_name(
    session: Session,
    text: str,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """Collect prospect's name → QUALIFICATION_BUSINESS."""
    name = text.strip()
    if len(name) < 2:
        return [build_text_message(to, "Apna poora naam dein.")]

    state_data = dict(session.state_data or {})
    state_data.setdefault("qualification", {})
    state_data["qualification"]["name"] = name

    # Update prospect record
    prospect_id = state_data.get("prospect_id")
    if prospect_id:
        await pros_repo.update(prospect_id, ProspectUpdate(name=name))

    transition(
        SessionStateB.QUALIFICATION_NAME,
        SessionStateB.QUALIFICATION_BUSINESS,
    )
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.QUALIFICATION_BUSINESS,
        previous_state=session.current_state,
        state_data=state_data,
    )
    return [build_text_message(to, _ASK_BUSINESS.format(name=name))]


async def _handle_qualification_business(
    session: Session,
    text: str,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """Collect business name → QUALIFICATION_CITY."""
    business_name = text.strip()
    if len(business_name) < 2:
        return [build_text_message(to, "Business ka naam batayein.")]

    state_data = dict(session.state_data or {})
    state_data.setdefault("qualification", {})
    state_data["qualification"]["business_name"] = business_name

    prospect_id = state_data.get("prospect_id")
    if prospect_id:
        await pros_repo.update(
            prospect_id, ProspectUpdate(business_name=business_name)
        )

    transition(
        SessionStateB.QUALIFICATION_BUSINESS,
        SessionStateB.QUALIFICATION_CITY,
    )
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.QUALIFICATION_CITY,
        previous_state=session.current_state,
        state_data=state_data,
    )
    return [build_text_message(to, _ASK_CITY.format(business_name=business_name))]


async def _handle_qualification_city(
    session: Session,
    text: str,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """Collect city → QUALIFICATION_RETAILER_COUNT."""
    city = text.strip()
    if len(city) < 2:
        return [build_text_message(to, "City ka naam batayein.")]

    state_data = dict(session.state_data or {})
    state_data.setdefault("qualification", {})
    state_data["qualification"]["city"] = city

    prospect_id = state_data.get("prospect_id")
    if prospect_id:
        await pros_repo.update(prospect_id, ProspectUpdate(city=city))

    transition(
        SessionStateB.QUALIFICATION_CITY,
        SessionStateB.QUALIFICATION_RETAILER_COUNT,
    )
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.QUALIFICATION_RETAILER_COUNT,
        previous_state=session.current_state,
        state_data=state_data,
    )
    return [build_text_message(to, _ASK_RETAILER_COUNT.format(city=city))]


async def _handle_qualification_retailer_count(
    session: Session,
    text: str,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """Collect retailer count → SERVICE_DETAIL (show service info)."""
    # Extract number from text
    digits = "".join(c for c in text.strip() if c.isdigit())
    if not digits:
        return [build_text_message(to, _INVALID_NUMBER)]

    retailer_count = int(digits)
    state_data = dict(session.state_data or {})
    qual = state_data.setdefault("qualification", {})
    qual["retailer_count"] = retailer_count

    prospect_id = state_data.get("prospect_id")
    if prospect_id:
        await pros_repo.update(
            prospect_id,
            ProspectUpdate(
                estimated_retailer_count=retailer_count,
                status=ProspectStatus.QUALIFIED,
            ),
        )

    # Load default service
    from app.channels.channel_b.service_registry import service_registry

    service = await service_registry.get_default_service()
    if service:
        state_data["service_id"] = str(service.id)

    transition(
        SessionStateB.QUALIFICATION_RETAILER_COUNT,
        SessionStateB.SERVICE_DETAIL,
    )
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.SERVICE_DETAIL,
        previous_state=session.current_state,
        state_data=state_data,
    )

    messages: list[dict] = []

    # Qualification summary
    messages.append(build_text_message(
        to,
        _QUALIFICATION_COMPLETE.format(
            name=qual.get("name", ""),
            business_name=qual.get("business_name", ""),
            city=qual.get("city", ""),
            retailer_count=retailer_count,
        ),
    ))

    # Service detail
    if service:
        detail = service_registry.format_service_detail(service)
        messages.append(build_button_message(
            to,
            _SERVICE_DETAIL.format(service_detail=detail),
            [
                ("sales_interested", "Interested ✅"),
                ("sales_demo", "Demo dekhein 🎥"),
                ("sales_not_now", "Abhi nahi ❌"),
            ],
        ))
    else:
        messages.append(build_text_message(
            to,
            "Abhi hamara service setup ho raha hai. Jald aapko update milega!",
        ))

    logger.info(
        "sales.qualification_complete",
        session_id=str(session.id),
        retailer_count=retailer_count,
        whatsapp=to[-4:],
    )
    return messages


async def _handle_service_detail(
    session: Session,
    text: str,
    button_id: Optional[str],
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """SERVICE_DETAIL — respond to interest / demo / not-interested."""
    choice = button_id or text.strip().lower()
    state_data = dict(session.state_data or {})

    if choice in {"sales_interested", "interested", "yes", "haan", "ji"}:
        # Skip demo → straight to proposal
        return await _send_proposal(session, state_data, to, sess_repo, pros_repo)

    elif choice in {"sales_demo", "demo"}:
        transition(SessionStateB.SERVICE_DETAIL, SessionStateB.DEMO_BOOKING)
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.DEMO_BOOKING,
            previous_state=session.current_state,
            state_data=state_data,
        )
        return [build_text_message(to, _DEMO_ASK)]

    elif choice in {"sales_not_now", "nahi", "no", "bad mein", "later"}:
        # Mark as follow-up
        prospect_id = state_data.get("prospect_id")
        if prospect_id:
            follow_up = datetime.now(tz=timezone.utc) + timedelta(days=3)
            await pros_repo.update(
                prospect_id,
                ProspectUpdate(follow_up_at=follow_up),
            )
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.IDLE,
            previous_state=session.current_state,
        )
        return [build_text_message(
            to,
            "Koi baat nahi! Hum 3 din baad follow up karenge. "
            "Kisi bhi waqt message karein! 👋",
        )]
    else:
        return [build_button_message(
            to,
            "Kya karna chahte hain?",
            [
                ("sales_interested", "Interested ✅"),
                ("sales_demo", "Demo dekhein 🎥"),
                ("sales_not_now", "Abhi nahi ❌"),
            ],
        )]


async def _handle_demo_booking(
    session: Session,
    text: str,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """DEMO_BOOKING — book slot or skip to proposal."""
    normalized = text.strip().lower()
    state_data = dict(session.state_data or {})

    if normalized in {"skip", "nahi", "proposal", "confirm"}:
        # Skip demo — straight to proposal
        return await _send_proposal(session, state_data, to, sess_repo, pros_repo)

    # Accept any text as demo slot description
    demo_slot = text.strip()
    state_data["demo_slot"] = demo_slot

    prospect_id = state_data.get("prospect_id")
    if prospect_id:
        await pros_repo.update(
            prospect_id,
            ProspectUpdate(
                status=ProspectStatus.DEMO_BOOKED,
                demo_booked_at=datetime.now(tz=timezone.utc),
            ),
        )

    logger.info(
        "sales.demo_booked",
        session_id=str(session.id),
        slot=demo_slot,
        whatsapp=to[-4:],
    )

    # Move to proposal
    return await _send_proposal(
        session, state_data, to, sess_repo, pros_repo,
        header_msg=_DEMO_BOOKED.format(slot=demo_slot),
    )


async def _handle_proposal_response(
    session: Session,
    text: str,
    button_id: Optional[str],
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """PROPOSAL_SENT — proceed to payment or negotiate."""
    choice = button_id or text.strip().lower()
    state_data = dict(session.state_data or {})

    if choice in {"sales_accept", "accept", "ok", "haan", "yes", "pay"}:
        # Generate payment link and move to PAYMENT_PENDING
        return await _send_payment_link(session, state_data, to, sess_repo, pros_repo)

    elif choice in {"sales_negotiate", "discount", "kam karo", "negotiate"}:
        return [build_text_message(
            to,
            "💬 Pricing ke baare mein baat karne ke liye humara team se contact "
            "karein. 'talk to human' likh kar owner se baat kar saktay hain.",
        )]

    elif choice in {"sales_reject", "nahi", "no", "reject"}:
        prospect_id = state_data.get("prospect_id")
        if prospect_id:
            await pros_repo.update(
                prospect_id,
                ProspectUpdate(status=ProspectStatus.LOST, lost_reason="Rejected proposal"),
            )
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.IDLE,
            previous_state=session.current_state,
        )
        return [build_text_message(to, _NOT_INTERESTED)]
    else:
        return [build_button_message(
            to,
            "Proposal accept karna chahte hain?",
            [
                ("sales_accept", "Accept ✅"),
                ("sales_negotiate", "Negotiate 💬"),
                ("sales_reject", "Reject ❌"),
            ],
        )]


async def _handle_payment_pending(
    session: Session,
    text: str,
    button_id: Optional[str],
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """PAYMENT_PENDING — confirm payment or resend link."""
    choice = button_id or text.strip().lower()
    state_data = dict(session.state_data or {})

    paid_keywords = {"paid", "done", "ho gaya", "payment kar diya", "sent", "bhej diya"}
    if choice in {"sales_paid", *paid_keywords} or any(kw in choice for kw in paid_keywords):
        # Do NOT auto-confirm — mark as PAYMENT_VERIFICATION_PENDING
        # and require owner/webhook confirmation before activating.
        prospect_id = state_data.get("prospect_id")
        qual = state_data.get("qualification", {})

        if prospect_id:
            await pros_repo.update(
                prospect_id,
                ProspectUpdate(
                    status=ProspectStatus.PAYMENT_VERIFICATION,
                ),
            )

        state_data["payment_self_reported"] = True
        state_data["payment_self_reported_at"] = (
            datetime.now(tz=timezone.utc).isoformat()
        )

        await sess_repo.update_state(
            str(session.id),
            session.current_state,
            previous_state=session.current_state,
            state_data=state_data,
        )

        logger.info(
            "sales.payment_self_reported",
            session_id=str(session.id),
            prospect_id=prospect_id,
            whatsapp=to[-4:],
        )

        return [build_text_message(
            to,
            "Shukriya! Hum aapki payment verify kar rahe hain. \u23f3\n"
            "Verification complete hone par aapko update mil jayega.\n\n"
            "Agar koi issue ho toh 'talk to human' likhen.",
        )]

    elif choice in {"sales_resend", "link", "resend"}:
        link = state_data.get("payment_link", "")
        if link:
            return [build_text_message(to, f"Payment link:\n{link}")]
        return [build_text_message(to, "Payment link generate ho raha hai...")]

    else:
        return [build_button_message(
            to,
            "Payment ho gaya?",
            [
                ("sales_paid", "Paid ✅"),
                ("sales_resend", "Link dobara"),
            ],
        )]


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


async def _send_proposal(
    session: Session,
    state_data: dict,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
    *,
    header_msg: Optional[str] = None,
) -> list[dict]:
    """Build and send the proposal message, transition to PROPOSAL_SENT."""
    from app.channels.channel_b.service_registry import service_registry

    messages: list[dict] = []
    if header_msg:
        messages.append(build_text_message(to, header_msg))

    service_id = state_data.get("service_id")
    service = None
    if service_id:
        service = await service_registry.get_service_by_id(service_id)
    if not service:
        service = await service_registry.get_default_service()

    if service:
        monthly = f"{service.monthly_fee_pkr:,.0f}"
        setup = f"{service.setup_fee_pkr:,.0f}"
        total = f"{(service.monthly_fee_paisas + service.setup_fee_paisas) / 100:,.0f}"
        messages.append(build_button_message(
            to,
            _PROPOSAL.format(
                service_name=service.name,
                monthly_fee=monthly,
                setup_fee=setup,
                total_now=total,
            ),
            [
                ("sales_accept", "Accept ✅"),
                ("sales_negotiate", "Negotiate 💬"),
                ("sales_reject", "Reject ❌"),
            ],
        ))
    else:
        messages.append(build_text_message(
            to,
            "Pricing details jald available honge. Hum aapko update karenge!",
        ))

    # Update prospect status
    prospect_id = state_data.get("prospect_id")
    if prospect_id:
        await pros_repo.update(
            prospect_id, ProspectUpdate(status=ProspectStatus.PROPOSAL_SENT)
        )

    transition(
        SessionStateB(session.current_state),
        SessionStateB.PROPOSAL_SENT,
    )
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.PROPOSAL_SENT,
        previous_state=session.current_state,
        state_data=state_data,
    )
    return messages


async def _send_payment_link(
    session: Session,
    state_data: dict,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
) -> list[dict]:
    """Generate payment link and transition to PAYMENT_PENDING."""
    from app.core.config import get_settings

    settings = get_settings()
    base = getattr(settings, "payment_callback_base_url", "https://pay.teletraan.pk")
    prospect_id = state_data.get("prospect_id", "unknown")
    payment_link = f"{base}/subscribe/{prospect_id}"
    state_data["payment_link"] = payment_link

    prospect_id_str = state_data.get("prospect_id")
    if prospect_id_str:
        await pros_repo.update(
            prospect_id_str,
            ProspectUpdate(status=ProspectStatus.PAYMENT_PENDING),
        )

    transition(SessionStateB.PROPOSAL_SENT, SessionStateB.PAYMENT_PENDING)
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.PAYMENT_PENDING,
        previous_state=session.current_state,
        state_data=state_data,
    )

    logger.info(
        "sales.payment_link_sent",
        session_id=str(session.id),
        prospect_id=prospect_id_str,
        whatsapp=to[-4:],
    )

    return [
        build_text_message(to, _PAYMENT_LINK.format(payment_link=payment_link)),
        build_button_message(
            to,
            "Payment complete hone par batayein:",
            [("sales_paid", "Paid ✅"), ("sales_resend", "Link dobara")],
        ),
    ]
