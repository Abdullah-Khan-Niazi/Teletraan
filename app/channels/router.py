"""Message routing by phone_number_id, distributor resolution, and channel dispatch.

Every incoming WhatsApp message arrives tagged with a ``phone_number_id``
that identifies which registered WhatsApp Business number received it.

Routing logic
    1. Look up ``phone_number_id`` against distributor records.
    2. If the phone_number_id matches the owner's number (env var
       ``OWNER_PHONE_NUMBER_ID``), route to **Channel B** (sales funnel).
    3. Otherwise route to **Channel A** (retailer order management).
    4. If no distributor found, log warning and drop the message.

The router does NOT handle orchestration — it simply resolves the
distributor and determines which channel pipeline should process
the message.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.core.constants import ChannelType
from app.core.exceptions import NotFoundError
from app.db.models.distributor import Distributor
from app.db.repositories import distributor_repo
from app.whatsapp.parser import ParsedMessage


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

    Args:
        message: Parsed incoming WhatsApp message.

    Returns:
        ``RoutingResult`` if routing succeeded, ``None`` if the message
        should be dropped (unknown phone_number_id).
    """
    settings = get_settings()
    phone_number_id = message.phone_number_id

    # ── Channel B check (owner phone number) ─────────────────────
    if phone_number_id == settings.owner_phone_number_id:
        # For Channel B, the "distributor" context is the system owner.
        # Resolve via the owner's phone number ID.
        distributor = await _resolve_distributor(phone_number_id)
        if distributor is None:
            logger.error(
                "router.owner_distributor_not_found",
                phone_number_id=phone_number_id,
            )
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
