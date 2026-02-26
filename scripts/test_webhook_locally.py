#!/usr/bin/env python3
"""Send test webhook payloads to a local TELETRAAN instance.

Simulates Meta WhatsApp webhook events for development testing.
Generates valid HMAC-SHA256 signatures using META_APP_SECRET.

Usage:
    python scripts/test_webhook_locally.py --type text --message "Panadol 5 strip"
    python scripts/test_webhook_locally.py --type text --message "order status"
    python scripts/test_webhook_locally.py --type payment --gateway dummy
    python scripts/test_webhook_locally.py --type status_update

Requires:
    META_APP_SECRET in .env
    Local server running on http://localhost:8000

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)


def build_text_payload(
    message: str,
    from_number: str = "923001234567",
    phone_number_id: str = "TEST_PHONE_ID",
) -> dict:
    """Build a Meta webhook payload for a text message."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test Customer"},
                                    "wa_id": from_number,
                                }
                            ],
                            "messages": [
                                {
                                    "from": from_number,
                                    "id": "wamid.TEST123",
                                    "timestamp": "1234567890",
                                    "text": {"body": message},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def build_status_payload(
    message_id: str = "wamid.TEST123",
    status: str = "delivered",
) -> dict:
    """Build a Meta webhook payload for a message status update."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "TEST_PHONE_ID",
                            },
                            "statuses": [
                                {
                                    "id": message_id,
                                    "status": status,
                                    "timestamp": "1234567890",
                                    "recipient_id": "923001234567",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def build_payment_callback(gateway: str = "dummy") -> dict:
    """Build a payment callback payload."""
    if gateway == "dummy":
        return {
            "payment_id": "test-payment-123",
            "order_number": "ORD-2025-0001",
            "status": "completed",
            "amount_paisas": 50000,
        }
    if gateway == "jazzcash":
        return {
            "pp_ResponseCode": "000",
            "pp_ResponseMessage": "Transaction successful",
            "pp_Amount": "50000",
            "pp_TxnRefNo": "T20250115123456",
            "pp_BillReference": "ORD-2025-0001",
        }
    return {"status": "success", "reference": "test-ref"}


def sign_payload(payload_bytes: bytes, app_secret: str) -> str:
    """Generate HMAC-SHA256 signature for the payload."""
    return "sha256=" + hmac.new(
        app_secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()


def send_webhook(
    base_url: str,
    payload: dict,
    app_secret: str,
    endpoint: str = "/api/webhook",
) -> None:
    """Send the webhook payload with proper signature."""
    payload_bytes = json.dumps(payload).encode()
    signature = sign_payload(payload_bytes, app_secret)

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
    }

    url = f"{base_url}{endpoint}"
    print(f"Sending POST to {url}")
    print(f"Signature: {signature[:40]}...")

    try:
        response = httpx.post(url, content=payload_bytes, headers=headers, timeout=30)
        print(f"Response: {response.status_code}")
        print(f"Body: {response.text[:500]}")
    except httpx.ConnectError:
        print(f"ERROR: Could not connect to {base_url}. Is the server running?")
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Test TELETRAAN webhooks locally")
    parser.add_argument(
        "--type",
        choices=["text", "status_update", "payment"],
        default="text",
        help="Type of webhook event",
    )
    parser.add_argument("--message", default="Panadol 5 strip", help="Text message body")
    parser.add_argument("--gateway", default="dummy", help="Payment gateway for callbacks")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Server URL")
    parser.add_argument("--from", dest="from_number", default="923001234567", help="Sender number")

    args = parser.parse_args()

    # Load app secret
    from dotenv import load_dotenv
    import os

    load_dotenv()
    app_secret = os.getenv("META_APP_SECRET", "test-secret")

    if args.type == "text":
        payload = build_text_payload(args.message, args.from_number)
        send_webhook(args.base_url, payload, app_secret)
    elif args.type == "status_update":
        payload = build_status_payload()
        send_webhook(args.base_url, payload, app_secret)
    elif args.type == "payment":
        payload = build_payment_callback(args.gateway)
        endpoint = f"/api/payments/{args.gateway}/callback"
        send_webhook(args.base_url, payload, app_secret, endpoint)


if __name__ == "__main__":
    main()
