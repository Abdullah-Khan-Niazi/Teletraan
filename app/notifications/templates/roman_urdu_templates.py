"""Roman Urdu notification and bot message templates.

This is the **default** language for TELETRAAN.  Most Pakistani medicine
distributors and retailers communicate in Roman Urdu on WhatsApp.

All templates use ``.format()``-style placeholders.  Caller is
responsible for passing the correct keyword arguments.

Formatting rules (from SKILL_voice_and_tone):
    - Use Unicode emoji for visual structure: ✅ ⚠️ 📦 🔔 ❌
    - No markdown (WhatsApp doesn't render it in API messages)
    - PKR format: "PKR 8,500" not "Rs 8500"
    - Medicines in English (brand name first)
    - Max 800 chars conversational, 4000 for summaries
"""

from __future__ import annotations


# ── Bot — Greetings ──────────────────────────────────────────────────

GREETING_NEW_CUSTOMER = (
    "Assalam o Alaikum! 😊 {distributor_name} mein khush aamdeed.\n"
    "Main TELETRAAN hoon — aapka order assistant.\n"
    "Apna naam aur dukan ka naam bata dein taake hum start karein."
)

GREETING_RETURNING_CUSTOMER = (
    "Walaikum assalam {customer_name}! 😊 Kya chahiye aaj?"
)

GREETING_RETURNING_CUSTOMER_NO_NAME = (
    "Walaikum assalam! 😊 Kya chahiye aaj?"
)

# ── Bot — Order Flow ─────────────────────────────────────────────────

ITEM_ADDED = (
    "💊 {medicine_name} × {quantity} {unit} — add ho gaya ✅\nAur kuch?"
)

ITEM_NOT_FOUND = "Yeh naam catalog mein nahi mila. Thora aur wazeh karein?"

ITEM_AMBIGUOUS = (
    "Yeh {match_count} medicines milin:\n{match_list}\n"
    "Konsi chahiye? Number ya naam batayein."
)

ITEM_OUT_OF_STOCK = (
    "⚠️ {medicine_name} abhi stock mein nahi hai.\n"
    "Koi aur medicine chahiye?"
)

ITEM_LOW_STOCK = (
    "⚠️ {medicine_name} sirf {available} {unit} bacha hai.\n"
    "{available} add karein?"
)

ITEM_REMOVED = "❌ {medicine_name} hata diya gaya. Aur kuch?"

ORDER_SUMMARY = (
    "📦 Aapka Order:\n"
    "─────────────────\n"
    "{items_list}\n"
    "─────────────────\n"
    "Subtotal: PKR {subtotal}\n"
    "{discount_line}"
    "Delivery: PKR {delivery_charges}\n"
    "Total: PKR {total}\n"
    "\nConfirm karein ya edit karein?"
)

ORDER_CONFIRMED = (
    "Order confirm! ✅ #{order_number}\n"
    "Total: PKR {total}\n"
    "{delivery_info}"
)

ORDER_CANCELLED = "Order cancel ho gayi. ❌ Koi masla nahi — jab chahein naya order lagayein."

ORDER_TIMED_OUT = (
    "⏰ Aapka order session time out ho gaya.\n"
    "Dobara order shuru karne ke liye koi bhi message bhejein."
)

# ── Bot — Payment ────────────────────────────────────────────────────

PAYMENT_LINK = (
    "💳 Payment ka link:\n{payment_url}\n\n"
    "Amount: PKR {amount}\n"
    "Payment method: {method}\n"
    "Yeh link {expiry_minutes} minute mein expire hoga."
)

PAYMENT_RECEIVED = "✅ Payment mil gayi! PKR {amount}\nOrder #{order_number} process ho raha hai."

PAYMENT_FAILED = (
    "❌ Payment nahi ho payi.\n"
    "Dobara try karein ya alag method use karein."
)

PAYMENT_PENDING_REMINDER = (
    "⏳ Order #{order_number} ki payment abhi tak pending hai.\n"
    "PKR {amount} — {method} se pay karein:\n{payment_url}"
)

# ── Bot — Complaints ─────────────────────────────────────────────────

COMPLAINT_REGISTERED = (
    "📝 Complaint register ho gayi. Ticket: #{ticket_number}\n"
    "Jaldi se jaldi dekha jayega. 🙏"
)

COMPLAINT_UPDATE = (
    "🔔 Complaint #{ticket_number} update:\n"
    "Status: {status}\n{resolution_note}"
)

# ── Bot — Guidance (unsupported types) ───────────────────────────────

UNSUPPORTED_TYPE_GUIDANCE = (
    "Main sirf text aur voice messages samajhta hoon.\n"
    "Apna order text mein bhejein ya voice note record karein. 🎙️"
)

