#!/usr/bin/env python3
"""Run all Supabase migrations in order.

Reads SQL files from app/db/migrations/ sorted by filename prefix (001_, 002_, …)
and executes them against the configured Supabase PostgreSQL database.

Usage:
    python scripts/run_migrations.py
    python scripts/run_migrations.py --dry-run

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY in .env

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_migrations(dry_run: bool = False) -> None:
    """Execute all migration SQL files in order."""
    from app.core.config import get_settings
    from app.db.client import get_db_client

    settings = get_settings()
    migrations_dir = Path(__file__).resolve().parent.parent / "app" / "db" / "migrations"

    if not migrations_dir.exists():
        print(f"ERROR: Migrations directory not found: {migrations_dir}")
        sys.exit(1)

    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        print("No migration files found.")
        return

    print(f"Found {len(sql_files)} migration files.")
    print(f"Database: {settings.SUPABASE_URL}")
    print()

    if dry_run:
        print("DRY RUN — no changes will be applied.\n")

    client = get_db_client()
    applied = 0
    failed = 0

    for sql_file in sql_files:
        name = sql_file.name
        sql_content = sql_file.read_text(encoding="utf-8")

        if dry_run:
            print(f"  [DRY] {name} ({len(sql_content)} chars)")
            continue

        try:
            await client.postgrest.rpc("exec_sql", {"query": sql_content}).execute()
            print(f"  [OK]  {name}")
            applied += 1
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            failed += 1

    print()
    if dry_run:
        print(f"Dry run complete. {len(sql_files)} migrations would be applied.")
    else:
        print(f"Applied: {applied}, Failed: {failed}, Total: {len(sql_files)}")

    if failed > 0:
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run Supabase migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List migrations without executing",
    )
    args = parser.parse_args()
    asyncio.run(run_migrations(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
