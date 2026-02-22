"""Discount rule repository — all database operations for discount_rules table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.exceptions import DatabaseError
from app.db.client import get_db_client
from app.db.models.discount_rule import DiscountRule, DiscountRuleCreate


class DiscountRuleRepository:
    """Repository for discount_rules table operations.

    All read operations require ``distributor_id`` for tenant isolation.
    """

    TABLE = "discount_rules"

    async def get_active_rules(
        self,
        distributor_id: str,
        *,
        catalog_id: str | None = None,
        customer_tags: list[str] | None = None,
    ) -> list[DiscountRule]:
        """Fetch active, currently valid discount rules.

        Filters by distributor, optionally by catalog_id and customer
        tags.  Returns rules sorted by priority descending (highest
        applied first).

        Args:
            distributor_id: Tenant scope.
            catalog_id: If provided, returns item-level rules matching
                this catalog ID plus order-level rules (catalog_id IS NULL).
                If None, returns only order-level rules.
            customer_tags: If provided, filter to rules whose
                applicable_customer_tags overlap with these tags.

        Returns:
            List of matching DiscountRule entities, sorted by
            priority descending.

        Raises:
            DatabaseError: On query failure.
        """
        try:
            client = get_db_client()
            now = datetime.now(tz=timezone.utc).isoformat()

            query = (
                client.table(self.TABLE)
                .select("*")
                .eq("distributor_id", distributor_id)
                .eq("is_active", True)
                .order("priority", desc=True)
            )

            result = await query.execute()

            rules = [DiscountRule.model_validate(row) for row in result.data]

            # Filter by validity window in Python since PostgREST
            # timestamp comparison syntax can be tricky
            now_dt = datetime.now(tz=timezone.utc)
            valid_rules: list[DiscountRule] = []
            for rule in rules:
                if rule.valid_from and rule.valid_from.astimezone(timezone.utc) > now_dt:
                    continue
                if rule.valid_until and rule.valid_until.astimezone(timezone.utc) < now_dt:
                    continue
                # Usage limit check
                if rule.usage_limit is not None and rule.usage_count >= rule.usage_limit:
                    continue
                valid_rules.append(rule)

            # Filter by catalog_id scope
            if catalog_id:
                valid_rules = [
                    r for r in valid_rules
                    if r.catalog_id is None or str(r.catalog_id) == catalog_id
                ]
            else:
                valid_rules = [
                    r for r in valid_rules
                    if r.catalog_id is None
                ]

            # Filter by customer tags overlap
            if customer_tags:
                tag_set = set(customer_tags)
                valid_rules = [
                    r for r in valid_rules
                    if not r.applicable_customer_tags
                    or tag_set.intersection(r.applicable_customer_tags)
                ]

            return valid_rules

        except Exception as exc:
            logger.error(
                "db.query_failed",
                table=self.TABLE,
                operation="get_active_rules",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to fetch {self.TABLE}: {exc}",
                operation="get_active_rules",
            ) from exc

    async def get_item_rules(
        self,
        distributor_id: str,
        catalog_id: str,
        *,
        customer_tags: list[str] | None = None,
    ) -> list[DiscountRule]:
        """Fetch discount rules applicable to a specific catalog item.

        Includes both item-specific rules (matching catalog_id) and
        order-level rules (catalog_id IS NULL) that could apply.

        Args:
            distributor_id: Tenant scope.
            catalog_id: The catalog item UUID.
            customer_tags: Optional customer tag filter.

        Returns:
            List of applicable DiscountRule entities.
        """
        return await self.get_active_rules(
            distributor_id,
            catalog_id=catalog_id,
            customer_tags=customer_tags,
        )

    async def increment_usage(self, rule_id: str) -> None:
        """Increment the usage count of a discount rule.

        Args:
            rule_id: UUID string of the rule.

        Raises:
            DatabaseError: On update failure.
        """
        try:
            client = get_db_client()
            # Fetch current count
            current = (
                await client.table(self.TABLE)
                .select("usage_count")
                .eq("id", rule_id)
                .maybe_single()
                .execute()
            )
            if current.data:
                new_count = (current.data.get("usage_count") or 0) + 1
                await (
                    client.table(self.TABLE)
                    .update({"usage_count": new_count})
                    .eq("id", rule_id)
                    .execute()
                )
                logger.debug(
                    "discount.usage_incremented",
                    rule_id=rule_id,
                    new_count=new_count,
                )
        except Exception as exc:
            logger.error(
                "db.update_failed",
                table=self.TABLE,
                operation="increment_usage",
                error=str(exc),
            )
            raise DatabaseError(
                f"Failed to increment usage for {self.TABLE}: {exc}",
                operation="increment_usage",
            ) from exc

    async def create(self, data: DiscountRuleCreate) -> DiscountRule:
        """Insert a new discount rule.

        Args:
            data: Validated creation payload.

        Returns:
            The created DiscountRule.

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
                rule_name=data.rule_name,
            )
            return DiscountRule.model_validate(result.data[0])
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
