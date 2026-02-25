"""Channel B — Post-payment onboarding flow.

Automates the steps after a prospect pays:
1. Create distributor record from prospect data
2. Run OnboardingService sequence (welcome, setup guide, etc.)
3. Assign Channel A phone number
4. Send welcome kit
5. Catalog upload instructions
6. Test order setup

This module bridges the Channel B sales funnel with the Channel A
operational infrastructure via the Distributor Management services.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from app.channels.channel_b.state_machine import transition
from app.core.constants import (
    ActorType,
    ProspectStatus,
    SessionStateB,
    SubscriptionStatus,
)
from app.db.models.distributor import DistributorCreate
from app.db.models.prospect import Prospect, ProspectUpdate
from app.db.models.session import Session
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.prospect_repo import ProspectRepository
from app.db.repositories.session_repo import SessionRepository
from app.whatsapp.message_types import build_button_message, build_text_message


# ═══════════════════════════════════════════════════════════════════
# Messages
# ═══════════════════════════════════════════════════════════════════

_ONBOARDING_START = (
    "🎉 *Welcome to TELETRAAN!*\n\n"
    "Aapka account setup ho raha hai. Yeh process kuch minutes mein "
    "complete ho jayega.\n\n"
    "Kya aap abhi apni catalog (medicine list) upload karna chahte hain?"
)

_DISTRIBUTOR_CREATED = (
    "✅ Aapka TELETRAAN distributor account create ho gaya!\n\n"
    "📋 Account details:\n"
    "• Business: {business_name}\n"
    "• Owner: {owner_name}\n"
    "• City: {city}\n"
    "• Subscription: 1 month (Active)\n\n"
    "Ab aapka setup complete karte hain 👇"
)

_CATALOG_INSTRUCTIONS = (
    "📦 *Catalog Upload Instructions:*\n\n"
    "1. Apni medicine list Excel file mein tayar karein:\n"
    "   Column A: Medicine Name (English)\n"
    "   Column B: Pack Size (e.g., Strip, Bottle)\n"
    "   Column C: Unit Price (PKR)\n"
    "   Column D: Stock Quantity\n\n"
    "2. WhatsApp par Excel file bhej dein\n"
    "3. Hum automatically import kar lenge\n\n"
    "Ya 'skip' likhen — baad mein bhi kar saktay hain."
)

_TEST_ORDER = (
    "🧪 *Test Order Setup*\n\n"
    "Aap ab ek test order place kar ke dekh saktay hain:\n\n"
    "1. Apne WhatsApp number se apne bot number par message karein\n"
    "2. 'Order' likhen\n"
    "3. Koi bhi medicine name likhen\n\n"
    "Bot automatically respond karega!"
)

_ONBOARDING_COMPLETE = (
    "🚀 *Setup Complete!*\n\n"
    "Aapka TELETRAAN bot ab live hai! Aapke retailers ab WhatsApp "
    "par order place kar saktay hain.\n\n"
    "📞 Bot Number: {bot_number}\n\n"
    "Koi bhi help chahiye toh 'help' likhen ya 'talk to human' se "
    "humari team se baat karein.\n\n"
    "Shukriya TELETRAAN choose karne ke liye! 🙏"
)

_ALREADY_ONBOARDED = (
    "Aapka account already setup hai! ✅\n"
    "Koi help chahiye toh batayein."
)


# ═══════════════════════════════════════════════════════════════════
# Main handler
# ═══════════════════════════════════════════════════════════════════


async def handle_onboarding_step(
    session: Session,
    text: str,
    *,
    button_id: Optional[str] = None,
    session_repo: Optional[SessionRepository] = None,
    prospect_repo: Optional[ProspectRepository] = None,
    distributor_repo: Optional[DistributorRepository] = None,
) -> list[dict]:
    """ONBOARDING_SETUP state — drive the post-payment onboarding.

    The onboarding sub-steps are tracked in ``session.state_data["onboarding_step"]``.
    """
    sess_repo = session_repo or SessionRepository()
    pros_repo = prospect_repo or ProspectRepository()
    dist_repo = distributor_repo or DistributorRepository()
    to = session.whatsapp_number
    state_data = dict(session.state_data)
    onboarding_step = state_data.get("onboarding_step", "start")

    if onboarding_step == "start":
        return await _start_onboarding(
            session, state_data, to, sess_repo, pros_repo, dist_repo
        )
    elif onboarding_step == "catalog_upload":
        return await _handle_catalog_step(
            session, text, button_id, state_data, to, sess_repo
        )
    elif onboarding_step == "test_order":
        return await _handle_test_order_step(
            session, text, button_id, state_data, to, sess_repo
        )
    elif onboarding_step == "complete":
        return [build_text_message(to, _ALREADY_ONBOARDED)]
    else:
        return await _start_onboarding(
            session, state_data, to, sess_repo, pros_repo, dist_repo
        )


# ═══════════════════════════════════════════════════════════════════
# Sub-steps
# ═══════════════════════════════════════════════════════════════════


async def _start_onboarding(
    session: Session,
    state_data: dict,
    to: str,
    sess_repo: SessionRepository,
    pros_repo: ProspectRepository,
    dist_repo: DistributorRepository,
) -> list[dict]:
    """Create distributor record from prospect, send welcome."""
    messages: list[dict] = []

    # Get prospect data
    prospect_id = state_data.get("prospect_id")
    prospect: Optional[Prospect] = None
    if prospect_id:
        prospect = await pros_repo.get_by_id(prospect_id)

    qual = state_data.get("qualification", {})
    owner_name = qual.get("name", "Distributor")
    business_name = qual.get("business_name", "Business")
    city = qual.get("city", "")

    # Check if distributor already exists (idempotent)
    existing_dist_id = state_data.get("distributor_id")
    if not existing_dist_id:
        # Create new distributor
        now = datetime.now(tz=timezone.utc)
        dist = await dist_repo.create(DistributorCreate(
            business_name=business_name,
            owner_name=owner_name,
            whatsapp_number=to,
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_start=now,
            subscription_end=now + timedelta(days=30),
            trial_end=now,
            is_active=True,
            metadata={"city": city, "source": "channel_b", "prospect_id": prospect_id},
        ))
        state_data["distributor_id"] = str(dist.id)

        # Link prospect to distributor
        if prospect_id:
            await pros_repo.update(
                prospect_id,
                ProspectUpdate(
                    converted_distributor_id=dist.id,
                    converted_at=now,
                    status=ProspectStatus.CONVERTED,
                ),
            )

        logger.info(
            "onboarding.distributor_created",
            distributor_id=str(dist.id),
            business_name=business_name,
            whatsapp=to[-4:],
        )

        # Start the distributor management onboarding service
        try:
            from app.distributor_mgmt.onboarding_service import onboarding_service
            await onboarding_service.start_onboarding(str(dist.id))
        except Exception as exc:
            logger.warning(
                "onboarding.service_start_failed",
                error=str(exc),
                distributor_id=str(dist.id),
            )

        messages.append(build_text_message(
            to,
            _DISTRIBUTOR_CREATED.format(
                business_name=business_name,
                owner_name=owner_name,
                city=city,
            ),
        ))
    else:
        messages.append(build_text_message(to, "Account already created ✅"))

    # Move to catalog upload step
    state_data["onboarding_step"] = "catalog_upload"
    await sess_repo.update_state(
        str(session.id),
        SessionStateB.ONBOARDING_SETUP,
        previous_state=session.current_state,
        state_data=state_data,
    )

    messages.append(build_button_message(
        to,
        _CATALOG_INSTRUCTIONS,
        [
            ("onb_catalog_later", "Baad mein ⏰"),
            ("onb_catalog_now", "Upload karein 📤"),
        ],
    ))

    return messages


async def _handle_catalog_step(
    session: Session,
    text: str,
    button_id: Optional[str],
    state_data: dict,
    to: str,
    sess_repo: SessionRepository,
) -> list[dict]:
    """Handle catalog upload step — skip or acknowledge."""
    choice = button_id or text.strip().lower()

    if choice in {"onb_catalog_later", "skip", "baad mein", "later"}:
        state_data["onboarding_step"] = "test_order"
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.ONBOARDING_SETUP,
            previous_state=session.current_state,
            state_data=state_data,
        )
        return [
            build_text_message(to, "👍 Catalog baad mein upload kar lena."),
            build_button_message(
                to,
                _TEST_ORDER,
                [
                    ("onb_test_done", "Test ho gaya ✅"),
                    ("onb_skip_test", "Skip karein ⏭️"),
                ],
            ),
        ]

    elif choice in {"onb_catalog_now", "upload", "ready"}:
        return [build_text_message(
            to,
            "📤 Apni Excel file yahan bhej dein.\n"
            "Ya 'skip' likhen agar baad mein karna hai.",
        )]

    else:
        # Treat as file received or random text — advance to test order
        state_data["onboarding_step"] = "test_order"
        state_data["catalog_uploaded"] = True
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.ONBOARDING_SETUP,
            previous_state=session.current_state,
            state_data=state_data,
        )
        return [
            build_text_message(to, "✅ Noted! Catalog process mein hai."),
            build_button_message(
                to,
                _TEST_ORDER,
                [
                    ("onb_test_done", "Test ho gaya ✅"),
                    ("onb_skip_test", "Skip karein ⏭️"),
                ],
            ),
        ]


async def _handle_test_order_step(
    session: Session,
    text: str,
    button_id: Optional[str],
    state_data: dict,
    to: str,
    sess_repo: SessionRepository,
) -> list[dict]:
    """Handle test order step — complete onboarding."""
    choice = button_id or text.strip().lower()

    if choice in {"onb_test_done", "done", "ho gaya", "test_done", "onb_skip_test", "skip"}:
        state_data["onboarding_step"] = "complete"

        # Transition to FOLLOW_UP or IDLE based on completeness
        transition(SessionStateB.ONBOARDING_SETUP, SessionStateB.IDLE)
        await sess_repo.update_state(
            str(session.id),
            SessionStateB.IDLE,
            previous_state=session.current_state,
            state_data=state_data,
        )

        from app.core.config import get_settings
        settings = get_settings()
        bot_number = getattr(settings, "whatsapp_phone_number", "your bot number")

        logger.info(
            "onboarding.complete",
            session_id=str(session.id),
            distributor_id=state_data.get("distributor_id"),
            whatsapp=to[-4:],
        )

        return [build_text_message(
            to,
            _ONBOARDING_COMPLETE.format(bot_number=bot_number),
        )]

    else:
        return [build_button_message(
            to,
            "Test order try kiya?",
            [
                ("onb_test_done", "Test ho gaya ✅"),
                ("onb_skip_test", "Skip karein ⏭️"),
            ],
        )]
