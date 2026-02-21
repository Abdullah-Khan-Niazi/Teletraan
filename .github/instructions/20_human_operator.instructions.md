---
applyTo: "app/notifications/**,app/**/*notification*.py,app/**/*operator*.py,app/**/*alert*.py"
---

# SKILL 20 — HUMAN OPERATOR COMMUNICATIONS
## Source: `docs/skills/SKILL_human_operator.md` (to be authored)

---

## PURPOSE

Defines all communications sent TO the human operator (distributor owner or sales rep):
- Order notifications
- Payment alerts
- Escalation handoffs
- System health alerts
- Daily/weekly business reports

---

## NOTIFICATION CHANNELS

All owner notifications sent via WhatsApp to `OWNER_WHATSAPP_NUMBER` env var.
Critical alerts also logged to `notifications_log` table with delivery status tracking.

---

## NOTIFICATION TYPES

### 1. New Order — send immediately on confirmation
```
📦 Naya Order — #ORD-2024-0847

Customer: Ahmed Medicals (****4567)
Items: 12 | Total: PKR 23,400
Payment: Pending (JazzCash)

Order dekhne ke liye: [Order ID]
```

### 2. Payment Received — send within 30 seconds
```
✅ Payment Mila!

Order: #ORD-2024-0847
Customer: Ahmed Medicals
Amount: PKR 23,400
Gateway: JazzCash
Ref: JC-2024-988877
Time: 3:47 PM

Dispatch ke liye tayar hai 🚚
```

### 3. Escalation Handoff — send immediately
```
⚠️ Customer Escalation

Customer: ****4567
Reason: [reason from escalation type]
Conversation: Last 3 messages shown

Jawab dene ke liye customer ko message karein:
+92300****4567
```

### 4. Payment Failed Alert
```
❌ Payment Failed

Order: #ORD-2024-0847
Customer: Ahmed Medicals
Amount: PKR 23,400
Gateway: JazzCash
Error: [error code]
Attempts: 3

Manual follow-up required.
```

### 5. System Alert (critical failures)
```
🚨 System Alert

Issue: Database connectivity lost
Time: 3:47 PM
Duration: 2 minutes

Auto-recovery attempted. Check dashboard.
```

---

## NOTIFICATION SERVICE (app/notifications/service.py)

```python
class NotificationService:
    """Service for sending WhatsApp notifications to the human operator."""

    async def notify_new_order(
        self,
        distributor_id: str,
        order: Order,
        customer: Customer,
    ) -> None:
        """Send new order notification to distributor owner."""

    async def notify_payment_received(
        self,
        distributor_id: str,
        payment: Payment,
        order: Order,
    ) -> None:
        """Send payment confirmation to distributor owner."""

    async def notify_escalation(
        self,
        distributor_id: str,
        customer: Customer,
        reason: str,
        recent_messages: list[str],
    ) -> None:
        """Send escalation handoff to human operator."""

    async def notify_system_alert(
        self,
        alert_type: str,
        message: str,
        is_critical: bool = False,
    ) -> None:
        """Send system health alert. Uses TELETRAAN_ADMIN_NUMBER for critical."""
```

---

## RULES

1. **Never block order processing to send owner notification** — use background task
2. **Always log to `notifications_log`** — track delivery status
3. **Critical alerts** (DB down, security events) → send immediately, don't batch
4. **Business notifications** → can be queued and retried on failure
5. **Rate limit** owner notifications — max 1 per order event type per order
6. **Phone numbers masked** in notification content — owner can see customer's number
   only in escalation handoffs (necessary for them to respond)
