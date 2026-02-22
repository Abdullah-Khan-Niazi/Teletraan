"""Billing service — discount rules engine, bonus units, delivery charges.

Calculates order bills by:
1. Applying item-level discount rules (bonus_units, percentage, flat)
2. Applying order-level discount rules
3. Computing delivery charges from zone, with free-delivery threshold
4. Populating PricingSnapshot on the OrderContext

All amounts are in paisas (PKR x 100) as integers to avoid
floating-point precision errors.  Discount rules are applied in
priority order (highest first).  Non-stackable rules are mutually
exclusive — only the highest-priority rule applies.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.constants import DiscountRequestStatus, DiscountRuleType
from app.db.models.delivery_zone import DeliveryZone
from app.db.models.discount_rule import DiscountRule
from app.db.models.order_context import (
    AutoAppliedDiscount,
    OrderContext,
    OrderItemDraft,
    PricingSnapshot,
)
from app.db.repositories.delivery_zone_repo import DeliveryZoneRepository
from app.db.repositories.discount_rule_repo import DiscountRuleRepository


# ═══════════════════════════════════════════════════════════════════
# SERVICE CLASS
# ═══════════════════════════════════════════════════════════════════


class BillingService:
    """Calculates order bills, applies discount rules, and computes
    delivery charges.

    All amounts are in paisas (PKR x 100) as integers.
    Discount rules are applied in priority order (highest first).
    Non-stackable rules are mutually exclusive — only the
    highest-priority rule applies per item.

    Args:
        discount_repo: Repository for fetching active discount rules.
        delivery_zone_repo: Repository for fetching zone delivery charges.
    """

    def __init__(
        self,
        discount_repo: DiscountRuleRepository | None = None,
        delivery_zone_repo: DeliveryZoneRepository | None = None,
    ) -> None:
        self._discount_repo = discount_repo or DiscountRuleRepository()
        self._delivery_zone_repo = delivery_zone_repo or DeliveryZoneRepository()

    # ── Main entry point ──────────────────────────────────────────

    async def calculate_bill(
        self,
        context: OrderContext,
        distributor_id: str,
        *,
        customer_tags: list[str] | None = None,
        delivery_zone_id: str | None = None,
    ) -> OrderContext:
        """Calculate the full bill for an order context.

        Applies discount rules, computes delivery charges, and updates
        the PricingSnapshot on the context.  Modifies the context
        in-place and returns it.

        Args:
            context: The order context to bill.
            distributor_id: Tenant scope.
            customer_tags: Customer tags for rule targeting.
            delivery_zone_id: Zone UUID for delivery charge lookup.

        Returns:
            The same OrderContext with updated pricing.
        """
        logger.info(
            "billing.calculate_start",
            item_count=len(context.items),
            distributor_id=distributor_id,
        )

        # Step 1: Apply item-level discounts
        auto_discounts: list[AutoAppliedDiscount] = []
        for item in context.items:
            if item.cancelled:
                continue
            item_auto = await self._apply_item_discounts(
                item, distributor_id, customer_tags=customer_tags,
            )
            auto_discounts.extend(item_auto)

        # Step 2: Apply order-level discount rules
        order_auto = await self._apply_order_discounts(
            context, distributor_id, customer_tags=customer_tags,
        )
        auto_discounts.extend(order_auto)

        # Step 3: Compute delivery charges
        delivery_charges = await self._compute_delivery_charges(
            context, distributor_id, delivery_zone_id,
        )

        # Step 4: Build final pricing snapshot
        active_items = [i for i in context.items if not i.cancelled]
        subtotal = sum(i.line_total_paisas for i in active_items)
        item_discounts = sum(i.discount_applied_paisas for i in active_items)
        order_discount = context.pricing_snapshot.order_discount_paisas
        total = subtotal - order_discount + delivery_charges

        context.pricing_snapshot = PricingSnapshot(
            subtotal_paisas=subtotal,
            item_discounts_paisas=item_discounts,
            order_discount_paisas=order_discount,
            auto_applied_discounts=auto_discounts,
            delivery_charges_paisas=delivery_charges,
            total_paisas=max(0, total),
            calculated_at=datetime.now(tz=timezone.utc),
        )

        logger.info(
            "billing.calculate_complete",
            subtotal=subtotal,
            item_discounts=item_discounts,
            order_discount=order_discount,
            delivery=delivery_charges,
            total=context.pricing_snapshot.total_paisas,
            auto_rules=len(auto_discounts),
        )

        return context

    # ── Item-level discount application ───────────────────────────

    async def _apply_item_discounts(
        self,
        item: OrderItemDraft,
        distributor_id: str,
        *,
        customer_tags: list[str] | None = None,
    ) -> list[AutoAppliedDiscount]:
        """Apply automatic discount rules to a single item.

        Rules are applied in priority order.  Non-stackable rules
        prevent subsequent rules from applying.

        Args:
            item: The order item draft.
            distributor_id: Tenant scope.
            customer_tags: Optional customer tag filter.

        Returns:
            List of auto-applied discounts for this item.
        """
        if not item.catalog_id:
            _recalculate_line_totals(item)
            return []

        rules = await self._discount_repo.get_item_rules(
            distributor_id,
            str(item.catalog_id),
            customer_tags=customer_tags,
        )

        # Filter to item-level rules only (catalog_id is not None)
        item_rules = [r for r in rules if r.catalog_id is not None]

        applied: list[AutoAppliedDiscount] = []
        total_discount_paisas = 0
        total_bonus_units = 0
        non_stackable_applied = False

        for rule in item_rules:
            if non_stackable_applied and not rule.is_stackable:
                continue

            # Check minimum quantity requirement
            if rule.minimum_order_quantity and item.quantity_requested < rule.minimum_order_quantity:
                continue

            discount_paisas = 0
            bonus = 0

            if rule.rule_type == DiscountRuleType.BONUS_UNITS.value:
                bonus = _calculate_bonus_units(
                    item.quantity_requested,
                    rule.buy_quantity or 0,
                    rule.get_quantity or 0,
                )
                if bonus > 0:
                    total_bonus_units += bonus
                    applied.append(AutoAppliedDiscount(
                        rule_id=rule.id,
                        rule_name=rule.rule_name or "",
                        amount_paisas=0,
                    ))

            elif rule.rule_type == DiscountRuleType.PERCENTAGE_DISCOUNT.value:
                if rule.discount_percentage:
                    line_value = item.price_per_unit_paisas * item.quantity_requested
                    discount_paisas = int(
                        line_value * rule.discount_percentage / 100
                    )
                    total_discount_paisas += discount_paisas
                    applied.append(AutoAppliedDiscount(
                        rule_id=rule.id,
                        rule_name=rule.rule_name or "",
                        amount_paisas=discount_paisas,
                    ))

            elif rule.rule_type == DiscountRuleType.FLAT_DISCOUNT.value:
                if rule.discount_flat_paisas:
                    discount_paisas = rule.discount_flat_paisas
                    total_discount_paisas += discount_paisas
                    applied.append(AutoAppliedDiscount(
                        rule_id=rule.id,
                        rule_name=rule.rule_name or "",
                        amount_paisas=discount_paisas,
                    ))

            if not rule.is_stackable and (discount_paisas > 0 or bonus > 0):
                non_stackable_applied = True

        # Update item fields
        item.bonus_units = total_bonus_units
        item.discount_applied_paisas = total_discount_paisas

        # Update discount_request status if there was an auto-apply
        if applied and item.discount_request:
            item.discount_request.status = DiscountRequestStatus.AUTO_APPLIED.value

        _recalculate_line_totals(item)

        return applied

    # ── Order-level discount application ──────────────────────────

    async def _apply_order_discounts(
        self,
        context: OrderContext,
        distributor_id: str,
        *,
        customer_tags: list[str] | None = None,
    ) -> list[AutoAppliedDiscount]:
        """Apply order-level discount rules.

        These are rules where ``catalog_id IS NULL``.

        Args:
            context: The full order context.
            distributor_id: Tenant scope.
            customer_tags: Optional customer tag filter.

        Returns:
            List of auto-applied order-level discounts.
        """
        rules = await self._discount_repo.get_active_rules(
            distributor_id,
            customer_tags=customer_tags,
        )
        # Only order-level rules (catalog_id is None)
        order_rules = [r for r in rules if r.catalog_id is None]

        active_items = [i for i in context.items if not i.cancelled]
        subtotal = sum(i.line_total_paisas for i in active_items)

        applied: list[AutoAppliedDiscount] = []
        total_discount = 0

        for rule in order_rules:
            # Check minimum value requirement
            if rule.minimum_order_value_paisas and subtotal < rule.minimum_order_value_paisas:
                continue

            discount_paisas = 0

            if rule.rule_type == DiscountRuleType.PERCENTAGE_DISCOUNT.value:
                if rule.discount_percentage:
                    discount_paisas = int(
                        subtotal * rule.discount_percentage / 100
                    )

            elif rule.rule_type == DiscountRuleType.FLAT_DISCOUNT.value:
                if rule.discount_flat_paisas:
                    discount_paisas = rule.discount_flat_paisas

            elif rule.rule_type == DiscountRuleType.MINIMUM_ORDER.value:
                # Minimum order discount — flat discount if order meets threshold
                if rule.discount_flat_paisas:
                    discount_paisas = rule.discount_flat_paisas

            if discount_paisas > 0:
                total_discount += discount_paisas
                applied.append(AutoAppliedDiscount(
                    rule_id=rule.id,
                    rule_name=rule.rule_name or "",
                    amount_paisas=discount_paisas,
                ))

                if not rule.is_stackable:
                    break

        context.pricing_snapshot.order_discount_paisas = total_discount

        return applied

    # ── Delivery charges ──────────────────────────────────────────

    async def _compute_delivery_charges(
        self,
        context: OrderContext,
        distributor_id: str,
        delivery_zone_id: str | None,
    ) -> int:
        """Compute delivery charges based on zone and order value.

        If the order subtotal exceeds the zone's free delivery
        threshold, delivery is free.

        Args:
            context: The order context.
            distributor_id: Tenant scope.
            delivery_zone_id: Zone UUID, or None (no charge).

        Returns:
            Delivery charge in paisas.
        """
        if not delivery_zone_id:
            return 0

        zone = await self._delivery_zone_repo.get_by_id(
            delivery_zone_id, distributor_id=distributor_id,
        )
        if not zone:
            logger.warning(
                "billing.zone_not_found",
                zone_id=delivery_zone_id,
            )
            return 0

        # Calculate current subtotal
        active_items = [i for i in context.items if not i.cancelled]
        subtotal = sum(i.line_total_paisas for i in active_items)

        # Check free delivery threshold
        if (
            zone.minimum_order_for_free_delivery_paisas
            and subtotal >= zone.minimum_order_for_free_delivery_paisas
        ):
            logger.debug(
                "billing.free_delivery",
                subtotal=subtotal,
                threshold=zone.minimum_order_for_free_delivery_paisas,
            )
            return 0

        return zone.delivery_charges_paisas

    # ── Manual discount application ───────────────────────────────

    def apply_manual_item_discount(
        self,
        item: OrderItemDraft,
        discount_paisas: int,
    ) -> None:
        """Apply a manually approved discount to an item.

        Updates the item's discount and recalculates line totals.

        Args:
            item: The order item.
            discount_paisas: Approved discount amount in paisas.
        """
        item.discount_applied_paisas = discount_paisas
        if item.discount_request:
            item.discount_request.status = DiscountRequestStatus.APPROVED.value
        _recalculate_line_totals(item)
        logger.info(
            "billing.manual_discount_applied",
            medicine=item.medicine_name,
            discount=discount_paisas,
        )

    def apply_manual_order_discount(
        self,
        context: OrderContext,
        discount_paisas: int,
    ) -> None:
        """Apply a manually approved order-level discount.

        Args:
            context: The order context.
            discount_paisas: Approved discount in paisas.
        """
        context.pricing_snapshot.order_discount_paisas = discount_paisas
        if context.order_level_discount_request:
            context.order_level_discount_request.status = (
                DiscountRequestStatus.APPROVED.value
            )
        logger.info(
            "billing.manual_order_discount",
            discount=discount_paisas,
        )

    # ── Bill display formatting ───────────────────────────────────

    def format_bill_preview(
        self,
        context: OrderContext,
        *,
        language: str = "roman_urdu",
    ) -> str:
        """Format the bill as a WhatsApp-friendly text preview.

        Args:
            context: OrderContext with calculated pricing.
            language: Language for headers.

        Returns:
            Formatted bill string.
        """
        snap = context.pricing_snapshot
        active_items = [i for i in context.items if not i.cancelled]

        if language == "english":
            lines = ["\U0001f4cb *Bill Preview*\n"]
        else:
            lines = ["\U0001f4cb *Bill Ka Preview*\n"]

        for i, item in enumerate(active_items, 1):
            name = item.medicine_name
            qty = item.quantity_requested
            unit = item.unit or "unit"
            price_rs = item.price_per_unit_paisas / 100
            line_rs = item.line_total_paisas / 100
            line = f"{i}. {name} x{qty} {unit} @ Rs.{price_rs:,.0f} = Rs.{line_rs:,.0f}"
            if item.bonus_units:
                line += f" (+{item.bonus_units} free)"
            if item.discount_applied_paisas > 0:
                disc_rs = item.discount_applied_paisas / 100
                line += f" (-Rs.{disc_rs:,.0f})"
            lines.append(line)

        lines.append("")
        sub_rs = snap.subtotal_paisas / 100
        lines.append(f"Subtotal: Rs.{sub_rs:,.0f}")

        if snap.item_discounts_paisas > 0:
            disc_rs = snap.item_discounts_paisas / 100
            lines.append(f"Item Discounts: -Rs.{disc_rs:,.0f}")

        if snap.order_discount_paisas > 0:
            odisc_rs = snap.order_discount_paisas / 100
            lines.append(f"Order Discount: -Rs.{odisc_rs:,.0f}")

        if snap.delivery_charges_paisas > 0:
            del_rs = snap.delivery_charges_paisas / 100
            lines.append(f"Delivery: +Rs.{del_rs:,.0f}")
        else:
            if language == "english":
                lines.append("Delivery: FREE")
            else:
                lines.append("Delivery: FREE \u2705")

        lines.append("")
        total_rs = snap.total_paisas / 100
        lines.append(f"*Total: Rs.{total_rs:,.0f}*")

        if snap.auto_applied_discounts:
            lines.append("")
            if language == "english":
                lines.append("_Auto-applied discounts:_")
            else:
                lines.append("_Automatic discounts:_")
            for ad in snap.auto_applied_discounts:
                if ad.amount_paisas > 0:
                    lines.append(f"  \u2022 {ad.rule_name}: -Rs.{ad.amount_paisas / 100:,.0f}")
                else:
                    lines.append(f"  \u2022 {ad.rule_name}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


def _calculate_bonus_units(
    ordered_qty: int,
    buy_qty: int,
    get_qty: int,
) -> int:
    """Calculate bonus units for a buy-X-get-Y-free rule.

    For example, buy 10 get 2 free: ordering 20 gives 4 bonus.

    Args:
        ordered_qty: Quantity ordered.
        buy_qty: Buy X quantity.
        get_qty: Get Y free quantity.

    Returns:
        Number of bonus units.
    """
    if buy_qty <= 0 or get_qty <= 0:
        return 0
    sets = ordered_qty // buy_qty
    return sets * get_qty


def _recalculate_line_totals(item: OrderItemDraft) -> None:
    """Recalculate line subtotal and total for an item.

    ``line_subtotal`` = price × quantity
    ``line_total`` = line_subtotal − discount

    Args:
        item: The order item draft to recalculate.
    """
    item.line_subtotal_paisas = item.price_per_unit_paisas * item.quantity_requested
    item.line_total_paisas = max(
        0,
        item.line_subtotal_paisas - item.discount_applied_paisas,
    )
