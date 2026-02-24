"""English notification and bot message templates.

Used when the customer or distributor has set their language preference
to English, or when the system detects English input.

All templates use ``.format()``-style placeholders.  Caller is
responsible for passing the correct keyword arguments.

Formatting rules:
    - Unicode emoji for visual structure: ✅ ⚠️ 📦 🔔 ❌
    - No markdown (WhatsApp API doesn't render it)
    - PKR format: "PKR 8,500"
    - Medicine names in English (brand name first)
"""

from __future__ import annotations


# ── Bot — Greetings ──────────────────────────────────────────────────

GREETING_NEW_CUSTOMER = (
    "Hello! 😊 Welcome to {distributor_name}.\n"
    "I'm TELETRAAN — your order assistant.\n"
    "Please share your name and shop name to get started."
)

GREETING_RETURNING_CUSTOMER = (
    "Hello {customer_name}! 😊 What can I help you with today?"
)

GREETING_RETURNING_CUSTOMER_NO_NAME = (
    "Hello! 😊 What can I help you with today?"
)

# ── Bot — Order Flow ─────────────────────────────────────────────────

ITEM_ADDED = (
    "💊 {medicine_name} × {quantity} {unit} — added ✅\nAnything else?"
)

ITEM_NOT_FOUND = "Couldn't find that in the catalog. Could you be more specific?"

ITEM_AMBIGUOUS = (
    "Found {match_count} matches:\n{match_list}\n"
    "Which one would you like? Reply with the number or name."
)

ITEM_OUT_OF_STOCK = (
    "⚠️ {medicine_name} is currently out of stock.\n"
    "Would you like something else?"
)

ITEM_LOW_STOCK = (
    "⚠️ Only {available} {unit} of {medicine_name} left.\n"
    "Add {available}?"
)

ITEM_REMOVED = "❌ {medicine_name} removed. Anything else?"

ORDER_SUMMARY = (
    "📦 Your Order:\n"
    "─────────────────\n"
    "{items_list}\n"
    "─────────────────\n"
    "Subtotal: PKR {subtotal}\n"
    "{discount_line}"
    "Delivery: PKR {delivery_charges}\n"
    "Total: PKR {total}\n"
    "\nConfirm or edit?"
)

ORDER_CONFIRMED = (
    "Order confirmed! ✅ #{order_number}\n"
    "Total: PKR {total}\n"
    "{delivery_info}"
)

ORDER_CANCELLED = "Order cancelled. ❌ No worries — start a new order anytime."

ORDER_TIMED_OUT = (
    "⏰ Your order session has timed out.\n"
    "Send any message to start a new order."
)

# ── Bot — Payment ────────────────────────────────────────────────────

PAYMENT_LINK = (
    "💳 Payment link:\n{payment_url}\n\n"
    "Amount: PKR {amount}\n"
    "Method: {method}\n"
    "Link expires in {expiry_minutes} minutes."
)

PAYMENT_RECEIVED = "✅ Payment received! PKR {amount}\nOrder #{order_number} is being processed."

PAYMENT_FAILED = (
    "❌ Payment failed.\n"
    "Please try again or use a different method."
)

PAYMENT_PENDING_REMINDER = (
    "⏳ Payment for order #{order_number} is still pending.\n"
    "PKR {amount} — pay via {method}:\n{payment_url}"
)

# ── Bot — Complaints ─────────────────────────────────────────────────

COMPLAINT_REGISTERED = (
    "📝 Complaint registered. Ticket: #{ticket_number}\n"
    "We'll look into it as soon as possible. 🙏"
)

COMPLAINT_UPDATE = (
    "🔔 Complaint #{ticket_number} update:\n"
    "Status: {status}\n{resolution_note}"
)

# ── Bot — Guidance (unsupported types) ───────────────────────────────

UNSUPPORTED_TYPE_GUIDANCE = (
    "I only understand text and voice messages.\n"
    "Please type your order or send a voice note. 🎙️"
)

UNSUPPORTED_MESSAGE = "I didn't understand that. Could you try text or voice? 🤔"

# ── Bot — Errors ─────────────────────────────────────────────────────

GENERIC_ERROR = "Something went wrong. Please try again in a moment. 🙏"

RATE_LIMIT_MESSAGE = "Please slow down — you're sending messages too quickly."

SESSION_ESCALATED = (
    "Your request has been forwarded to our team.\n"
    "Someone will respond shortly. 🙏"
)

# ── Bot — Discount ───────────────────────────────────────────────────

DISCOUNT_REQUEST_SENT = "Request sent ✅ It will be updated once the owner approves."

DISCOUNT_APPROVED = (
    "✅ Discount approved!\n"
    "{discount_detail}\n"
    "Updated total: PKR {new_total}"
)

DISCOUNT_REJECTED = "❌ Discount request was not approved. Original amount stands."

# ── Bot — Quick Reorder ──────────────────────────────────────────────

QUICK_REORDER_PROMPT = (
    "📋 Your last order:\n{last_order_summary}\n\n"
    "Would you like to repeat it?"
)

# ── Owner Notifications (English remains same style) ─────────────────

