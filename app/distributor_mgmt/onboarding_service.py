"""Multi-step onboarding sequence for new distributors.

Steps: payment confirmed → welcome message → setup guide →
       test order → catalog upload → go-live.

Each step is tracked via the distributor's ``metadata`` field
under the ``onboarding`` key so progress survives restarts.
Completion of all steps sets ``onboarding_completed=True`` and
``onboarding_completed_at`` on the distributor record.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from loguru import logger

from app.core.constants import ActorType, RecipientType
from app.db.models.audit import AuditLogCreate, ScheduledMessageCreate
from app.db.models.distributor import DistributorUpdate
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.scheduled_message_repo import (
    ScheduledMessageRepository,
)


class OnboardingStep(StrEnum):
    """Ordered onboarding steps for a new distributor."""

    PAYMENT_CONFIRMED = "payment_confirmed"
    WELCOME_SENT = "welcome_sent"
    SETUP_GUIDE_SENT = "setup_guide_sent"
    TEST_ORDER_SENT = "test_order_sent"
    CATALOG_UPLOAD_PROMPTED = "catalog_upload_prompted"
    GO_LIVE = "go_live"


_STEP_ORDER: list[OnboardingStep] = list(OnboardingStep)

_STEP_MESSAGES: dict[OnboardingStep, dict[str, str]] = {
    OnboardingStep.WELCOME_SENT: {
        "roman_urdu": (
            "🎉 TELETRAAN mein khush aamdeed!\n\n"
            "Aapki subscription activate ho gayi hai. Ab hum aapko setup "
            "karwate hain taake aap apne retailers ke orders WhatsApp "
            "se manage kar sakein.\n\n"
            "Agla step: Setup guide aane wala hai..."
        ),
        "english": (
            "🎉 Welcome to TELETRAAN!\n\n"
            "Your subscription is now active. We'll walk you through "
            "setup so you can manage retailer orders via WhatsApp.\n\n"
            "Next step: Setup guide coming up..."
        ),
        "urdu": (
            "🎉 ٹیلیٹران میں خوش آمدید!\n\n"
            "آپ کی سبسکرپشن فعال ہو گئی ہے۔ اب ہم آپ کو سیٹ اپ "
            "کرواتے ہیں تاکہ آپ اپنے ریٹیلرز کے آرڈرز واٹس ایپ "
            "سے منیج کر سکیں۔\n\n"
            "اگلا قدم: سیٹ اپ گائیڈ آنے والی ہے..."
        ),
    },
    OnboardingStep.SETUP_GUIDE_SENT: {
        "roman_urdu": (
            "📋 Setup Guide\n\n"
            "1️⃣ Apni catalog file (Excel/CSV) tayyar karein — "
            "medicine name, price, unit\n"
            "2️⃣ Catalog file ko Google Drive pe upload karein\n"
            "3️⃣ Share link yahaan bhejein\n"
            "4️⃣ Hum catalog import karke confirm karenge\n\n"
            "Tayar hain? Apni catalog file bhejein!"
        ),
        "english": (
            "📋 Setup Guide\n\n"
            "1️⃣ Prepare your catalog file (Excel/CSV) — "
            "medicine name, price, unit\n"
            "2️⃣ Upload to Google Drive\n"
            "3️⃣ Share the link here\n"
            "4️⃣ We'll import and confirm\n\n"
            "Ready? Send your catalog file!"
        ),
        "urdu": (
            "📋 سیٹ اپ گائیڈ\n\n"
            "1️⃣ اپنی کیٹلاگ فائل (Excel/CSV) تیار کریں — "
            "دوائی کا نام، قیمت، یونٹ\n"
            "2️⃣ گوگل ڈرائیو پر اپ لوڈ کریں\n"
            "3️⃣ شیئر لنک یہاں بھیجیں\n"
            "4️⃣ ہم کیٹلاگ امپورٹ کر کے تصدیق کریں گے\n\n"
            "تیار ہیں؟ اپنی کیٹلاگ فائل بھیجیں!"
        ),
    },
    OnboardingStep.TEST_ORDER_SENT: {
        "roman_urdu": (
            "🧪 Test Order ka waqt!\n\n"
            "Ek test customer ke tor pe apne WhatsApp number se "
            "order karke dekhein. Yeh ensure karega ke sab kuch "
            "sahi kaam kar raha hai.\n\n"
            "Bas apne number se order likh ke bhejein — "
            "jaise koi customer karega."
        ),
        "english": (
            "🧪 Time for a Test Order!\n\n"
            "Place a test order from your own WhatsApp number to "
            "make sure everything works correctly.\n\n"
            "Just send your order text as if you were a customer."
        ),
        "urdu": (
            "🧪 ٹیسٹ آرڈر کا وقت!\n\n"
            "اپنے واٹس ایپ نمبر سے ایک ٹیسٹ آرڈر دیں تاکہ "
            "یقینی بنایا جا سکے کہ سب کچھ درست کام کر رہا ہے۔\n\n"
            "بس اپنے نمبر سے آرڈر لکھ کر بھیجیں — "
            "جیسے کوئی کسٹمر کرے گا۔"
        ),
    },
    OnboardingStep.CATALOG_UPLOAD_PROMPTED: {
        "roman_urdu": (
            "📦 Catalog Upload\n\n"
            "Test kamyab raha! Ab apni full catalog upload karein.\n\n"
            "Google Drive link ya Excel file bhej dein. Hum auto-import "
            "karke daily sync set kar denge."
        ),
        "english": (
            "📦 Catalog Upload\n\n"
            "Test successful! Now upload your full catalog.\n\n"
            "Send a Google Drive link or Excel file. We'll auto-import "
            "and set up daily sync."
        ),
        "urdu": (
            "📦 کیٹلاگ اپ لوڈ\n\n"
            "ٹیسٹ کامیاب رہا! اب اپنی مکمل کیٹلاگ اپ لوڈ کریں۔\n\n"
            "گوگل ڈرائیو لنک یا Excel فائل بھیج دیں۔ ہم خودکار "
            "امپورٹ اور روزانہ سنک سیٹ کر دیں گے۔"
        ),
    },
    OnboardingStep.GO_LIVE: {
        "roman_urdu": (
            "🟢 Aap LIVE hain!\n\n"
            "Setup mukammal! Ab aapke retailers order de sakte hain.\n\n"
            "✅ Catalog imported\n"
            "✅ Test order verified\n"
            "✅ WhatsApp bot active\n\n"
            "Koi masla ho to TYPE: help"
        ),
        "english": (
            "🟢 You're LIVE!\n\n"
            "Setup complete! Your retailers can now place orders.\n\n"
            "✅ Catalog imported\n"
            "✅ Test order verified\n"
            "✅ WhatsApp bot active\n\n"
            "Need help? Type: help"
        ),
        "urdu": (
            "🟢 آپ لائیو ہیں!\n\n"
            "سیٹ اپ مکمل! اب آپ کے ریٹیلرز آرڈر دے سکتے ہیں۔\n\n"
            "✅ کیٹلاگ امپورٹ\n"
            "✅ ٹیسٹ آرڈر تصدیق شدہ\n"
            "✅ واٹس ایپ بوٹ فعال\n\n"
            "مدد چاہیے؟ لکھیں: help"
        ),
    },
}


class OnboardingService:
    """Manages the multi-step onboarding process for new distributors.

    Progress is tracked via the distributor's ``metadata.onboarding``
    dict, which stores completed steps and timestamps.

    Attributes:
        _dist_repo: Distributor repository.
        _msg_repo: Scheduled message repository.
        _audit_repo: Audit log repository.
    """

    def __init__(self) -> None:
        self._dist_repo = DistributorRepository()
        self._msg_repo = ScheduledMessageRepository()
        self._audit_repo = AuditRepository()

    async def start_onboarding(
        self,
        distributor_id: str,
        *,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: Optional[str] = None,
    ) -> None:
        """Begin the onboarding sequence after payment confirmation.

        Marks the PAYMENT_CONFIRMED step as complete and sends
        the welcome message.

        Args:
            distributor_id: UUID of the new distributor.
            actor_type: Who triggered onboarding.
            actor_id: Optional actor UUID.

        Raises:
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)

        if distributor.onboarding_completed:
            logger.info(
                "onboarding.already_completed",
                distributor_id=distributor_id,
            )
            return

        # Mark payment confirmed
        await self._complete_step(
            distributor=distributor,
            step=OnboardingStep.PAYMENT_CONFIRMED,
            actor_type=actor_type,
            actor_id=actor_id,
        )

        # Send welcome message
        await self._send_step_message(
            distributor=distributor,
            step=OnboardingStep.WELCOME_SENT,
        )
        await self._complete_step(
            distributor=distributor,
            step=OnboardingStep.WELCOME_SENT,
            actor_type=actor_type,
            actor_id=actor_id,
        )

        logger.info(
            "onboarding.started",
            distributor_id=distributor_id,
        )

    async def advance_onboarding(
        self,
        distributor_id: str,
        completed_step: OnboardingStep,
        *,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: Optional[str] = None,
    ) -> Optional[OnboardingStep]:
        """Mark a step as complete and advance to the next.

        Sends the next step's message if one exists.

        Args:
            distributor_id: UUID of the distributor.
            completed_step: The step that was just completed.
            actor_type: Who triggered the advancement.
            actor_id: Optional actor UUID.

        Returns:
            The next step if one exists, or None if onboarding is
            complete.

        Raises:
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)

        if distributor.onboarding_completed:
            return None

        await self._complete_step(
            distributor=distributor,
            step=completed_step,
            actor_type=actor_type,
            actor_id=actor_id,
        )

        next_step = self._get_next_step(completed_step)
        if next_step is None:
            # Last step completed — mark onboarding done
            await self._finalize_onboarding(
                distributor_id=distributor_id,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            return None

        # Send next step message if it has one
        if next_step in _STEP_MESSAGES:
            await self._send_step_message(
                distributor=distributor,
                step=next_step,
            )

        return next_step

    async def get_onboarding_progress(
        self,
        distributor_id: str,
    ) -> dict:
        """Get the current onboarding progress for a distributor.

        Args:
            distributor_id: UUID of the distributor.

        Returns:
            Dict with completed steps, current step, and completion
            status.

        Raises:
            NotFoundError: If distributor not found.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)
        onboarding_data = distributor.metadata.get("onboarding", {})
        completed = onboarding_data.get("completed_steps", [])

        current_step: Optional[str] = None
        for step in _STEP_ORDER:
            if step.value not in completed:
                current_step = step.value
                break

        return {
            "distributor_id": distributor_id,
            "completed_steps": completed,
            "current_step": current_step,
            "total_steps": len(_STEP_ORDER),
            "completed_count": len(completed),
            "is_complete": distributor.onboarding_completed,
            "completed_at": (
                distributor.onboarding_completed_at.isoformat()
                if distributor.onboarding_completed_at
                else None
            ),
        }

    async def reset_onboarding(
        self,
        distributor_id: str,
        *,
        actor_type: ActorType = ActorType.OWNER,
        actor_id: Optional[str] = None,
    ) -> None:
        """Reset onboarding progress for a distributor.

        Used when a distributor needs to redo onboarding (e.g., after
        re-subscription).

        Args:
            distributor_id: UUID of the distributor.
            actor_type: Who triggered the reset.
            actor_id: Optional actor UUID.

        Raises:
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)

        # Clear onboarding metadata
        new_metadata = dict(distributor.metadata)
        new_metadata.pop("onboarding", None)

        update = DistributorUpdate(
            onboarding_completed=False,
            onboarding_completed_at=None,
            metadata=new_metadata,
        )
        await self._dist_repo.update(distributor_id, update)

        await self._audit_onboarding(
            distributor_id=distributor_id,
            action="onboarding.reset",
            actor_type=actor_type,
            actor_id=actor_id,
        )

        logger.info(
            "onboarding.reset",
            distributor_id=distributor_id,
        )

    # ── Private helpers ─────────────────────────────────────────────

    async def _complete_step(
        self,
        *,
        distributor: object,
        step: OnboardingStep,
        actor_type: ActorType,
        actor_id: Optional[str],
    ) -> None:
        """Mark a single onboarding step as complete.

        Updates the distributor's metadata.onboarding.completed_steps.

        Args:
            distributor: Distributor object.
            step: Step to mark complete.
            actor_type: Who triggered.
            actor_id: Optional actor UUID.
        """
        dist_id = str(getattr(distributor, "id", ""))
        metadata = dict(getattr(distributor, "metadata", {}))
        onboarding_data = dict(metadata.get("onboarding", {}))
        completed_steps: list[str] = list(
            onboarding_data.get("completed_steps", [])
        )

        if step.value in completed_steps:
            return

        completed_steps.append(step.value)
        onboarding_data["completed_steps"] = completed_steps
        onboarding_data[f"{step.value}_at"] = (
            datetime.now(tz=timezone.utc).isoformat()
        )
        metadata["onboarding"] = onboarding_data

        update = DistributorUpdate(metadata=metadata)
        await self._dist_repo.update(dist_id, update)

        await self._audit_onboarding(
            distributor_id=dist_id,
            action=f"onboarding.step.{step.value}",
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={"step": step.value},
        )

        logger.info(
            "onboarding.step_completed",
            distributor_id=dist_id,
            step=step.value,
        )

    async def _send_step_message(
        self,
        *,
        distributor: object,
        step: OnboardingStep,
    ) -> None:
        """Send the onboarding message for a step.

        Creates a scheduled_message row for the message.

        Args:
            distributor: Distributor object.
            step: The step whose message to send.
        """
        lang = getattr(
            getattr(distributor, "bot_language_default", None),
            "value",
            "roman_urdu",
        )
        dist_id = getattr(distributor, "id", "")
        whatsapp_number = getattr(distributor, "whatsapp_number", "")

        step_msgs = _STEP_MESSAGES.get(step)
        if not step_msgs:
            return

        text = step_msgs.get(lang, step_msgs.get("roman_urdu", ""))
        if not text:
            return

        idempotency_key = f"onboarding:{dist_id}:{step.value}"

        msg_data = ScheduledMessageCreate(
            distributor_id=dist_id,
            recipient_number=whatsapp_number,
            recipient_type=RecipientType.DISTRIBUTOR,
            message_type=f"onboarding_{step.value}",
            message_payload={"text": text, "step": step.value},
            scheduled_for=datetime.now(tz=timezone.utc),
            reference_id=dist_id,
            reference_type="distributor",
            idempotency_key=idempotency_key,
        )

        try:
            await self._msg_repo.create(msg_data)
        except Exception as exc:
            logger.error(
                "onboarding.message_create_failed",
                distributor_id=str(dist_id),
                step=step.value,
                error=str(exc),
            )

    async def _finalize_onboarding(
        self,
        distributor_id: str,
        *,
        actor_type: ActorType,
        actor_id: Optional[str],
    ) -> None:
        """Mark onboarding as fully complete.

        Sets ``onboarding_completed=True`` and
        ``onboarding_completed_at`` on the distributor record.

        Args:
            distributor_id: UUID of the distributor.
            actor_type: Who triggered finalization.
            actor_id: Optional actor UUID.
        """
        now = datetime.now(tz=timezone.utc)
        update = DistributorUpdate(
            onboarding_completed=True,
            onboarding_completed_at=now,
        )
        await self._dist_repo.update(distributor_id, update)

        await self._audit_onboarding(
            distributor_id=distributor_id,
            action="onboarding.completed",
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={"completed_at": now.isoformat()},
        )

        logger.info(
            "onboarding.completed",
            distributor_id=distributor_id,
        )

    @staticmethod
    def _get_next_step(
        current_step: OnboardingStep,
    ) -> Optional[OnboardingStep]:
        """Get the next step after the given one.

        Args:
            current_step: The step that was just completed.

        Returns:
            Next OnboardingStep, or None if this was the last step.
        """
        try:
            idx = _STEP_ORDER.index(current_step)
            if idx + 1 < len(_STEP_ORDER):
                return _STEP_ORDER[idx + 1]
            return None
        except ValueError:
            return None

    async def _audit_onboarding(
        self,
        *,
        distributor_id: str,
        action: str,
        actor_type: ActorType,
        actor_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:
        """Write an onboarding audit log entry.

        Never raises — audit failures are logged but don't block.

        Args:
            distributor_id: UUID of the distributor.
            action: Audit action string.
            actor_type: Who triggered.
            actor_id: Optional actor UUID.
            metadata: Additional metadata.
        """
        try:
            audit_entry = AuditLogCreate(
                actor_type=actor_type,
                actor_id=actor_id,
                distributor_id=distributor_id,
                action=action,
                entity_type="distributor",
                entity_id=distributor_id,
                metadata=metadata or {},
            )
            await self._audit_repo.create(audit_entry)
        except Exception as exc:
            logger.error(
                "onboarding.audit_failed",
                distributor_id=distributor_id,
                action=action,
                error=str(exc),
            )


# ── Module singleton ────────────────────────────────────────────────

onboarding_service = OnboardingService()
