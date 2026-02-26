#!/usr/bin/env python3
"""Seed the medicine catalog from a CSV file.

Reads a CSV with columns: medicine_name, generic_name, manufacturer,
category, unit, price_per_unit_paisas, stock_quantity
and inserts rows into the catalog table for the specified distributor.

Usage:
    python scripts/seed_catalog.py --file catalog.csv --distributor-id <uuid>
    python scripts/seed_catalog.py --file catalog.csv --distributor-id <uuid> --dry-run

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY in .env

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REQUIRED_COLUMNS = {
    "medicine_name",
    "generic_name",
    "manufacturer",
    "category",
    "unit",
    "price_per_unit_paisas",
    "stock_quantity",
}


def parse_csv(file_path: str) -> list[dict]:
    """Parse the catalog CSV file and validate columns."""
    path = Path(file_path)
    if not path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("ERROR: CSV file is empty or has no header.")
            sys.exit(1)

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            print(f"ERROR: Missing columns: {', '.join(missing)}")
            sys.exit(1)

        rows = list(reader)

    print(f"Parsed {len(rows)} rows from {file_path}")
    return rows


async def seed_catalog(
    file_path: str,
    distributor_id: str,
    dry_run: bool = False,
) -> None:
    """Insert catalog items from CSV into the database."""
    from app.db.client import get_db_client

    rows = parse_csv(file_path)

    if not rows:
        print("No rows to insert.")
        return

    payloads = []
    for i, row in enumerate(rows, 1):
        try:
            payload = {
                "id": str(uuid4()),
                "distributor_id": distributor_id,
                "medicine_name": row["medicine_name"].strip(),
                "generic_name": row.get("generic_name", "").strip() or None,
                "manufacturer": row.get("manufacturer", "").strip() or None,
                "category": row.get("category", "").strip() or None,
                "unit": row.get("unit", "strip").strip(),
                "price_per_unit_paisas": int(row["price_per_unit_paisas"]),
                "stock_quantity": int(row["stock_quantity"]),
                "is_active": True,
                "search_keywords": [
                    row["medicine_name"].strip().lower(),
                    row.get("generic_name", "").strip().lower(),
                ],
            }
            payloads.append(payload)
        except (ValueError, KeyError) as exc:
            print(f"  [SKIP] Row {i}: {exc}")

    if dry_run:
        print(f"\nDRY RUN — {len(payloads)} items would be inserted.")
        for p in payloads[:5]:
            print(f"  {p['medicine_name']} — {p['price_per_unit_paisas']} paisas")
        if len(payloads) > 5:
            print(f"  ... and {len(payloads) - 5} more")
        return

    client = get_db_client()
    batch_size = 50
    inserted = 0

    for start in range(0, len(payloads), batch_size):
        batch = payloads[start : start + batch_size]
        try:
            await client.table("catalog").insert(batch).execute()
            inserted += len(batch)
            print(f"  Inserted batch {start // batch_size + 1} ({len(batch)} items)")
        except Exception as exc:
            print(f"  [FAIL] Batch starting at row {start + 1}: {exc}")

    print(f"\nDone. Inserted {inserted}/{len(payloads)} catalog items.")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Seed the medicine catalog from CSV")
    parser.add_argument("--file", required=True, help="Path to CSV file")
    parser.add_argument("--distributor-id", required=True, help="UUID of the distributor")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't insert")
    args = parser.parse_args()
    asyncio.run(seed_catalog(args.file, args.distributor_id, args.dry_run))


if __name__ == "__main__":
    main()
