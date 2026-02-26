# TELETRAAN — API Reference

## Base URL

```
https://<your-domain>/
```

All endpoints are served by the FastAPI application on port 8000 (configurable
via `APP_PORT`).

---

## Health

### `GET /health`

System health check. Probes the database connection.

**Response 200:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-01-15T12:00:00Z",
  "checks": {
    "database": "ok",
    "scheduler": "running"
  }
}
```

**Response 503:** Database unreachable or critical check failed.

---

## Webhook

### `GET /api/webhook`

Meta webhook verification endpoint. Returns the `hub.challenge` value when
`hub.verify_token` matches `META_VERIFY_TOKEN`.

**Query Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `hub.mode` | string | Must be `"subscribe"` |
| `hub.verify_token` | string | Must match `META_VERIFY_TOKEN` env var |
| `hub.challenge` | string | Challenge value to echo back |

**Response 200:** Plain text challenge value.
**Response 403:** Token mismatch.

---

### `POST /api/webhook`

Receive WhatsApp webhook events from Meta. The handler:

1. Verifies HMAC-SHA256 signature via `X-Hub-Signature-256` header
2. Parses the payload into structured message objects
3. Routes to Channel A or B based on phone number ID
4. Processes the message through the FSM pipeline

**Headers:**
| Header | Description |
|---|---|
| `X-Hub-Signature-256` | `sha256=<hex digest>` computed with `META_APP_SECRET` |

**Request Body:** Meta webhook event payload (JSON).

**Response 200:** Always returns `{"status": "ok"}` to acknowledge receipt.
**Response 400:** Invalid signature.

---

## Payment Callbacks

### `POST /api/payments/jazzcash/callback`

JazzCash payment result callback. Verifies the integrity hash and updates
the payment and order status.

### `POST /api/payments/easypaisa/callback`

EasyPaisa payment result callback. Verifies SHA256 hash signature.

### `POST /api/payments/safepay/callback`

SafePay webhook callback. Verifies webhook secret signature.

### `POST /api/payments/nayapay/callback`

NayaPay payment webhook. Verifies HMAC signature.

### `POST /api/payments/dummy/callback`

Dummy gateway callback (development only). Auto-confirms payments.

### `GET /api/payments/dummy/callback`

Dummy gateway redirect callback (GET-based confirmation).

### `GET /api/payments/status`

Check payment status by payment ID or order number.

**Query Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `payment_id` | string (UUID) | Payment record ID |
| `order_number` | string | Order number (alternative lookup) |

---

## Admin API

All admin endpoints require the `X-Admin-Key` header matching the
`ADMIN_API_KEY` environment variable.

### `POST /api/admin/distributors`

Create a new distributor account.

**Request Body:**
```json
{
  "business_name": "Ali Medical Distributors",
  "owner_name": "Ali Khan",
  "whatsapp_number": "+923001234567",
  "phone_number_id": "123456789",
  "waba_id": "987654321",
  "access_token": "EAAxxxxxxx...",
  "city": "Lahore",
  "subscription_plan_id": "uuid-of-plan"
}
```

**Response 201:** Created distributor object.

### `GET /api/admin/distributors`

List all active distributors.

**Response 200:** Array of distributor objects.

### `GET /api/admin/distributors/{distributor_id}`

Get detailed info for a specific distributor.

**Response 200:** Distributor object with subscription details.
**Response 404:** Distributor not found.

### `POST /api/admin/distributors/{distributor_id}/suspend`

Suspend a distributor (stops all processing for their numbers).

**Response 200:** Updated distributor object.

### `POST /api/admin/distributors/{distributor_id}/unsuspend`

Reactivate a suspended distributor.

**Response 200:** Updated distributor object.

### `POST /api/admin/distributors/{distributor_id}/extend`

Extend a distributor's subscription.

**Request Body:**
```json
{
  "days": 30
}
```

**Response 200:** Updated distributor with new expiry.

### `GET /api/admin/status`

System status overview: counts of distributors, active sessions, pending
orders, and scheduler job states.

**Response 200:**
```json
{
  "distributors_active": 5,
  "sessions_active": 12,
  "orders_pending": 8,
  "scheduler_running": true,
  "uptime_seconds": 86400
}
```

### `GET /api/admin/health/gateway`

Health check for the active payment gateway.

**Response 200:**
```json
{
  "gateway": "jazzcash",
  "status": "healthy",
  "last_check": "2025-01-15T12:00:00Z"
}
```

### `GET /api/admin/health/ai`

Health check for the active AI provider.

**Response 200:**
```json
{
  "provider": "gemini",
  "status": "healthy",
  "model": "gemini-1.5-flash"
}
```

### `POST /api/admin/inventory/sync`

Force an immediate inventory sync for a distributor.

**Request Body:**
```json
{
  "distributor_id": "uuid-of-distributor"
}
```

**Response 200:** Sync result summary.

### `POST /api/admin/announce`

Send an announcement message to all or selected distributors.

**Request Body:**
```json
{
  "message": "System maintenance at 2 AM PKT tonight.",
  "distributor_ids": ["uuid1", "uuid2"]
}
```

**Response 200:** Delivery summary.

---

## Authentication

| Endpoint Group | Auth Method |
|---|---|
| `/health` | None (public) |
| `/api/webhook` | HMAC-SHA256 signature verification |
| `/api/payments/*` | Gateway-specific signature verification |
| `/api/admin/*` | `X-Admin-Key` header |

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status | Meaning |
|---|---|
| 400 | Bad request / invalid signature |
| 403 | Authentication failed |
| 404 | Resource not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
