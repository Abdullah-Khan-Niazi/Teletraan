# TELETRAAN Payment Gateway Abstraction — Implementation Spec

## Abstract Base Class (`app/payments/base.py`)

`PaymentGateway` abstract base class — all 6 gateway implementations must inherit this.

### Required Abstract Methods
```python
async def generate_payment_link(
    amount_paisas: int,
    reference_id: str,
    description: str,
    payer_phone: str,
) -> PaymentLinkResponse: ...

async def verify_webhook_signature(
    payload_bytes: bytes,
    headers: dict,
) -> bool: ...

async def process_callback(
    payload_dict: dict,
) -> PaymentCallbackResult: ...

async def get_payment_status(
    gateway_transaction_id: str,
) -> PaymentStatusResult: ...

async def cancel_payment(
    gateway_transaction_id: str,
) -> bool: ...

def get_gateway_name(self) -> str: ...
def get_gateway_metadata(self) -> dict: ...  # supported features, limits, etc.
async def health_check(self) -> bool: ...
```

### Response Types

**PaymentLinkResponse** must contain:
- `link_url: str`
- `gateway_order_id: str`
- `expires_at: datetime`
- `metadata: dict`

**PaymentCallbackResult** must contain:
- `is_successful: bool`
- `amount_paisas: int`
- `gateway_transaction_id: str`
- `failure_reason: str | None`
- `raw_payload: dict`

---

## Gateway Implementations (`app/payments/gateways/`)

| File | Gateway | Auth Method | Callback Path |
|---|---|---|---|
| `jazzcash.py` | JazzCash | HMAC-SHA256 integrity hash | `/api/payments/jazzcash/callback` |
| `easypaisa.py` | EasyPaisa | HMAC per EasyPaisa spec | `/api/payments/easypaisa/callback` |
| `safepay.py` | SafePay | Bearer token + HMAC webhook sig | `/api/payments/safepay/callback` |
| `nayapay.py` | NayaPay | API key + request signing | `/api/payments/nayapay/callback` |
| `bank_transfer.py` | Bank Transfer | Manual owner approval | N/A (no webhook) |
| `dummy_gateway.py` | Dummy | Internal — dev/test only | `/api/payments/dummy/callback` |

---

## Factory (`app/payments/factory.py`)
- Reads `ACTIVE_PAYMENT_GATEWAY` from environment
- Returns the default gateway instance
- Supports per-distributor `preferred_payment_gateway` override
- Multiple gateways can be active simultaneously
- Dummy gateway: **BLOCKED if `APP_ENV == production`** — factory enforces this

---

## Idempotency (all gateways MUST implement)
```
Before processing any callback:
1. Check payments table for gateway_transaction_id
2. If already processed (status = completed):
   → Return success without re-processing
   → Log duplicate callback to audit_log
   → Return HTTP 200 to gateway (important — never return error on duplicate)
```

---

## Signature Failure Handling
```
If verify_webhook_signature() returns False:
1. Log to audit_log with full headers and body preview
2. Return HTTP 400 (NOT 401 — avoid leaking auth information)
3. If 3+ failed verifications in 10 minutes from same IP:
   → Alert owner via WhatsApp
```

---

## Bank Transfer Flow (special — no API)
```
1. Bot sends bank account details (from BANK_* env vars) to customer
2. Customer transfers and sends screenshot via WhatsApp
3. Bot downloads image, stores in Supabase Storage
4. Notifies owner with screenshot + payer details
5. Owner sends confirmation command
6. Bot auto-extends subscription / confirms order
7. Full audit trail in payments + audit_log tables
```

## Dummy Gateway Behavior (dev/test only)
- Auto-confirm after `DUMMY_GATEWAY_CONFIRM_DELAY_SECONDS`
- Amounts ending in `99` paisas → auto-fail (failure simulation)
- Links expire after 15 minutes
- **Completely blocked when `APP_ENV = production`** — factory raises if attempted

---

## Analytics Tracking
Every payment event must log to `analytics_events`:
- `payment_gateway` — which gateway handled the transaction
- `event_type` — `payment.initiated`, `payment.completed`, `payment.failed`, etc.
- `properties` — amount, reference_id, gateway_transaction_id
