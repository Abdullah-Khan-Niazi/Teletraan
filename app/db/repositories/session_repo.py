"""Session repository — all database operations for the sessions table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError, NotFoundError
from app.db.client import get_db_client
from app.db.models.session import Session, SessionCreate, SessionUpdate


class SessionRepository:
    """Repository for sessions table operations.

    Sessions track per-customer conversation state inside a tenant.
    All reads that touch a single session use ``id`` as the primary
    key; the distributor scope is enforced by the session's own
    ``distributor_id`` column rather than an explicit query filter on
    every call.
    """

    TABLE = "sessions"

    # ── Standard CRUD ───────────────────────────────────────────────

    async def get_by_id(self, id: str) -> Optional[Session]:
        """Fetch a single session by primary key.

        Args:
            id: UUID string of the session.

        Returns:
            Session if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("id", id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return Session.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_id",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_by_id",
            ) from exc

    async def get_by_id_or_raise(self, id: str) -> Session:
        """Fetch a single session or raise NotFoundError.

        Args:
            id: UUID string of the session.

        Returns:
            Session entity.

        Raises:
            NotFoundError: If no session matches the given id.
            DatabaseError: On query failure.
        """
        result = await self.get_by_id(id)
        if result is None:
            raise NotFoundError(
                f"{self.TABLE} with id={id} not found",
                operation="get_by_id_or_raise",
            )
        return result

    async def create(self, data: SessionCreate) -> Session:
        """Insert a new session row.

        Args:
            data: Validated creation payload.

        Returns:
            The newly created Session.

        Raises:
            DatabaseError: On insert failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .insert(data.model_dump(exclude_none=True, mode="json"))
                .execute()
            )
            logger.info(
                "db.record_created",
                table=self.TABLE,
                number_suffix=data.whatsapp_number[-4:],
            )
            return Session.model_validate(result.data[0])
        except Exception as exc:
            logger.error(
                "db.insert_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to create {self.TABLE}: {exc}",
                operation="create",
            ) from exc

    async def update(self, id: str, data: SessionUpdate) -> Session:
        """Update an existing session.

        Args:
            id: UUID string of the session to update.
            data: Validated update payload (only non-None fields written).

        Returns:
            The updated Session.

        Raises:
            NotFoundError: If the session does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            payload = data.model_dump(exclude_none=True, mode="json")
            if not payload:
                return await self.get_by_id_or_raise(id)
            result = (
                await client.table(self.TABLE)
                .update(payload)
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for update",
                    operation="update",
                )
            return Session.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update {self.TABLE}: {exc}",
                operation="update",
            ) from exc

    # ── Domain-specific methods ─────────────────────────────────────

    async def get_by_number(
        self, distributor_id: str, whatsapp_number: str
    ) -> Optional[Session]:
        """Look up a session by distributor + WhatsApp number.

        This is the main identification path when a message arrives —
        we find the active session for the sender within the
        distributor's tenant.

        Args:
            distributor_id: Tenant scope.
            whatsapp_number: E.164 formatted phone number.

        Returns:
            Session if found, None otherwise.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("whatsapp_number", whatsapp_number)
                .maybe_single()
                .execute()
            )
            if result.data:
                logger.debug(
                    "session.found",
                    state=result.data.get("current_state"),
                    number_suffix=whatsapp_number[-4:],
                )
                return Session.model_validate(result.data)
            return None
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_by_number",
                number_suffix=whatsapp_number[-4:],
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE} by number: {exc}",
                operation="get_by_number",
            ) from exc

    async def update_state(
        self,
        id: str,
        new_state: str,
        *,
        previous_state: str | None = None,
        state_data: dict | None = None,
        pending_order_draft: dict | None = None,
    ) -> Session:
        """Convenience method for FSM state transitions.

        Updates ``current_state``, ``previous_state``, and optionally
        ``state_data`` and ``pending_order_draft`` in a single write.

        Args:
            id: UUID string of the session.
            new_state: Target FSM state name.
            previous_state: The state being transitioned from.
            state_data: Arbitrary data for the new state.
            pending_order_draft: Updated order context snapshot.

        Returns:
            The updated Session.

        Raises:
            NotFoundError: If the session does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            payload: dict = {"current_state": new_state}
            if previous_state is not None:
                payload["previous_state"] = previous_state
            if state_data is not None:
                payload["state_data"] = state_data
            if pending_order_draft is not None:
                payload["pending_order_draft"] = pending_order_draft
            result = (
                await client.table(self.TABLE)
                .update(payload)
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for state update",
                    operation="update_state",
                )
            logger.info(
                "session.state_updated",
                session_id=id,
                new_state=new_state,
                previous_state=previous_state,
            )
            return Session.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="update_state",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update state on {self.TABLE}: {exc}",
                operation="update_state",
            ) from exc

    async def update_order_draft(self, id: str, draft: dict) -> Session:
        """Update only the ``pending_order_draft`` JSONB column.

        Args:
            id: UUID string of the session.
            draft: New order context draft dict.

        Returns:
            The updated Session.

        Raises:
            NotFoundError: If the session does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update({"pending_order_draft": draft})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for draft update",
                    operation="update_order_draft",
                )
            logger.debug("session.order_draft_updated", session_id=id)
            return Session.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="update_order_draft",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to update order draft on {self.TABLE}: {exc}",
                operation="update_order_draft",
            ) from exc

    async def clear_order_draft(self, id: str) -> Session:
        """Set ``pending_order_draft`` to an empty dict.

        Args:
            id: UUID string of the session.

        Returns:
            The updated Session.

        Raises:
            NotFoundError: If the session does not exist.
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .update({"pending_order_draft": {}})
                .eq("id", id)
                .execute()
            )
            if not result.data:
                raise NotFoundError(
                    f"{self.TABLE} with id={id} not found for draft clear",
                    operation="clear_order_draft",
                )
            logger.debug("session.order_draft_cleared", session_id=id)
            return Session.model_validate(result.data[0])
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="clear_order_draft",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to clear order draft on {self.TABLE}: {exc}",
                operation="clear_order_draft",
            ) from exc

    async def get_expired_sessions(self) -> list[Session]:
        """Fetch sessions that are non-idle and past their expiry time.

        Returns:
            List of expired Session entities.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(timezone.utc).isoformat()
            result = (
                await client.table(self.TABLE)
                .select("*")
                .neq("current_state", "idle")
                .lt("expires_at", now)
                .execute()
            )
            return [Session.model_validate(row) for row in result.data]
        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_expired_sessions",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch expired {self.TABLE}: {exc}",
                operation="get_expired_sessions",
            ) from exc

    async def delete_session(self, id: str) -> bool:
        """Hard-delete a session row.

        Args:
            id: UUID string of the session to delete.

        Returns:
            True if a row was deleted.

        Raises:
            DatabaseError: On delete failure.
        """
        try:
            client = get_db_client()
            result = (
                await client.table(self.TABLE)
                .delete()
                .eq("id", id)
                .execute()
            )
            deleted = bool(result.data)
            if deleted:
                logger.info("session.deleted", session_id=id)
            return deleted
        except Exception as exc:
            logger.error(
                "db.delete_failed",
                table=self.TABLE,
                operation="delete_session",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to delete {self.TABLE}: {exc}",
                operation="delete_session",
            ) from exc
