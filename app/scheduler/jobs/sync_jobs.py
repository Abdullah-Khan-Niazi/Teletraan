"""Inventory sync scheduler jobs.

Contains the APScheduler job functions for:
- ``run_inventory_sync`` — syncs catalog for all active distributors
  that have a ``catalog_sync_url`` configured.
- ``scheduler_health_check`` — heartbeat to confirm scheduler is alive.

Job functions **never raise exceptions** to the scheduler.  All errors
are caught, logged, and silently consumed so one failure does not crash
the scheduler or prevent other jobs from running.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from app.core.config import get_settings
from app.core.constants import SyncSource, SyncStatus
from app.db.repositories import distributor_repo
from app.inventory.stock_service import stock_service
from app.inventory.sync_service import inventory_sync_service


# ═══════════════════════════════════════════════════════════════════
# INVENTORY SYNC JOB
# ═══════════════════════════════════════════════════════════════════


async def run_inventory_sync() -> None:
    """Sync inventory for every active distributor with a catalog URL.

    Called by APScheduler at the interval defined by
    ``INVENTORY_SYNC_INTERVAL_MINUTES``.

    Flow per distributor:
        1. Skip if no ``catalog_sync_url`` is set.
        2. Download and parse the file via InventorySyncService.
        3. If sync succeeded or partially succeeded, run post-sync
           stock checks (refresh is_in_stock flags, send low-stock alerts).
        4. Update ``catalog_last_synced`` on the distributor row.

    This function never raises — all errors are logged and execution
    continues to the next distributor.
    """
    logger.info("scheduler.inventory_sync.start")
    settings = get_settings()

    if not settings.enable_inventory_sync:
        logger.info("scheduler.inventory_sync.disabled")
        return

    try:
        distributors = await distributor_repo.get_active_distributors()
    except Exception as exc:
        logger.error(
            "scheduler.inventory_sync.fetch_distributors_failed",
            error=str(exc),
        )
        return

    synced_count = 0
    failed_count = 0

    for dist in distributors:
        dist_id = str(dist.id)

        # Skip distributors without a configured sync URL
        if not dist.catalog_sync_url:
            logger.debug(
                "scheduler.inventory_sync.no_url",
                distributor_id=dist_id,
                business_name=dist.business_name,
            )
            continue

        try:
            # ── Run sync ────────────────────────────────────────────
            result = await inventory_sync_service.sync_from_url(
                distributor_id=dist_id,
                file_url=dist.catalog_sync_url,
                sync_source=SyncSource.GOOGLE_DRIVE,
            )

            if result.status in (SyncStatus.COMPLETED, SyncStatus.PARTIAL):
                # ── Post-sync stock maintenance ─────────────────────
                try:
                    await stock_service.post_sync_stock_check(dist_id)
                except Exception as stock_exc:
                    logger.error(
                        "scheduler.inventory_sync.stock_check_failed",
                        distributor_id=dist_id,
                        error=str(stock_exc),
                    )

                # ── Update catalog_last_synced ──────────────────────
                try:
                    from app.db.models.distributor import DistributorUpdate

                    await distributor_repo.update(
                        dist_id,
                        DistributorUpdate(
                            catalog_last_synced=datetime.now(tz=timezone.utc),
                        ),
                    )
                except Exception as update_exc:
                    logger.error(
                        "scheduler.inventory_sync.update_timestamp_failed",
                        distributor_id=dist_id,
                        error=str(update_exc),
                    )

                synced_count += 1
                logger.info(
                    "scheduler.inventory_sync.distributor_complete",
                    distributor_id=dist_id,
                    status=result.status.value,
                    rows_processed=result.rows_processed,
                    inserted=result.rows_inserted,
                    updated=result.rows_updated,
                    failed=result.rows_failed,
                )
            else:
                failed_count += 1
                logger.warning(
                    "scheduler.inventory_sync.distributor_failed",
                    distributor_id=dist_id,
                    status=result.status.value,
                    errors_count=len(result.errors),
                )

        except Exception as exc:
            failed_count += 1
            logger.error(
                "scheduler.inventory_sync.distributor_error",
                distributor_id=dist_id,
                error=str(exc),
            )
            # Continue to next distributor — never crash the job
            continue

    logger.info(
        "scheduler.inventory_sync.complete",
        total_distributors=len(distributors),
        synced=synced_count,
        failed=failed_count,
    )


# ═══════════════════════════════════════════════════════════════════
# HEALTH CHECK JOB
# ═══════════════════════════════════════════════════════════════════


async def scheduler_health_check() -> None:
    """Log a heartbeat to confirm the scheduler is alive.

    Runs every 5 minutes.  Does nothing except log — useful for
    monitoring and debugging scheduler issues.
    """
    logger.info(
        "scheduler.heartbeat",
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )
