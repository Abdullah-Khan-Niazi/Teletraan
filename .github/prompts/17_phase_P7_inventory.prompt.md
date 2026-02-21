# Phase 7 — Inventory Sync

**Prerequisites:** Phase 6 complete and verified.
**Verify before P8:** Full sync cycle working — upload file → DB update → low stock alert sent.

## Steps (execute in order, commit after each)

1. Implement `app/inventory/sync_service.py` — Excel/CSV sync with validation, upsert, and error logging  
   (read from Google Drive URL or Supabase Storage, validate columns, upsert catalog, write to `inventory_sync_log`)  
   → Commit: `"inventory: implement Excel/CSV sync with validation, upsert, and error logging"`

2. Implement `app/inventory/stock_service.py` — stock level checks, `is_in_stock` updates, low-stock detection  
   (check `stock_quantity` vs `low_stock_threshold`, trigger alerts, update `is_in_stock` flag)  
   → Commit: `"inventory: add stock level checks, is_in_stock updates, and low-stock detection"`

3. Implement APScheduler inventory sync job in `app/scheduler/jobs/sync_jobs.py`  
   Per-distributor interval: reads `INVENTORY_SYNC_INTERVAL_MINUTES` and per-distributor config  
   → Commit: `"scheduler: add inventory sync job with per-distributor interval configuration"`

4. Test full sync cycle — upload Excel → scheduler runs → DB updated → low stock alert sent  
   → Commit: `"tests: verify inventory sync pipeline from upload to DB update to alert"`

5. **PHASE 7 COMPLETE** Commit: `"phase-7: inventory sync automation complete and tested"`
