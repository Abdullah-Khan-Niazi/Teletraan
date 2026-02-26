# TELETRAAN — Payment Gateways Integration Guide

## Overview

TELETRAAN supports 6 payment gateways, configured via environment variables.
Only one gateway is active at a time, set by `ACTIVE_PAYMENT_GATEWAY`.

All gateways implement the same `PaymentGateway` base interface:
- `initiate_payment()` — create a payment link/request
- `verify_callback()` — verify incoming webhook/callback
- `check_status()` — query payment status
- `get_health()` — gateway health check

All monetary amounts are in **paisas** (PKR × 100).

---

## Gateway Selection

```env
ACTIVE_PAYMENT_GATEWAY=jazzcash   # Options: jazzcash, easypaisa, safepay, nayapay, bank_transfer, dummy
```

The `PaymentFactory` instantiates the correct gateway at startup.

---

## JazzCash

Pakistan's leading mobile wallet. Uses HMAC-SHA256 for request integrity.

### Environment Variables

```env
JAZZCASH_MERCHANT_ID=MC12345
JAZZCASH_PASSWORD=your-password
JAZZCASH_INTEGRITY_SALT=your-salt
JAZZCASH_API_URL=https://sandbox.jazzcash.com.pk/ApplicationAPI/API/Payment/DoTransaction
```

### Flow

1. App sends POST to JazzCash API with signed payload
2. Customer redirected to JazzCash payment page
3. JazzCash POSTs result to `/api/payments/jazzcash/callback`
4. App verifies HMAC integrity hash and updates payment status

### Signature

```
HMAC-SHA256(integrity_salt + sorted_parameter_values)
```

---

## EasyPaisa

Telenor's mobile payment platform.

### Environment Variables

```env
EASYPAISA_STORE_ID=your-store-id
EASYPAISA_HASH_KEY=your-hash-key
EASYPAISA_API_URL=https://easypay.easypaisa.com.pk/easypay/Index.jsf
```

### Flow

1. App generates payment URL with signed parameters
2. Customer redirected to EasyPaisa
3. EasyPaisa POSTs result to `/api/payments/easypaisa/callback`
4. App verifies SHA256 hash: `SHA256(amount + order_id + store_id + hash_key)`

### Signature

```python
SHA256(amount + order_id + store_id + hash_key)  # amount FIRST
```

---

## SafePay

Modern online payment gateway with API-first design.

### Environment Variables

```env
SAFEPAY_API_KEY=your-api-key
SAFEPAY_SECRET_KEY=your-secret-key
SAFEPAY_API_URL=https://api.getsafepay.com
SAFEPAY_WEBHOOK_SECRET=your-webhook-secret
```

### Flow

1. App creates checkout session via SafePay API
2. Customer pays on SafePay-hosted page
3. SafePay sends webhook to `/api/payments/safepay/callback`
4. App verifies webhook signature using `SAFEPAY_WEBHOOK_SECRET`

---

## NayaPay

Digital wallet with QR code and online payment support.

### Environment Variables

```env
NAYAPAY_MERCHANT_ID=your-merchant-id
NAYAPAY_API_KEY=your-api-key
NAYAPAY_SECRET=your-secret
NAYAPAY_API_URL=https://api.nayapay.com
```

### Flow

1. App creates payment request via NayaPay API
2. Customer pays via NayaPay app or web
3. NayaPay sends webhook to `/api/payments/nayapay/callback`
4. App verifies HMAC signature and updates status

---

## Bank Transfer

Manual bank transfer with receipt confirmation.

### Environment Variables

```env
BANK_ACCOUNT_NAME=Ali Medical Distributors
BANK_ACCOUNT_NUMBER=1234567890
BANK_IBAN=PK36MEZN0001234567890
BANK_NAME=Meezan Bank
BANK_BRANCH=Lahore Main
```

### Flow

1. App sends bank account details to customer via WhatsApp
2. Customer transfers manually and sends receipt photo
3. Distributor confirms payment manually
4. No automatic callback — status updated via admin

---

## Dummy Gateway (Development Only)

Auto-confirms payments for testing. **Blocked in production** (`APP_ENV=production`).

### Environment Variables

```env
DUMMY_GATEWAY_AUTO_CONFIRM=true
DUMMY_GATEWAY_CONFIRM_DELAY_SECONDS=10
```

### Flow

1. App creates dummy payment (no external API call)
2. If `AUTO_CONFIRM=true`, payment auto-confirmed after delay
3. Callback endpoint accepts both POST and GET

---

## Payment Callback URLs

All callbacks are at:

```
POST /api/payments/{gateway}/callback
```

| Gateway | Callback Path |
|---|---|
| JazzCash | `/api/payments/jazzcash/callback` |
| EasyPaisa | `/api/payments/easypaisa/callback` |
| SafePay | `/api/payments/safepay/callback` |
| NayaPay | `/api/payments/nayapay/callback` |
| Dummy | `/api/payments/dummy/callback` (POST + GET) |

Set `PAYMENT_CALLBACK_BASE_URL` to your production domain:

```env
PAYMENT_CALLBACK_BASE_URL=https://your-app.onrender.com
```

---

## Adding a New Gateway

1. Create `app/payments/gateways/new_gateway.py`
2. Extend `PaymentGateway` base class
3. Implement all 4 methods: `initiate_payment`, `verify_callback`, `check_status`, `get_health`
4. Register in `app/payments/factory.py`
5. Add callback route in `app/api/payments.py`
6. Add env vars to `app/core/config.py` Settings class
7. Update `.env.example`

---

## Testing Payments

### Local Testing

```bash
# Use dummy gateway
ACTIVE_PAYMENT_GATEWAY=dummy

# Send test callback
python scripts/test_webhook_locally.py --type payment --gateway dummy
```

### Production Testing

1. Set gateway to `dummy` initially
2. Create a test order
3. Verify payment flow end-to-end
4. Switch to real gateway after verification
