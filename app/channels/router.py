"""Message routing by phone_number_id, distributor resolution, and channel dispatch.

Every incoming WhatsApp message arrives tagged with a ``phone_number_id``
that identifies which registered WhatsApp Business number received it.

Routing logic
    1. Look up ``phone_number_id`` against distributor records.
    2. **Rate-limit check** — enforce 30 messages/minute per sender.
    3. If the phone_number_id matches the owner's number (env var
       ``OWNER_PHONE_NUMBER_ID``), route to **Channel B** (sales funnel).
    4. Otherwise route to **Channel A** (retailer order management).
    5. If no distributor found, log warning and drop the message.

The router does NOT handle orchestration — it simply resolves the
distributor, enforces per-number rate limits, and determines which
channel pipeline should process the message.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.core.constants import ChannelType
from app.core.exceptions import NotFoundError
from app.db.models.distributor import Distributor
from app.db.repositories import distributor_repo, rate_limit_repo
from app.whatsapp.parser import ParsedMessage


# ── Constants ────────────────────────────────────────────────────────

RATE_LIMIT_MAX_MESSAGES: int = 30
"""Maximum messages per 1-minute sliding window per number."""


# ── Data class for routing result ────────────────────────────────────


class RoutingResult:
    """Encapsulates the outcome of the channel router.

    Attributes:
        distributor: The resolved distributor entity.
        channel: Which channel to route the message to.
        parsed_message: The original parsed message.
    """

    __slots__ = ("distributor", "channel", "parsed_message")

    def __init__(
        self,
        distributor: Distributor,
        channel: ChannelType,
        parsed_message: ParsedMessage,
    ) -> None:
        self.distributor = distributor
        self.channel = channel
        self.parsed_message = parsed_message

    def __repr__(self) -> str:
        return (
            f"RoutingResult(distributor_id={self.distributor.id}, "
            f"channel={self.channel.value})"
        )


# ── Router ───────────────────────────────────────────────────────────


async def resolve_and_route(message: ParsedMessage) -> RoutingResult | None:
    """Resolve distributor from phone_number_id and determine channel.

    Enforces per-number rate limiting (30 msg/min) before routing.
    On the 31st message, a single throttle reply is sent and the
    message is dropped.  From the 32nd onward, excess messages are
    dropped silently.

    Args:
        message: Parsed incoming WhatsApp message.

    Returns:
        ``RoutingResult`` if routing succeeded, ``None`` if the message
        should be dropped (unknown phone_number_id or rate-limited).
    """
    settings = get_settings()
    phone_number_id = message.phone_number_id

    # ── Channel B check (owner phone number) ─────────────────────
    if phone_number_id == settings.owner_phone_number_id:
        distributor = await _resolve_distributor(phone_number_id)
        if distributor is None:
            logger.error(
                "router.owner_distributor_not_found",
                phone_number_id=phone_number_id,
            )
            return None

        # ── Rate limit ───────────────────────────────────────────
        if await _is_rate_limited(str(distributor.id), message):
            return None

        logger.info(
            "router.channel_b",
            distributor_id=str(distributor.id),
            from_suffix=message.from_number[-4:] if message.from_number else "????",
        )
        return RoutingResult(
            distributor=distributor,
            channel=ChannelType.CHANNEL_B,
            parsed_message=message,
        )

    # ── Channel A (distributor's WhatsApp number) ────────────────
    distributor = await _resolve_distributor(phone_number_id)
    if distributor is None:
        logger.warning(
            "router.unknown_phone_number_id",
            phone_number_id=phone_number_id,
            from_suffix=message.from_number[-4:] if message.from_number else "????",
        )
        return None

    # ── Rate limit ───────────────────────────────────────────────
    if await _is_rate_limited(str(distributor.id), message):
        return None

    logger.info(
        "router.channel_a",
        distributor_id=str(distributor.id),
        from_suffix=message.from_number[-4:] if message.from_number else "????",
    )
    return RoutingResult(
        distributor=distributor,
        channel=ChannelType.CHANNEL_A,
        parsed_message=message,
    )


# ── Internal helpers ─────────────────────────────────────────────────


async def _is_rate_limited(distributor_id: str, message: ParsedMessage) -> bool:
    """Check and enforce per-number rate limiting.

    Increments the sliding-window counter and returns True if the
    sender has exceeded ``RATE_LIMIT_MAX_MESSAGES`` in the current
    window.

    Behaviour:
    - Message count <= limit → allowed (returns False).
    - Message count == limit + 1 → throttle reply sent, drops message
      (returns True).
    - Message count > limit + 1 → silently dropped (returns True).

    On any DB error the message is *allowed* through to avoid
    blocking legitimate users.

    Args:
        distributor_id: UUID string of the resolved distributor.
        message: The incoming parsed message (provides ``from_number``
            and ``phone_number_id`` for the throttle reply).

    Returns:
        True if the message should be dropped, False if it may proceed.
    """
    from_number = message.from_number
    number_suffix = from_number[-4:] if from_number else "????"

    try:
        window = await rate_limit_repo.create_or_increment(
            distributor_id, from_number
        )
        count = window.message_count

        if count <= RATE_LIMIT_MAX_MESSAGES:
            return False

        # ── Threshold just crossed — send one throttle reply ─────
        if count == RATE_LIMIT_MAX_MESSAGES + 1:
            logger.warning(
                "router.rate_limit_reached",
                distributor_id=distributor_id,
                number_suffix=number_suffix,
                message_count=count,
            )
            await _send_throttle_reply(message)
            try:
                await rate_limit_repo.set_throttled(str(window.id))
            except Exception:
                pass  # best-effort flag
            return True

        # ── Already throttled — silent drop ──────────────────────
        logger.debug(
            "router.rate_limit_excess_dropped",
            number_suffix=number_suffix,
            message_count=count,
        )
        return True

    except Exception as exc:
        # Rate-limit failure must NEVER block legitimate messages.
        logger.error(
            "router.rate_limit_error",
            number_suffix=number_suffix,
            error=str(exc),
        )
        return False


async def _send_throttle_reply(message: ParsedMessage) -> None:
    """Send a single rate-limit warning to the sender.

    Uses lazy imports to avoid circular dependency with the WhatsApp
    client and notification templates.
    """
    try:
        from app.notifications.templates.english_templates import RATE_LIMIT_MESSAGE
        from app.whatsapp.client import whatsapp_client
        from app.whatsapp.message_types import build_text_message

        payload = build_text_message(message.from_number, RATE_LIMIT_MESSAGE)
        await whatsapp_client.send_message(
            phone_number_id=message.phone_number_id,
            payload=payload,
        )
    except Exception as exc:
        logger.error(
            "router.throttle_reply_failed",
            error=str(exc),
        )


async def _resolve_distributor(phone_number_id: str) -> Distributor | None:
    """Look up a distributor by their WhatsApp phone_number_id.

    Args:
        phone_number_id: Meta-assigned phone number ID.

    Returns:
        ``Distributor`` if found, ``None`` otherwise.
    """
    try:
        return await distributor_repo.get_by_phone_number_id(phone_number_id)
    except NotFoundError:
        return None
    except Exception as exc:
        logger.error(
            "router.distributor_lookup_failed",
            phone_number_id=phone_number_id,
            error=str(exc),
        )
        return None
