# PAYMENT GATEWAY INTEGRATION SKILL
## SKILL: payment-gateways | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines how to implement, verify, and maintain all payment gateway
integrations in TELETRAAN. Read this before implementing any gateway code.

---

## ARCHITECTURE PRINCIPLE

All gateways implement `PaymentGateway` abstract base class defined in
`app/payments/base.py`. The factory in `app/payments/factory.py` selects
the active gateway from environment. Business logic NEVER imports a specific
gateway class — it always goes through the factory.

```
Business Logic
     ↓
factory.get_gateway()
     ↓
PaymentGateway (abstract)
     ↓
[jazzcash | easypaisa | safepay | nayapay | bank_transfer | dummy]
```

---

## ABSTRACT BASE CLASS CONTRACT

Every gateway must fully implement all these methods:

```
generate_payment_link(
    amount_paisas: int,
    reference_id: str,
    description: str,
    payer_phone: str,
    metadata: dict = {}
) → PaymentLinkResponse

verify_webhook_signature(
    payload_bytes: bytes,
    headers: dict
) → bool

process_callback(
    payload: dict
) → PaymentCallbackResult

get_payment_status(
    gateway_transaction_id: str
) → PaymentStatusResult

cancel_payment(
    gateway_transaction_id: str
) → bool

get_gateway_name() → str

get_gateway_metadata() → dict

health_check() → bool
```

Response models (defined in base.py — not redefined per gateway):

```
PaymentLinkResponse:
    link_url: str
    gateway_order_id: str
    expires_at: datetime
    metadata: dict

PaymentCallbackResult:
    is_successful: bool
    amount_paisas: int
    gateway_transaction_id: str
    failure_reason: str | None
    raw_payload: dict

PaymentStatusResult:
    status: str  # ENUM: pending, completed, failed, expired, refunded
    amount_paisas: int
    paid_at: datetime | None
    raw_response: dict
```

---

## GATEWAY SPECIFICATIONS

### 1. JazzCash (app/payments/gateways/jazzcash.py)

**Auth mechanism:** HMAC-SHA256 integrity hash
**Payment flow:** Customer redirected to JazzCash payment page or USSD push
**Callback:** POST to /api/payments/jazzcash/callback

Hash generation for request:
- Concatenate fields in exact JazzCash-specified order separated by `&`
- HMAC-SHA256 with JAZZCASH_INTEGRITY_SALT as key
- Convert to uppercase hex string

Success indicator: `pp_ResponseCode == "000"`

Required env vars: JAZZCASH_MERCHANT_ID, JAZZCASH_PASSWORD,
JAZZCASH_INTEGRITY_SALT, JAZZCASH_API_URL

Callback verification: recompute hash from callback payload, compare to
`pp_SecureHash` in callback. Reject if mismatch.

### 2. EasyPaisa (app/payments/gateways/easypaisa.py)

**Auth mechanism:** Hash per EasyPaisa spec (MD5 or SHA-256 depending on endpoint)
**Payment flow:** EasyPaisa hosted page or mobile wallet OTP push
**Callback:** POST to /api/payments/easypaisa/callback

Success indicator: `status == "0000"` (EasyPaisa uses string "0000")

Required env vars: EASYPAISA_STORE_ID, EASYPAISA_HASH_KEY, EASYPAISA_API_URL

### 3. SafePay (app/payments/gateways/safepay.py)

**Auth mechanism:** Bearer token for API calls + HMAC-SHA256 for webhooks
**Payment flow:** Hosted checkout page (similar to Stripe Checkout)
**Callback:** POST to /api/payments/safepay/callback

API call to create checkout session:
- POST to SAFEPAY_API_URL/v1/checkout/create
- Bearer token: SAFEPAY_API_KEY
- Returns: `tracker.token` — use to construct checkout URL

Checkout URL format: `https://getsafepay.com/checkout/pay?tracker=<token>`

Webhook verification:
- Header: `x-sfpy-signature`
- HMAC-SHA256(payload_bytes, SAFEPAY_WEBHOOK_SECRET)
- Compare hex digest

Success indicator: `payload.type == "payment.success"` and
`payload.data.tracker.state == "CONFIRMED"`

Required env vars: SAFEPAY_API_KEY, SAFEPAY_SECRET_KEY, SAFEPAY_API_URL,
SAFEPAY_WEBHOOK_SECRET

### 4. NayaPay (app/payments/gateways/nayapay.py)

**Auth mechanism:** API key in header + request signing
**Payment flow:** QR code scan or NayaPay app redirect
**Callback:** POST to /api/payments/nayapay/callback

Payment initiation:
- POST to NAYAPAY_API_URL/api/v1/payment/initiate
- Headers: `X-Api-Key: NAYAPAY_API_KEY`
- Body includes: merchant_id, amount, reference_id, callback_url
- Returns: `payment_url` (QR or redirect) and `payment_id`

Callback verification:
- Compute HMAC-SHA256 of `payment_id + amount + status` with NAYAPAY_SECRET
- Compare to `signature` in callback

Success indicator: `status == "SUCCESS"`

Required env vars: NAYAPAY_MERCHANT_ID, NAYAPAY_API_KEY, NAYAPAY_SECRET,
NAYAPAY_API_URL

