# TELETRAAN — Distributor Onboarding Guide

## Overview

This guide explains how to onboard a new medicine distributor onto TELETRAAN.
Each distributor gets their own WhatsApp Business number, catalog, customer
base, and configuration — fully isolated via multi-tenancy.

---

## Prerequisites

Before onboarding, the distributor must have:

1. **WhatsApp Business API access** — registered phone number via Meta
2. **Phone Number ID** — from Meta Developer Dashboard
3. **WABA ID** — WhatsApp Business Account ID
4. **Access Token** — permanent token for the Meta API
5. **Medicine catalog** — CSV/Excel file with product data

---

## Step 1: Create Subscription Plan (if needed)

If the distributor's plan doesn't exist yet, create one via the database:

```sql
INSERT INTO subscription_plans (
    id, name, slug, description, price_paisas,
    duration_days, max_customers, max_orders_per_day,
    features, is_active
) VALUES (
    gen_random_uuid(), 'Basic Plan', 'basic',
    'Up to 100 customers, 50 orders/day',
    500000,  -- PKR 5,000
    30, 100, 50, '{"voice": true, "reports": true}', true
);
```

---

## Step 2: Create Distributor

### Via Admin API

```bash
curl -X POST https://your-domain.com/api/admin/distributors \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -d '{
    "business_name": "Ali Medical Distributors",
    "owner_name": "Ali Khan",
    "whatsapp_number": "+923001234567",
    "phone_number_id": "123456789012345",
    "waba_id": "987654321098765",
    "access_token": "EAAxxxxxxxxxx...",
    "city": "Lahore",
    "subscription_plan_id": "uuid-of-plan"
  }'
```

### Via Script

```bash
python scripts/create_distributor.py \
  --name "Ali Medical Distributors" \
  --owner "Ali Khan" \
  --number "+923001234567" \
  --phone-id "123456789012345" \
  --waba-id "987654321098765" \
  --city "Lahore"
```

---

## Step 3: Configure WhatsApp Webhook

In the Meta Developer Dashboard for the distributor's app:

1. Go to WhatsApp → Configuration
2. Set Callback URL: `https://your-domain.com/api/webhook`
3. Set Verify Token: same as your `META_VERIFY_TOKEN`
4. Subscribe to: `messages`

TELETRAAN's channel router will identify the distributor by their
`phone_number_id` and route messages to Channel A.

---

## Step 4: Import Medicine Catalog

### Via CSV

Prepare a CSV file with columns:

```csv
medicine_name,generic_name,manufacturer,category,unit,price_per_unit_paisas,stock_quantity
Panadol,Paracetamol,GSK,Tablet,strip,15000,500
Augmentin 625mg,Amoxicillin+Clavulanate,GSK,Tablet,strip,45000,200
```

```bash
python scripts/seed_catalog.py \
  --file catalog.csv \
  --distributor-id <distributor-uuid>
```

### Via Admin API

Individual items can be added via the admin interface or direct DB insert.

---

## Step 5: Verify Setup

### Send Test Message

Send a WhatsApp message to the distributor's number from any phone.
You should receive a greeting response from TELETRAAN.

### Check Admin Status

```bash
curl https://your-domain.com/api/admin/distributors/<id> \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

### Test Order Flow

1. Send "Panadol 5 strip" to the distributor's number
2. Verify order appears in the database
3. Confirm pricing is calculated correctly

---

## Step 6: Configure Optional Features

### Enable Payment Gateway

Set the appropriate payment gateway environment variables
(see `docs/payment_gateways.md`).

### Configure Reports

Reports are generated automatically if `ENABLE_EXCEL_REPORTS=true` and
`ENABLE_ANALYTICS=true`. The distributor receives:

- Daily morning/evening Excel reports
- Weekly summary
- Monthly analytics

### Set Delivery Zones

```sql
INSERT INTO delivery_zones (
    id, distributor_id, name, delivery_charge_paisas,
    estimated_hours, is_active
) VALUES (
    gen_random_uuid(), '<distributor-uuid>',
    'Lahore City', 20000, 4, true
);
```

---

## Managing Distributors

### Suspend

```bash
curl -X POST \
  https://your-domain.com/api/admin/distributors/<id>/suspend \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

### Extend Subscription

```bash
curl -X POST \
  https://your-domain.com/api/admin/distributors/<id>/extend \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -d '{"days": 30}'
```

### View All Distributors

```bash
curl https://your-domain.com/api/admin/distributors \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

---

## Troubleshooting

| Issue | Resolution |
|---|---|
| Messages not received | Check phone_number_id matches, webhook subscribed |
| "Unknown distributor" | Verify distributor record exists and is_active=true |
| Catalog empty | Run seed script or check catalog import |
| Orders not pricing | Verify catalog prices are in paisas |
| Reports not sending | Check ENABLE_EXCEL_REPORTS and RESEND_API_KEY |