OWNER_NEW_ORDER = (
    "📦 New Order\n"
    "#{order_number} | {customer_name}\n"
    "Items: {item_count} | Total: PKR {total}\n"
    "Payment: {payment_method} ({payment_status})\n"
    "{payment_link_or_dash}"
)

OWNER_PAYMENT_RECEIVED = (
    "✅ Payment Received\n\n"
    "Order: #{order_number}\n"
    "Customer: {customer_name}\n"
    "Amount: PKR {amount}\n"
    "Gateway: {gateway}\n"
    "Ref: {reference}\n"
    "Time: {time}\n\n"
    "Ready for dispatch 🚚"
)

OWNER_PAYMENT_FAILED = (
    "❌ Payment Failed\n\n"
    "Order: #{order_number}\n"
    "Customer: {customer_name}\n"
    "Amount: PKR {amount}\n"
    "Gateway: {gateway}\n"
    "Error: {error}\n"
    "Attempts: {attempts}\n\n"
    "Manual follow-up required."
)

OWNER_ESCALATION = (
    "⚠️ Customer Escalation\n\n"
    "Customer: ****{phone_suffix}\n"
    "Reason: {reason}\n"
    "{conversation_snippet}\n\n"
    "Please respond promptly."
)

OWNER_DAILY_SUMMARY = (
    "📊 Today's Summary — {date}\n\n"
    "Orders: {confirmed} ✅ | {pending} ⏳ | {cancelled} ❌\n"
    "Revenue: PKR {revenue}\n"
    "Payments received: PKR {payments_received}\n"
    "Outstanding: PKR {outstanding}\n\n"
    "Top item: {top_item} ({top_qty} units)\n"
    "New customers: {new_customers}"
)

OWNER_LOW_STOCK = (
    "⚠️ Low Stock Alert\n"
    "{medicine_name} — only {quantity} {unit} remaining\n"
    "Reorder threshold: {threshold} {unit}"
)

OWNER_SUBSCRIPTION_7_DAYS = (
    "⚠️ Your subscription expires in 7 days.\n"
    "Renew here: {renewal_link}"
)

OWNER_SUBSCRIPTION_3_DAYS = (
    "⚠️ Your subscription expires in 3 days.\n"
    "Renew here: {renewal_link}"
)

OWNER_SUBSCRIPTION_1_DAY = (
    "🔴 URGENT — Your subscription expires tomorrow!\n"
    "Renew here: {renewal_link}"
)

OWNER_SUBSCRIPTION_EXPIRY_DAY = (
    "🛑 Your subscription expires TODAY.\n"
    "Renew immediately to avoid service interruption: {renewal_link}"
)

OWNER_SUBSCRIPTION_SUSPENDED = (
    "❌ Your subscription has been suspended.\n"
    "You have {grace_days} days to renew before cancellation.\n"
    "Renew here: {renewal_link}"
)

OWNER_SUBSCRIPTION_CANCELLED = (
    "🚫 Your subscription has been cancelled.\n"
    "Contact support to reactivate: {support_link}"
)

OWNER_DISCOUNT_REQUEST = (
    "💬 Discount Request\n"
    "{customer_name} | Order #{order_number}\n"
    "Requested: {requested_percent}%\n"
    "Order Total: PKR {total}\n\n"
    "Reply:\n"
    "APPROVE {suggested_percent} or REJECT"
)

OWNER_NEW_CUSTOMER = (
    "👋 New Customer\n"
    "{customer_name} — {shop_name}\n"
    "Phone: ****{phone_suffix}\n"
    "Attempting first order"
)

OWNER_PAYMENT_MISMATCH = (
    "⚠️ Payment Mismatch\n"
    "Order #{order_number} | {customer_name}\n"
    "Expected: PKR {expected}\n"
    "Gateway reports: PKR {received}\n"
    "Difference: PKR {difference}\n"
    "Manual verification needed."
)

OWNER_WEEKLY_REPORT = (
    "📋 Weekly Report Ready — {week_label}\n"
    "Sending Excel now."
)

OWNER_SYSTEM_ALERT = (
    "🚨 System Alert\n\n"
    "Issue: {issue}\n"
    "Time: {time}\n\n"
    "Auto-recovery attempted. Check dashboard."
)

# ── Sales Rep Notifications ──────────────────────────────────────────

REP_ORDER_SUBMITTED = (
    "✅ Order submitted\n"
    "#{order_number} | {customer_name}\n"
    "Total: PKR {total}\n"
    "Status: Processing"
)

REP_COMMISSION_UPDATE = (
    "💰 Commission Update\n"
    "{month_label}\n\n"
    "Sales target: PKR {target}\n"
    "Achieved: PKR {achieved} ({percent}%)\n"
    "Commission earned: PKR {commission}\n\n"
    "{days_remaining} days remaining in month."
)

REP_VISIT_REMINDER = (
    "📍 Visit Reminder\n"
    "No visit to {customer_name} in {days_since} days.\n"
    "Last order: {last_order_date}"
)

REP_DAILY_SUMMARY = (
    "📊 Your Summary Today\n\n"
    "Orders submitted: {orders_count}\n"
    "Total value: PKR {total_value}\n"
    "New prospects: {prospects_added}\n"
    "Visits logged: {visits_logged}"
)
