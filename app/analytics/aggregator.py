"""Daily analytics aggregator — orchestrates all analytics services.

Pulls data from order, customer, and system analytics modules and
upserts a single analytics_daily row per distributor per date.
Also computes top items and customer events.

Run nightly at 23:50 PKT by the scheduler, or on-demand via admin API.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone, datetime
from uuid import UUID

from loguru import logger

from app.analytics.customer_analytics import (
    compute_customer_metrics,
    detect_churning_customers,
)
from app.analytics.order_analytics import compute_order_metrics, compute_top_items
from app.analytics.system_analytics import compute_system_metrics
from app.db.models.analytics import DailyAnalyticsCreate
from app.db.repositories.daily_analytics_repo import (
    DailyAnalyticsRepository,
    daily_analytics_repo,
)
from app.db.repositories.top_items_repo import (
    CustomerEventRepository,
    TopItemRepository,
    customer_event_repo,
    top_item_repo,
)


class DailyAnalyticsAggregator:
    """Computes and upserts daily analytics for all active distributors.

    Orchestrates:
    - Order metrics (volume, revenue, avg)
    - Customer metrics (new vs returning)
    - System metrics (AI cost, response times, fallbacks)
    - Top items (top N products by revenue)

    Usage::

        aggregator = DailyAnalyticsAggregator()
        await aggregator.compute_for_date(distributor_id, target_date)
    """

    def __init__(
        self,
        *,
        daily_repo: DailyAnalyticsRepository | None = None,
        items_repo: TopItemRepository | None = None,
        events_repo: CustomerEventRepository | None = None,
    ) -> None:
        self._daily_repo = daily_repo or daily_analytics_repo
        self._items_repo = items_repo or top_item_repo
        self._events_repo = events_repo or customer_event_repo

    async def compute_for_date(
        self,
        distributor_id: str,
        target_date: date,
    ) -> None:
        """Compute and upsert all analytics for one distributor+date.

        Args:
            distributor_id: Tenant scope.
            target_date: Calendar date to compute.
        """
        logger.info(
            "analytics.aggregation_started",
            distributor_id=distributor_id,
            date=str(target_date),
        )

        # Step 1: Order metrics
        order_metrics = await compute_order_metrics(distributor_id, target_date)
        confirmed_ids = order_metrics.pop("_confirmed_order_ids", [])
        customer_ids = order_metrics.pop("_customer_ids", [])

        # Step 2: Customer metrics
        customer_metrics = await compute_customer_metrics(
            distributor_id, target_date, customer_ids,
        )

        # Step 3: System metrics
        system_metrics = await compute_system_metrics(distributor_id, target_date)

        # Step 4: Upsert daily analytics
        payload = DailyAnalyticsCreate(
            distributor_id=UUID(distributor_id),
            date=target_date,
            **order_metrics,
            **customer_metrics,
            **system_metrics,
        )
        await self._daily_repo.upsert(payload)

        # Step 5: Top items
        top_items = await compute_top_items(
            distributor_id, target_date, confirmed_ids,
        )
        if top_items:
            await self._items_repo.replace_for_date(
                distributor_id, target_date, top_items,
            )

        logger.info(
            "analytics.aggregation_complete",
            distributor_id=distributor_id,
            date=str(target_date),
            orders_confirmed=order_metrics.get("orders_confirmed", 0),
            top_items=len(top_items),
        )

    async def compute_all_distributors(
        self,
        target_date: date,
    ) -> int:
        """Compute daily analytics for all active distributors.

        Args:
            target_date: Calendar date to compute.

        Returns:
            Number of distributors processed.
        """
        from app.db.client import get_db_client

        client = get_db_client()
        try:
            result = (
                await client.table("distributors")
                .select("id")
                .eq("is_active", True)
                .execute()
            )
        except Exception as exc:
            logger.error(
                "analytics.distributor_list_failed",
                error=str(exc),
            )
            return 0

        count = 0
        for row in result.data:
            dist_id = row["id"]
            try:
                await self.compute_for_date(dist_id, target_date)
                count += 1
            except Exception as exc:
                logger.error(
                    "analytics.aggregation_failed",
                    distributor_id=dist_id,
                    date=str(target_date),
                    error=str(exc),
                )

        logger.info(
            "analytics.batch_complete",
            date=str(target_date),
            distributors_processed=count,
        )
        return count

    async def run_churn_detection(self) -> int:
        """Run churn detection for all active distributors.

        Creates customer events for at-risk customers.

        Returns:
            Total number of churn events created.
        """
        from app.db.client import get_db_client

        client = get_db_client()
        try:
            result = (
                await client.table("distributors")
                .select("id")
                .eq("is_active", True)
                .execute()
            )
        except Exception as exc:
            logger.error(
                "analytics.churn_distributor_list_failed",
                error=str(exc),
            )
            return 0

        total_events = 0
        for row in result.data:
            dist_id = row["id"]
            try:
                events = await detect_churning_customers(dist_id)
                for event in events:
                    await self._events_repo.create(event)
                total_events += len(events)
            except Exception as exc:
                logger.error(
                    "analytics.churn_failed",
                    distributor_id=dist_id,
                    error=str(exc),
                )

        logger.info(
            "analytics.churn_batch_complete",
            total_events=total_events,
        )
        return total_events


# Module-level singleton
aggregator = DailyAnalyticsAggregator()
