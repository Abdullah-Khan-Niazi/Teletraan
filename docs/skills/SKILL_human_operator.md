# HUMAN OPERATOR COMMUNICATION SKILL
## SKILL: human-operator | Version: 1.0 | Priority: MEDIUM

---

## PURPOSE

This skill defines the communication standards for HUMANS operating within
the TELETRAAN system: the distributor owner, sales reps (Channel B), and
the build agent developer. This covers admin commands, owner notifications,
escalation handling, and the conversational register for human-initiated
messages in the WhatsApp interface.

This is distinct from the TELETRAAN bot persona. Here we define how real
people communicate with and through the system.

---

## THREE HUMAN ROLES IN TELETRAAN

### ROLE 1 — DISTRIBUTOR OWNER (Admin)
Receives: daily summaries, order alerts, discount requests, escalations,
subscription notices, payment confirmations, anomaly alerts.
Sends: admin commands via WhatsApp (approve discount, suspend customer,
generate report, check stats).
Channel: Dedicated owner WhatsApp number registered in `distributors.owner_whatsapp_number`.

### ROLE 2 — SALES REP (Channel B)
Receives: customer order confirmations, target summaries, commission updates.
Sends: customer orders on behalf of clients, visit logs, prospect additions.
Channel: Channel B WhatsApp number. Rep's number registered in
`sales_reps.whatsapp_number`.

### ROLE 3 — BUILD AGENT (Developer)
Does not interact via WhatsApp. Operates via code, bash, git.
Communication style: technical, precise, imperative.
Covered separately in SKILL_git_protocol.md and SKILL_python_standards.md.

---

## OWNER ADMIN COMMANDS (WhatsApp Interface)

The owner interacts with TELETRAAN via WhatsApp commands sent to the admin
channel. Commands are parsed by `app/ai/prompts/admin_nlp.py` using NLP —
the owner does not need exact syntax.

### Command Reference

```
APPROVE DISCOUNT:
  Command: "APPROVE 10 [order_id]" or "10% discount do Ahmed ko"
  NLP understands: percentage + customer/order reference

REJECT DISCOUNT:
  Command: "REJECT [order_id]" or "Discount mat do"

SUSPEND CUSTOMER:
  Command: "SUSPEND [customer_name_or_phone]"
  Requires confirmation: "Confirm karna ho to CONFIRM likhein"

UNSUSPEND CUSTOMER:
  Command: "UNSUSPEND [customer_name_or_phone]"

VIEW TODAY'S SUMMARY:
  Command: "Aaj ka summary" or "Stats dikhao" or "Today"

VIEW PENDING ORDERS:
  Command: "Pending orders" or "Kya pending hai"

GENERATE EXCEL REPORT:
  Command: "Excel report chahiye [this week/this month/last month]"
  Response: PDF/Excel link sent to owner

MARK PAYMENT RECEIVED:
  Command: "Payment receive ho gayi [order_id]" or "[customer] ne PKR X diya"

UPDATE CREDIT LIMIT:
  Command: "[customer_name] ka credit PKR 50,000 kar do"

BROADCAST MESSAGE:
  Command: "Sabko message karo: [message text]"
  Requires confirmation before sending

RESUME BOT (after escalation):
  Command: "Resume [customer_phone]"
  Reactivates bot for an escalated customer session

HELP:
  Command: "Help" or "Commands"
  Response: brief list of available commands
```

### Admin Command Response Format
```
STANDARD ACKNOWLEDGMENT:
"✅ Ho gaya. [brief confirmation of what was done]"

CONFIRMATION REQUIRED:
"[Action description]. Confirm karna ho to *CONFIRM* likhein ⚠️"

ERROR:
"❌ [Brief reason]. [What owner should do instead]"

DATA RESPONSE (for reports/stats):
[Structured data in readable format, then:]
"Puri detail ke liye: [link]"
```

---

## OWNER NOTIFICATION TEMPLATES

Define all owner notifications in: `app/notifications/owner.py`

### Notification Design Rules

```
RULE 1 — LEAD WITH ACTION ITEM
If the notification requires owner action, state it in the first line.
"💬 Discount approve karna hai — reply APPROVE ya REJECT"

RULE 2 — DATA IS STRUCTURED, NOT NARRATIVE
Use consistent field: value format. Never write paragraphs for data.

RULE 3 — NOTIFICATIONS ARE SCANNABLE IN 5 SECONDS
Owner sees these between other WhatsApp messages. Make the key number
or decision visible at a glance.

RULE 4 — CRITICAL ALERTS USE ⚠️ PREFIX
Reserve ⚠️ for actions needed TODAY. Don't cry wolf.

RULE 5 — EVERY NOTIFICATION HAS A REFERENCE ID
Include order ID, customer name, or report date so owner can follow up.
```

### Notification Templates

