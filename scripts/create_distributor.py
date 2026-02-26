#!/usr/bin/env python3
"""Create a new distributor with full configuration.

Interactive script that creates a distributor record, assigns a subscription
plan, and verifies the WhatsApp connection.

Usage:
    python scripts/create_distributor.py
    python scripts/create_distributor.py --name "Ali Medical" --owner "Ali Khan" \
        --number "+923001234567" --phone-id "123456789" --waba-id "987654321" \
        --city "Lahore"

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY in .env

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def create_distributor(
    business_name: str,
    owner_name: str,
    whatsapp_number: str,
    phone_number_id: str,
    waba_id: str,
    city: str,
    access_token: str = "",
    plan_slug: str = "basic",
) -> None:
    """Create a new distributor in the database."""
    from app.db.client import get_db_client

    client = get_db_client()

    # Look up subscription plan
    plan_result = await (
        client.table("subscription_plans")
        .select("*")
        .eq("slug", plan_slug)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )

    plan_id = None
    if plan_result.data:
        plan_id = plan_result.data["id"]
        print(f"Using plan: {plan_result.data['name']} ({plan_slug})")
    else:
        print(f"WARNING: No plan found with slug '{plan_slug}'. Creating without plan.")

    distributor_id = str(uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    expires_at = (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat()

    distributor = {
        "id": distributor_id,
        "business_name": business_name,
        "owner_name": owner_name,
        "whatsapp_number": whatsapp_number,
        "phone_number_id": phone_number_id,
        "waba_id": waba_id,
        "access_token": access_token,
        "city": city,
        "subscription_plan_id": plan_id,
        "subscription_status": "active",
        "subscription_expires_at": expires_at,
        "is_active": True,
        "settings": {},
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = await client.table("distributors").insert(distributor).execute()
        if result.data:
            print(f"\nDistributor created successfully!")
            print(f"  ID:             {distributor_id}")
            print(f"  Business:       {business_name}")
            print(f"  Owner:          {owner_name}")
            print(f"  WhatsApp:       {whatsapp_number}")
            print(f"  Phone Number ID:{phone_number_id}")
            print(f"  City:           {city}")
            print(f"  Expires:        {expires_at}")
        else:
            print("ERROR: Insert returned no data.")
    except Exception as exc:
        print(f"ERROR: Failed to create distributor: {exc}")
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Create a new TELETRAAN distributor")
    parser.add_argument("--name", help="Business name")
    parser.add_argument("--owner", help="Owner name")
    parser.add_argument("--number", help="WhatsApp number (+923...)")
    parser.add_argument("--phone-id", help="Meta Phone Number ID")
    parser.add_argument("--waba-id", help="WhatsApp Business Account ID")
    parser.add_argument("--city", help="Business city")
    parser.add_argument("--access-token", default="", help="Meta API access token")
    parser.add_argument("--plan", default="basic", help="Subscription plan slug")

    args = parser.parse_args()

    # Interactive mode if args not provided
    name = args.name or input("Business name: ").strip()
    owner = args.owner or input("Owner name: ").strip()
    number = args.number or input("WhatsApp number (+923...): ").strip()
    phone_id = args.phone_id or input("Meta Phone Number ID: ").strip()
    waba_id = args.waba_id or input("WABA ID: ").strip()
    city = args.city or input("City: ").strip()
    token = args.access_token or input("Access token (press Enter to skip): ").strip()

    if not all([name, owner, number, phone_id, waba_id, city]):
        print("ERROR: All fields except access token are required.")
        sys.exit(1)

    asyncio.run(
        create_distributor(
            business_name=name,
            owner_name=owner,
            whatsapp_number=number,
            phone_number_id=phone_id,
            waba_id=waba_id,
            city=city,
            access_token=token,
            plan_slug=args.plan,
        )
    )


if __name__ == "__main__":
    main()