UNSUPPORTED_MESSAGE = "Yeh samajh nahi aaya. Text ya voice mein batayein? 🤔"

# ── Bot — Errors ─────────────────────────────────────────────────────

GENERIC_ERROR = "Ek masla aa gaya. Thori dair mein dobara try karein. 🙏"

RATE_LIMIT_MESSAGE = "Thoda wait karein — aap bohat fast messages bhej rahe hain."

SESSION_ESCALATED = (
    "Aapki baat team tak pohanchadi gayi hai.\n"
    "Koi jaldi respond karega. 🙏"
)

# ── Bot — Discount ───────────────────────────────────────────────────

DISCOUNT_REQUEST_SENT = "Request bhej di ✅ Owner approve kare to update ho jayega."

DISCOUNT_APPROVED = (
    "✅ Discount approve ho gaya!\n"
    "{discount_detail}\n"
    "Updated total: PKR {new_total}"
)

DISCOUNT_REJECTED = "❌ Discount request approve nahi hui. Original amount qaim hai."

# ── Bot — Quick Reorder ──────────────────────────────────────────────

QUICK_REORDER_PROMPT = (
    "📋 Aapka last order:\n{last_order_summary}\n\n"
    "Repeat karna hai?"
)

# ── Owner Notifications ──────────────────────────────────────────────

OWNER_NEW_ORDER = (
    "📦 Naya Order\n"
    "#{order_number} | {customer_name}\n"
    "Items: {item_count} | Total: PKR {total}\n"
    "Payment: {payment_method} ({payment_status})\n"
    "{payment_link_or_dash}"
)

OWNER_PAYMENT_RECEIVED = (
    "✅ Payment Mila!\n\n"
    "Order: #{order_number}\n"
    "Customer: {customer_name}\n"
    "Amount: PKR {amount}\n"
    "Gateway: {gateway}\n"
    "Ref: {reference}\n"
    "Time: {time}\n\n"
    "Dispatch ke liye tayar hai 🚚"
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
    "Please jaldi respond karein."
)

OWNER_DAILY_SUMMARY = (
    "📊 Aaj ka Summary — {date}\n\n"
    "Orders: {confirmed} ✅ | {pending} ⏳ | {cancelled} ❌\n"
    "Revenue: PKR {revenue}\n"
    "Payments received: PKR {payments_received}\n"
    "Outstanding: PKR {outstanding}\n\n"
    "Top item: {top_item} ({top_qty} units)\n"
    "New customers: {new_customers}"
)

OWNER_LOW_STOCK = (
    "⚠️ Low Stock Alert\n"
    "{medicine_name} — sirf {quantity} {unit} bacha hai\n"
    "Reorder threshold: {threshold} {unit}"
)

OWNER_SUBSCRIPTION_7_DAYS = (
    "⚠️ Subscription 7 din mein expire hogi.\n"
    "Renew karein: {renewal_link}"
)

OWNER_SUBSCRIPTION_1_DAY = (
    "🔴 URGENT — Subscription kal expire hogi!\n"
    "Renew karein: {renewal_link}"
)

OWNER_DISCOUNT_REQUEST = (
    "💬 Discount Request\n"
    "{customer_name} | Order #{order_number}\n"
    "Requested: {requested_percent}%\n"
    "Order Total: PKR {total}\n\n"
    "Reply karna ho:\n"
    "APPROVE {suggested_percent} ya REJECT"
)

OWNER_NEW_CUSTOMER = (
    "👋 Naya Customer\n"
    "{customer_name} — {shop_name}\n"
    "Phone: ****{phone_suffix}\n"
    "First order lagane ki koshish ki"
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
    "Excel bheja ja raha hai."
)

OWNER_SYSTEM_ALERT = (
    "🚨 System Alert\n\n"
    "Issue: {issue}\n"
    "Time: {time}\n\n"
    "Auto-recovery attempted. Check dashboard."
)

# ── Sales Rep Notifications ──────────────────────────────────────────

REP_ORDER_SUBMITTED = (
    "✅ Order submit ho gayi\n"
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
    "{days_remaining} din remaining in month."
)

REP_VISIT_REMINDER = (
    "📍 Visit Reminder\n"
    "{customer_name} ka visit {days_since} din se nahi hua.\n"
    "Last order: {last_order_date}"
)

REP_DAILY_SUMMARY = (
    "📊 Aaj aapka Summary\n\n"
    "Orders submitted: {orders_count}\n"
    "Total value: PKR {total_value}\n"
    "New prospects: {prospects_added}\n"
    "Visits logged: {visits_logged}"
)
