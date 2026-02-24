"""Subscription lifecycle FSM — manages distributor subscription states.

States: trial → active → expiring → suspended (grace period) → cancelled.

The ``SubscriptionManager`` centralises all subscription transition
logic so that scheduler jobs, payment webhooks, and admin endpoints
all route through a single, audited code-path.

Transitions
-----------
trial → active          : after first payment confirmation
active → expiring       : when subscription_end is within 7 days
expiring → active       : after renewal payment confirmation
expiring → suspended    : on subscription_end + grace_period_days
suspended → active      : after late renewal payment confirmation
suspended → cancelled   : when grace period expires with no payment
cancelled → active      : after re-subscription payment (new cycle)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from app.core.constants import ActorType, SubscriptionStatus
from app.db.models.audit import AuditLogCreate
from app.db.models.distributor import DistributorUpdate
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.distributor_repo import DistributorRepository


# ── Valid state transitions ─────────────────────────────────────────

_VALID_TRANSITIONS: dict[SubscriptionStatus, set[SubscriptionStatus]] = {
    SubscriptionStatus.TRIAL: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.ACTIVE: {
        SubscriptionStatus.EXPIRING,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.EXPIRING: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.SUSPENDED: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.CANCELLED: {
        SubscriptionStatus.ACTIVE,
    },
}


class SubscriptionManager:
    """Manages the full subscription lifecycle for distributors.

    Every transition is validated against the FSM, persisted to the
    database, and written to the audit log.

    Attributes:
        _dist_repo: Distributor repository instance.
        _audit_repo: Audit log repository instance.
    """

    def __init__(self) -> None:
        self._dist_repo = DistributorRepository()
        self._audit_repo = AuditRepository()

    # ── Public transition methods ───────────────────────────────────

    async def activate_subscription(
        self,
        distributor_id: str,
        subscription_months: int = 1,
        *,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: Optional[str] = None,
    ) -> None:
        """Activate a subscription after payment confirmation.

        Works from trial, expiring, suspended, or cancelled states.
        Sets subscription_start, subscription_end, and flips
        is_active=True.

        Args:
            distributor_id: UUID of the distributor.
            subscription_months: Duration in months (default 1).
            actor_type: Who triggered the activation.
            actor_id: Optional UUID of the actor.

        Raises:
            ValueError: If transition from current state is invalid.
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)
        old_status = distributor.subscription_status

        self._validate_transition(old_status, SubscriptionStatus.ACTIVE)

        now = datetime.now(tz=timezone.utc)
        # If renewing from active/expiring, extend from current end date
        if (
            old_status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRING)
            and distributor.subscription_end
            and distributor.subscription_end > now
        ):
            new_start = distributor.subscription_start or now
            new_end = distributor.subscription_end + timedelta(
                days=30 * subscription_months,
            )
        else:
            new_start = now
            new_end = now + timedelta(days=30 * subscription_months)

        update = DistributorUpdate(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_start=new_start,
            subscription_end=new_end,
            is_active=True,
        )
        await self._dist_repo.update(distributor_id, update)

        await self._audit_transition(
            distributor_id=distributor_id,
            old_status=old_status,
            new_status=SubscriptionStatus.ACTIVE,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={
                "subscription_months": subscription_months,
                "subscription_start": new_start.isoformat(),
                "subscription_end": new_end.isoformat(),
            },
        )

        logger.info(
            "subscription.activated",
            distributor_id=distributor_id,
            old_status=old_status.value,
            months=subscription_months,
            expires=new_end.isoformat(),
        )

    async def mark_expiring(
        self,
        distributor_id: str,
        *,
        actor_type: ActorType = ActorType.SCHEDULER,
        actor_id: Optional[str] = None,
    ) -> None:
        """Transition an active subscription to expiring state.

        Called by the reminder scheduler when subscription_end is
        within the warning window (typically 7 days).

        Args:
            distributor_id: UUID of the distributor.
            actor_type: Who triggered the transition.
            actor_id: Optional UUID of the actor.

        Raises:
            ValueError: If not currently ACTIVE.
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)
        old_status = distributor.subscription_status

        # Idempotent — already expiring, skip
        if old_status == SubscriptionStatus.EXPIRING:
            return

        self._validate_transition(old_status, SubscriptionStatus.EXPIRING)

        update = DistributorUpdate(
            subscription_status=SubscriptionStatus.EXPIRING,
        )
        await self._dist_repo.update(distributor_id, update)

        await self._audit_transition(
            distributor_id=distributor_id,
            old_status=old_status,
            new_status=SubscriptionStatus.EXPIRING,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={
                "subscription_end": (
                    distributor.subscription_end.isoformat()
                    if distributor.subscription_end
                    else None
                ),
            },
        )

        logger.info(
            "subscription.marked_expiring",
            distributor_id=distributor_id,
            subscription_end=(
                distributor.subscription_end.isoformat()
                if distributor.subscription_end
                else "unknown"
            ),
        )

    async def suspend(
        self,
        distributor_id: str,
        *,
        actor_type: ActorType = ActorType.SCHEDULER,
        actor_id: Optional[str] = None,
    ) -> None:
        """Suspend a distributor whose subscription has expired.

        The distributor enters a grace period of
        ``grace_period_days`` (default 3) during which they can still
        renew.  The bot will refuse to process new orders.

        Args:
            distributor_id: UUID of the distributor.
            actor_type: Who triggered the suspension.
            actor_id: Optional UUID of the actor.

        Raises:
            ValueError: If not in EXPIRING state.
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)
        old_status = distributor.subscription_status

        # Idempotent
        if old_status == SubscriptionStatus.SUSPENDED:
            return

        self._validate_transition(old_status, SubscriptionStatus.SUSPENDED)

        update = DistributorUpdate(
            subscription_status=SubscriptionStatus.SUSPENDED,
            is_active=False,
        )
        await self._dist_repo.update(distributor_id, update)

        await self._audit_transition(
            distributor_id=distributor_id,
            old_status=old_status,
            new_status=SubscriptionStatus.SUSPENDED,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={
                "grace_period_days": distributor.grace_period_days,
                "grace_expires": (
                    datetime.now(tz=timezone.utc)
                    + timedelta(days=distributor.grace_period_days)
                ).isoformat(),
            },
        )

        logger.warning(
            "subscription.suspended",
            distributor_id=distributor_id,
            grace_period_days=distributor.grace_period_days,
        )

    async def cancel(
        self,
        distributor_id: str,
        *,
        reason: str = "grace_period_expired",
        actor_type: ActorType = ActorType.SCHEDULER,
        actor_id: Optional[str] = None,
    ) -> None:
        """Cancel a subscription permanently.

        Called when the grace period expires without payment, or by
        admin/owner action.  The distributor is deactivated.

        Args:
            distributor_id: UUID of the distributor.
            reason: Human-readable cancellation reason.
            actor_type: Who triggered the cancellation.
            actor_id: Optional UUID of the actor.

        Raises:
            ValueError: If transition is invalid.
            NotFoundError: If distributor not found.
            DatabaseError: On DB failure.
        """
        distributor = await self._dist_repo.get_by_id_or_raise(distributor_id)
        old_status = distributor.subscription_status

        # Idempotent
        if old_status == SubscriptionStatus.CANCELLED:
            return

        self._validate_transition(old_status, SubscriptionStatus.CANCELLED)

        update = DistributorUpdate(
            subscription_status=SubscriptionStatus.CANCELLED,
            is_active=False,
        )
        await self._dist_repo.update(distributor_id, update)

        await self._audit_transition(
            distributor_id=distributor_id,
            old_status=old_status,
            new_status=SubscriptionStatus.CANCELLED,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={"reason": reason},
        )

        logger.warning(
            "subscription.cancelled",
            distributor_id=distributor_id,
            reason=reason,
        )

    # ── Lifecycle check methods ─────────────────────────────────────

    async def check_and_transition_expiring(self) -> int:
        """Find active distributors nearing expiry and mark them expiring.

        Queries for distributors with ``subscription_status in
        ('active',)`` and ``subscription_end <= now + 7 days``.

        Returns:
            Number of distributors transitioned to EXPIRING.
        """
        distributors = await self._dist_repo.get_expiring_subscriptions(
            days_ahead=7,
        )
        count = 0
        for dist in distributors:
            if dist.subscription_status != SubscriptionStatus.ACTIVE:
                continue
            try:
                await self.mark_expiring(str(dist.id))
                count += 1
            except (ValueError, Exception) as exc:
                logger.error(
                    "subscription.mark_expiring_failed",
                    distributor_id=str(dist.id),
                    error=str(exc),
                )
        return count

    async def check_and_suspend_expired(self) -> int:
        """Find expiring distributors past their subscription_end and suspend them.

        Returns:
            Number of distributors suspended.
        """
        now = datetime.now(tz=timezone.utc)
        # Get distributors where subscription_end has passed
        distributors = await self._dist_repo.get_expiring_subscriptions(
            days_ahead=0,
        )
        count = 0
        for dist in distributors:
            if dist.subscription_status != SubscriptionStatus.EXPIRING:
                continue
            if dist.subscription_end and dist.subscription_end <= now:
                try:
                    await self.suspend(str(dist.id))
                    count += 1
                except (ValueError, Exception) as exc:
                    logger.error(
                        "subscription.suspend_failed",
                        distributor_id=str(dist.id),
                        error=str(exc),
                    )
        return count

    async def check_and_cancel_grace_expired(self) -> int:
        """Find suspended distributors whose grace period has expired and cancel.

        Grace period is ``subscription_end + grace_period_days``.

        Returns:
            Number of distributors cancelled.
        """
        now = datetime.now(tz=timezone.utc)
        # We need to get suspended distributors — not available in
        # get_expiring_subscriptions, so query active distributors differently
        active_distributors = await self._get_suspended_distributors()
        count = 0
        for dist in active_distributors:
            if dist.subscription_status != SubscriptionStatus.SUSPENDED:
                continue
            grace_end = self._calculate_grace_end(dist)
            if grace_end and grace_end <= now:
                try:
                    await self.cancel(str(dist.id))
                    count += 1
                except (ValueError, Exception) as exc:
                    logger.error(
                        "subscription.cancel_failed",
                        distributor_id=str(dist.id),
                        error=str(exc),
                    )
        return count

    async def run_lifecycle_checks(self) -> dict[str, int]:
        """Execute all lifecycle check methods in order.

        Called by the scheduler job.  The order matters:
        1. Cancel grace-expired first (so we don't re-suspend)
        2. Suspend newly-expired
        3. Mark nearing-expiry as expiring

        Returns:
            Dict with counts: expiring, suspended, cancelled.
        """
        cancelled = await self.check_and_cancel_grace_expired()
        suspended = await self.check_and_suspend_expired()
        expiring = await self.check_and_transition_expiring()

        logger.info(
            "subscription.lifecycle_check_complete",
            expiring=expiring,
            suspended=suspended,
            cancelled=cancelled,
        )
        return {
            "expiring": expiring,
            "suspended": suspended,
            "cancelled": cancelled,
        }

    # ── Query helpers ───────────────────────────────────────────────

    def is_subscription_valid(
        self,
        status: SubscriptionStatus,
    ) -> bool:
        """Check if a subscription status allows normal bot operation.

        Only TRIAL and ACTIVE allow order processing.

        Args:
            status: Current subscription status.

        Returns:
            True if the distributor can process orders.
        """
        return status in (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE)

    @staticmethod
    def _calculate_grace_end(
        distributor: object,
    ) -> Optional[datetime]:
        """Calculate the grace period end date.

        Args:
            distributor: Distributor object with subscription_end and
                grace_period_days.

        Returns:
            Datetime when grace period expires, or None if no
            subscription_end is set.
        """
        sub_end = getattr(distributor, "subscription_end", None)
        grace_days = getattr(distributor, "grace_period_days", 3)
        if sub_end is None:
            return None
        return sub_end + timedelta(days=grace_days)

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _validate_transition(
        current: SubscriptionStatus,
        target: SubscriptionStatus,
    ) -> None:
        """Validate that a state transition is allowed.

        Args:
            current: Current subscription status.
            target: Desired new status.

        Raises:
            ValueError: If the transition is not in the FSM map.
        """
        allowed = _VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid subscription transition: {current.value} → {target.value}. "
                f"Allowed from {current.value}: {[s.value for s in allowed]}"
            )

    async def _get_suspended_distributors(self) -> list:
        """Fetch distributors in SUSPENDED state.

        Uses a direct query since get_expiring_subscriptions only
        covers 'active' and 'expiring' states.

        Returns:
            List of Distributor entities in SUSPENDED state.
        """
        try:
            from app.db.client import get_db_client
            from app.db.models.distributor import Distributor

            client = get_db_client()
            result = (
                await client.table("distributors")
                .select("*")
                .eq("subscription_status", "suspended")
                .eq("is_deleted", False)
                .execute()
            )
            return [Distributor.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "subscription.get_suspended_failed",
                error=str(exc),
            )
            return []

    async def _audit_transition(
        self,
        *,
        distributor_id: str,
        old_status: SubscriptionStatus,
        new_status: SubscriptionStatus,
        actor_type: ActorType,
        actor_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:
        """Write a subscription transition to the audit log.

        Never raises — audit failures are logged but do not block the
        transition.

        Args:
            distributor_id: UUID of the distributor.
            old_status: Previous subscription status.
            new_status: New subscription status.
            actor_type: Who triggered the transition.
            actor_id: Optional UUID of the actor.
            metadata: Additional metadata for the audit entry.
        """
        try:
            audit_entry = AuditLogCreate(
                actor_type=actor_type,
                actor_id=actor_id,
                distributor_id=distributor_id,
                action=f"subscription.{new_status.value}",
                entity_type="distributor",
                entity_id=distributor_id,
                before_state={"subscription_status": old_status.value},
                after_state={"subscription_status": new_status.value},
                metadata=metadata or {},
            )
            await self._audit_repo.create(audit_entry)
        except Exception as exc:
            logger.error(
                "subscription.audit_failed",
                distributor_id=distributor_id,
                transition=f"{old_status.value} → {new_status.value}",
                error=str(exc),
            )


# ── Module singleton ────────────────────────────────────────────────

subscription_manager = SubscriptionManager()