### 5. Bank Transfer (app/payments/gateways/bank_transfer.py)

**Auth mechanism:** None — manual flow
**Payment flow:** Show bank details → customer transfers → sends screenshot →
owner confirms → subscription extended

`generate_payment_link()` returns a message (not a URL) with bank details:
```
Bank: [BANK_NAME] - [BANK_BRANCH]
Account Title: [BANK_ACCOUNT_NAME]
Account Number: [BANK_ACCOUNT_NUMBER]
IBAN: [BANK_IBAN]
Amount: PKR [amount]
Reference: [reference_id]

Screenshot bhej dain payment ke baad is number pe.
```

`verify_webhook_signature()` always returns True (no webhook for this gateway).

`process_callback()` handles the owner's manual confirmation command
(received via Channel B: "confirm payment [distributor_number]").

Required env vars: BANK_ACCOUNT_NAME, BANK_ACCOUNT_NUMBER, BANK_IBAN,
BANK_NAME, BANK_BRANCH

### 6. Dummy Gateway (app/payments/gateways/dummy_gateway.py)

**PRODUCTION GUARD:** If APP_ENV == "production", raise RuntimeError immediately.
Never allow dummy gateway in production.

`generate_payment_link()` returns: `https://teletraan.local/dummy-pay/{ref_id}`

After DUMMY_GATEWAY_CONFIRM_DELAY_SECONDS, APScheduler fires dummy callback:
- If amount_paisas ends in 99: simulate failure
- Otherwise: simulate success

`verify_webhook_signature()` always returns True.

---

## IDEMPOTENCY — MANDATORY FOR ALL GATEWAYS

Before processing any callback in `process_callback()`:

```python
existing = await payment_repo.get_by_gateway_transaction_id(
    gateway_transaction_id=extracted_txn_id
)
if existing and existing.status == "completed":
    # Already processed — log duplicate and return success
    logger.warning("payment.duplicate_callback", txn_id=extracted_txn_id)
    await audit_repo.log(action="payment.duplicate_callback_ignored", ...)
    return PaymentCallbackResult(is_successful=True, ...)  # 200 to gateway
```

---

## POST-PAYMENT LIFECYCLE (app/payments/webhook_handlers.py)

After any gateway's `process_callback()` returns is_successful=True,
`webhook_handlers.py` runs this exact sequence:

1. Mark payment as completed in DB (payments table)
2. Log to audit_log (action: "payment.confirmed")
3. If payment_type = "subscription_fee" or "setup_fee":
   a. Extend distributor subscription_end by one month
   b. Update subscription_status to "active"
   c. Cancel any pending scheduled reminder messages
   d. Send confirmation message to distributor WhatsApp
   e. Notify owner via WhatsApp
4. If payment_type = "order_payment":
   a. Update order payment_status to "paid"
   b. Notify customer and distributor
5. Log to analytics_events with gateway name

---

## CALLBACK ENDPOINT PATTERN (app/api/payments.py)

Every gateway gets its own endpoint. All follow this pattern:

```
POST /api/payments/{gateway_name}/callback
  → Read raw body bytes for signature verification
  → Verify signature using gateway.verify_webhook_signature(body_bytes, headers)
  → If invalid: log, return HTTP 400, alert owner if repeated
  → Parse body to dict
  → Call gateway.process_callback(payload)
  → Call webhook_handlers.handle_successful_payment() or handle_failed_payment()
  → Return HTTP 200 (always — prevent retry storms even on business failures)
```

IMPORTANT: Always return HTTP 200 to the gateway even if business processing
fails. Log the error and handle async. Returning non-200 causes gateways
to retry indefinitely.

---

## SIGNATURE FAILURE ALERTING

Maintain a counter in DB (or Redis if available, otherwise use rate_limits table)
for failed signature verifications per gateway per IP.

If 3 or more failures in 10 minutes from same IP:
- Log to audit_log with action="payment.suspected_replay_attack"
- Send WhatsApp alert to owner

---

## TESTING GATEWAYS

For each gateway, write tests that verify:
1. `generate_payment_link()` produces correct payload structure
2. `verify_webhook_signature()` accepts valid signature
3. `verify_webhook_signature()` rejects tampered payload
4. `process_callback()` extracts correct fields from success payload
5. `process_callback()` handles failure payload correctly
6. Idempotency: second call with same transaction_id returns without re-processing

Use mocked httpx responses for all tests. Never call real gateway APIs in tests.

For dummy gateway:
1. Verify production guard raises RuntimeError when APP_ENV=production
2. Verify auto-confirm fires after configured delay
3. Verify failure simulation on 99-ending amounts

---

## ADDING A NEW GATEWAY IN THE FUTURE

1. Create `app/payments/gateways/new_gateway.py`
2. Implement all methods from PaymentGateway abstract class
3. Add to `app/payments/factory.py` GATEWAY_MAP dict
4. Add env vars to `app/core/config.py` as optional fields
5. Add callback endpoint to `app/api/payments.py`
6. Add env vars to `.env.example` with descriptions
7. Write all tests
8. Update `docs/payment_gateways.md`
9. Commit with scope `payments:`

Zero changes to any business logic. That is the design contract.
