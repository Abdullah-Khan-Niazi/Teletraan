"""Rate limit repository — all database operations for the rate_limits table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.audit import RateLimit, RateLimitCreate, RateLimitUpdate


class RateLimitRepository:
    """Repository for rate_limits table operations.

    Each row represents a sliding window for a (distributor, phone)
    pair.  The scheduler cleans expired windows periodically.
    """

    TABLE = "rate_limits"
    WINDOW_MINUTES = 1  # 1-minute sliding window

    # ── Read ────────────────────────────────────────────────────────

    async def get_current_window(
        self, distributor_id: str, whatsapp_number: str
    ) -> Optional[RateLimit]:
        """Fetch the active rate-limit window for a number.

        Returns the window where ``window_start <= now <= window_end``
        for the given distributor + number pair.

        Args:
            distributor_id: Tenant scope.
            whatsapp_number: E.164 formatted phone number.

        Returns:
            RateLimit if an active window exists, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("whatsapp_number", whatsapp_number)
                .lte("window_start", now)
                .gte("window_end", now)
                .maybe_single()
                .execute()
            )
            if result.data:
                return RateLimit.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_current_window",
                number_suffix=whatsapp_number[-4:],
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} current window: {exc}",
                operation="get_current_window",
            ) from exc

    # ── Upsert ──────────────────────────────────────────────────────

    async def create_or_increment(
        self, distributor_id: str, whatsapp_number: str
    ) -> RateLimit:
        """Get the current window and increment, or create a new one.

        If an active window exists for the (distributor, number) pair,
        increments ``message_count``.  Otherwise creates a fresh window
        with ``message_count=1``.

        Args:
            distributor_id: Tenant scope.
            whatsapp_number: E.164 formatted phone number.

        Returns:
            The created or updated RateLimit.

        Raises:
            DatabaseError: On query or write failure.
        """
        try:
            existing = await self.get_current_window(
                distributor_id, whatsapp_number
            )

            if existing is not None:
                new_count = existing.message_count + 1
                client = get_db_client()
                result = (
                    await client.table(self.TABLE)
                    .update({"message_count": new_count})
                    .eq("id", str(existing.id))
                    .execute()
                )
                if not result.data:
                    raise NotFoundError(
                        f"{self.TABLE} with id={existing.id} not found for increment",
                        operation="create_or_increment",
                    )
                logger.debug(
                    "rate_limit.incremented",
                    number_suffix=whatsapp_number[-4:],
                    message_count=new_count,
                )
                return RateLimit.model_validate(result.data[0])

            now = datetime.now(timezone.utc)
            window_end = now + timedelta(minutes=self.WINDOW_MINUTES)
            create_data = RateLimitCreate(
                distributor_id=distributor_id,
                whatsapp_number=whatsapp_number,
                window_start=now,
                window_end=window_end,
                message_count=1,
            )
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .insert(
                    create_data.model_dump(exclude_none=True, mode="json")
                )
                .execute()
            )
            logger.debug(
                "rate_limit.window_created",
                number_suffix=whatsapp_number[-4:],
            )
            return RateLimit.model_validate(result.data[0])
        except (NotFoundError, DatabaseError):
            raise
        except Exception as exc:
            logger.error(
                "db.upsert_failed",
                table=self.TABLE,
                operation="create_or_increment",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to create or increment {self.TABLE}: {exc}",
                operation="create_or_increment",
            ) from exc

    # ── Counter increments ──────────────────────────────────────────

    async def _increment_field(
        self, id: str, field: str, operation: str
    ) -> RateLimit:
        """Generic helper to increment a numeric counter field by 1.

        Args:
            id: UUID string of the rate limit record.
            field: Column name to increment.
            operation: Caller operation name for logging/errors.

        Returns:
            The updated RateLimit.

        Raises:
            NotFoundError: If the record does not exist.
            DatabaseError: On query or update failure.
        """
        try:
            client = get_db_client()
            # Read current value
            current_result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("id", id)
                .maybe_single()
                .execute()
            )
            if not current_result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found",
                    operation=operation,
                )
            current = RateLimit.model_validate(current_result.data)
            new_value = getattr(current, field) + 1

            result = (
                await client.table(self.TABLE)
                .update({field: new_value})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for {operation}",
                    operation=operation,
                )
            logger.debug(
                f"rate_limit.{field}_incremented",
                rate_limit_id=id,
                new_value=new_value,
            )
            return RateLimit.model_validate(result.data[0])
        except (NotFoundError, DatabaseError):
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation=operation,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to increment {field} on {self.TABLE}: {exc}",
                operation=operation,
            ) from exc

    async def increment_voice(self, id: str) -> RateLimit:
        """Increment ``voice_count`` by 1.

        Args:
            id: UUID string of the rate limit record.

        Returns:
            The updated RateLimit.

        Raises:
            NotFoundError: If the record does not exist.
            DatabaseError: On query or update failure.
        """
        return await self._increment_field(id, "voice_count", "increment_voice")

    async def increment_ai_call(self, id: str) -> RateLimit:
        """Increment ``ai_call_count`` by 1.

        Args:
            id: UUID string of the rate limit record.

        Returns:
            The updated RateLimit.

        Raises:
            NotFoundError: If the record does not exist.
            DatabaseError: On query or update failure.
        """
        return await self._increment_field(
            id, "ai_call_count", "increment_ai_call"
        )

    async def set_throttled(self, id: str) -> RateLimit:
        """Mark a rate limit record as throttled.

        Sets ``is_throttled=True``.

        Args:
            id: UUID string of the rate limit record.

        Returns:
            The updated RateLimit.

        Raises:
            NotFoundError: If the record does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update({"is_throttled": True})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for set_throttled",
                    operation="set_throttled",
                )
            logger.warning(
                "rate_limit.throttled",
                rate_limit_id=id,
            )
            return RateLimit.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="set_throttled",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to set throttled on {self.TABLE}: {exc}",
                operation="set_throttled",
            ) from exc