```python
OWNER_NOTIFICATIONS = {

    "new_order": """📦 *Naya Order*
#{order_number} | {customer_name}
Items: {item_count} | Total: PKR {total_formatted}
Payment: {payment_method} ({payment_status})
{payment_link_or_dash}""",

    "order_confirmed_no_payment": """⚠️ *Order confirmed — Payment pending*
#{order_number} | {customer_name}
Total: PKR {total_formatted}
{days_pending} din se pending
Action: Follow up karein""",

    "discount_request": """💬 *Discount Request*
{customer_name} | Order #{order_number}
Requested: {requested_percent}%
Order Total: PKR {total_formatted}

Reply karna ho:
*APPROVE {suggested_percent}* ya *REJECT*""",

    "daily_summary": """📊 *Aaj ka Summary* — {date}

Orders: {confirmed_count} ✅ | {pending_count} ⏳ | {cancelled_count} ❌
Revenue: PKR {total_revenue_formatted}
Payments received: PKR {payments_received_formatted}
Outstanding: PKR {outstanding_formatted}

Top item: {top_item_name} ({top_item_qty} units)
New customers: {new_customer_count}""",

    "weekly_report_ready": """📋 *Weekly Report Ready* — {week_label}
Excel bheja ja raha hai. {link}""",

    "low_stock_alert": """⚠️ *Low Stock Alert*
{medicine_name} — sirf {quantity} {unit} bacha hai
Reorder threshold: {threshold} {unit}""",

    "subscription_expiry_7_days": """⚠️ Subscription *7 din mein* expire hogi.
Renew karein: {renewal_link}""",

    "subscription_expiry_1_day": """🔴 *URGENT* — Subscription kal expire hogi!
Renew karein: {renewal_link}""",

    "customer_escalation": """⚠️ *Customer Escalation*
{customer_name} | {customer_phone}
Reason: {escalation_reason}
Active order: {order_summary_or_none}

Please jaldi respond karein.""",

    "new_customer_registered": """👋 *Naya Customer*
{customer_name} — {shop_name}
Phone: {customer_phone}
First order lagane ki koshish ki""",

    "payment_mismatch": """⚠️ *Payment Mismatch*
Order #{order_number} | {customer_name}
Expected: PKR {expected_formatted}
Gateway reports: PKR {received_formatted}
Difference: PKR {diff_formatted}
Manual verification needed.""",

}
```

---

## CHANNEL B — SALES REP COMMUNICATION

Sales reps use a different register. They are field professionals.
Their interaction pattern is more command-driven than conversational.

### Sales Rep Commands

```
SUBMIT ORDER (on behalf of customer):
Rep sends customer's order details:
"Ali Medical Store: 20 strip paracetamol, 5 daba brufen, 10 seesaw amoxil"
TELETRAAN creates draft order attributed to Ali Medical Store.
Rep confirms → order logged.

CHECK TARGETS:
"Mera target kya hai" or "This month target"
Response: Monthly target, achieved %, remaining.

VIEW COMMISSION:
"Commission dikhao" or "Is mahine commission"
Response: Commission breakdown for current month.

LOG VISIT:
"Visit log karo: Ali Medical Store, order li hai, kal deliver hogi"
Response: "Visit logged ✅ #{visit_id}"

ADD PROSPECT:
"Naya client: Dr. Rehman Pharmacy, Gulshan, 0311-XXXXXXX"
Response: "Prospect add ho gaya ✅ Follow-up 3 din mein."

VIEW MY CUSTOMERS:
"Meri customer list" or "Mere saare clients"
Response: List with last order dates.
```

### Sales Rep Notification Templates

```python
SALES_REP_NOTIFICATIONS = {

    "order_submitted_confirmation": """✅ Order submit ho gayi
#{order_number} | {customer_name}
Total: PKR {total_formatted}
Status: Processing""",

    "commission_update": """💰 *Commission Update*
{month_label}

Sales target: PKR {target_formatted}
Achieved: PKR {achieved_formatted} ({percent}%)
Commission earned: PKR {commission_formatted}

{days_remaining} din remaining in month.""",

    "visit_reminder": """📍 *Visit Reminder*
{customer_name} ka visit {days_since} din se nahi hua.
Last order: {last_order_date_or_none}""",

    "daily_rep_summary": """📊 *Aaj aapka Summary*

Orders submitted: {orders_count}
Total value: PKR {total_value_formatted}
New prospects: {prospects_added}
Visits logged: {visits_logged}""",

}
```

---

## HUMAN REGISTER vs BOT REGISTER — QUICK REFERENCE

| Scenario | TELETRAAN Bot Says | Human/Admin Says |
|---|---|---|
| Confirm action | "Add ho gaya ✅" | "Theek hai, confirm ho gaya" |
| Error | "Masla aa gaya 🙏" | "Kuch technical issue tha, fix ho gaya" |
| Greeting | "Walaikum assalam! 😊" | "Assalam o alaikum! Kya haal hai?" |
| Apology | "Maazrat" (one word) | "Bhai maafi chahta hoon, bohot delay ho gayi" |
| Request for action | "CONFIRM likhein" | "Bhai confirm kar dein please" |
| Providing data | Structured, formatted | Conversational, with context |

---

## BUILD AGENT DEVELOPER COMMUNICATION

When the build agent writes README sections, onboarding guides, or inline
documentation meant to be read by the distributor owner or a future human
developer, the following register applies:

```
AUDIENCE: Non-technical business owner OR junior developer

STYLE:
- Short sentences
- Pakistani business context (reference rupees, JazzCash, WhatsApp as known entities)
- Step-by-step numbered lists for setup instructions
- Screenshots placeholder comments where visuals would help
- No jargon without explanation

EXAMPLE (good README section):
## Shuru Kaise Karein

1. Apna phone number Meta Business account mein register karein
2. .env file mein WHATSAPP_PHONE_NUMBER_ID fill karein
3. python run.py chalayein
4. Apna WhatsApp se "hello" bhejein test ke liye

EXAMPLE (bad README section):
## Getting Started

Initialize the WhatsApp Cloud API webhook endpoint by configuring
the HMAC verification middleware and registering the phone number ID
obtained from the Meta for Developers portal.
```

---

*End of SKILL: human-operator v1.0*
