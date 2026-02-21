"""Urdu script notification and bot message templates.

Used when the customer communicates in Urdu script (نستعلیق).
Less common than Roman Urdu but supported for customers who prefer it.

All templates use ``.format()``-style placeholders.  Caller is
responsible for passing the correct keyword arguments.

Note: WhatsApp renders Urdu script correctly (right-to-left).
Emoji placement works fine alongside Urdu text.
"""

from __future__ import annotations


# ── Bot — Greetings ──────────────────────────────────────────────────

GREETING_NEW_CUSTOMER = (
    "السلام علیکم! 😊 {distributor_name} میں خوش آمدید۔\n"
    "میں TELETRAAN ہوں — آپ کا آرڈر اسسٹنٹ۔\n"
    "اپنا نام اور دکان کا نام بتا دیں تاکہ شروع کریں۔"
)

GREETING_RETURNING_CUSTOMER = (
    "وعلیکم السلام {customer_name}! 😊 آج کیا چاہیے؟"
)

GREETING_RETURNING_CUSTOMER_NO_NAME = (
    "وعلیکم السلام! 😊 آج کیا چاہیے؟"
)

# ── Bot — Order Flow ─────────────────────────────────────────────────

ITEM_ADDED = (
    "💊 {medicine_name} × {quantity} {unit} — ایڈ ہو گیا ✅\nاور کچھ؟"
)

ITEM_NOT_FOUND = "یہ نام کیٹلاگ میں نہیں ملا۔ تھوڑا اور واضح کریں؟"

ITEM_AMBIGUOUS = (
    "یہ {match_count} دوائیں ملیں:\n{match_list}\n"
    "کون سی چاہیے؟ نمبر یا نام بتائیں۔"
)

ITEM_OUT_OF_STOCK = (
    "⚠️ {medicine_name} ابھی سٹاک میں نہیں ہے۔\n"
    "کوئی اور دوائی چاہیے؟"
)

ITEM_LOW_STOCK = (
    "⚠️ {medicine_name} صرف {available} {unit} بچا ہے۔\n"
    "{available} ایڈ کریں؟"
)

ITEM_REMOVED = "❌ {medicine_name} ہٹا دیا گیا۔ اور کچھ؟"

ORDER_SUMMARY = (
    "📦 آپ کا آرڈر:\n"
    "─────────────────\n"
    "{items_list}\n"
    "─────────────────\n"
    "سب ٹوٹل: PKR {subtotal}\n"
    "{discount_line}"
    "ڈیلیوری: PKR {delivery_charges}\n"
    "ٹوٹل: PKR {total}\n"
    "\nکنفرم کریں یا ایڈٹ کریں؟"
)

ORDER_CONFIRMED = (
    "آرڈر کنفرم! ✅ #{order_number}\n"
    "ٹوٹل: PKR {total}\n"
    "{delivery_info}"
)

ORDER_CANCELLED = "آرڈر کینسل ہو گیا۔ ❌ کوئی مسئلہ نہیں — جب چاہیں نیا آرڈر لگائیں۔"

ORDER_TIMED_OUT = (
    "⏰ آپ کا آرڈر سیشن ٹائم آؤٹ ہو گیا۔\n"
    "دوبارہ آرڈر شروع کرنے کے لیے کوئی بھی پیغام بھیجیں۔"
)

# ── Bot — Payment ────────────────────────────────────────────────────

PAYMENT_LINK = (
    "💳 ادائیگی کا لنک:\n{payment_url}\n\n"
    "رقم: PKR {amount}\n"
    "طریقہ: {method}\n"
    "یہ لنک {expiry_minutes} منٹ میں ایکسپائر ہو گا۔"
)

PAYMENT_RECEIVED = "✅ ادائیگی مل گئی! PKR {amount}\nآرڈر #{order_number} پراسیس ہو رہا ہے۔"

PAYMENT_FAILED = (
    "❌ ادائیگی نہیں ہو پائی۔\n"
    "دوبارہ کوشش کریں یا مختلف طریقہ استعمال کریں۔"
)

PAYMENT_PENDING_REMINDER = (
    "⏳ آرڈر #{order_number} کی ادائیگی ابھی تک پینڈنگ ہے۔\n"
    "PKR {amount} — {method} سے ادائیگی کریں:\n{payment_url}"
)

# ── Bot — Complaints ─────────────────────────────────────────────────

COMPLAINT_REGISTERED = (
    "📝 شکایت درج ہو گئی۔ ٹکٹ: #{ticket_number}\n"
    "جلد از جلد دیکھا جائے گا۔ 🙏"
)

COMPLAINT_UPDATE = (
    "🔔 شکایت #{ticket_number} اپ ڈیٹ:\n"
    "حالت: {status}\n{resolution_note}"
)

# ── Bot — Guidance (unsupported types) ───────────────────────────────

UNSUPPORTED_TYPE_GUIDANCE = (
    "میں صرف ٹیکسٹ اور وائس پیغامات سمجھتا ہوں۔\n"
    "اپنا آرڈر ٹیکسٹ میں بھیجیں یا وائس نوٹ ریکارڈ کریں۔ 🎙️"
)

UNSUPPORTED_MESSAGE = "یہ سمجھ نہیں آیا۔ ٹیکسٹ یا وائس میں بتائیں؟ 🤔"

# ── Bot — Errors ─────────────────────────────────────────────────────

GENERIC_ERROR = "ایک مسئلہ آ گیا۔ تھوڑی دیر میں دوبارہ کوشش کریں۔ 🙏"

RATE_LIMIT_MESSAGE = "تھوڑا انتظار کریں — آپ بہت تیز پیغامات بھیج رہے ہیں۔"

SESSION_ESCALATED = (
    "آپ کی بات ٹیم تک پہنچا دی گئی ہے۔\n"
    "کوئی جلد رد عمل دے گا۔ 🙏"
)

# ── Bot — Discount ───────────────────────────────────────────────────

DISCOUNT_REQUEST_SENT = "درخواست بھیج دی ✅ مالک منظور کرے تو اپ ڈیٹ ہو جائے گا۔"

DISCOUNT_APPROVED = (
    "✅ ڈسکاؤنٹ منظور ہو گیا!\n"
    "{discount_detail}\n"
    "نیا ٹوٹل: PKR {new_total}"
)

DISCOUNT_REJECTED = "❌ ڈسکاؤنٹ درخواست منظور نہیں ہوئی۔ اصل رقم قائم ہے۔"

# ── Bot — Quick Reorder ──────────────────────────────────────────────

QUICK_REORDER_PROMPT = (
    "📋 آپ کا پچھلا آرڈر:\n{last_order_summary}\n\n"
    "دوبارہ کرنا ہے؟"
)

# ── Owner Notifications (consistent format across languages) ─────────

OWNER_NEW_ORDER = (
    "📦 نیا آرڈر\n"
    "#{order_number} | {customer_name}\n"
    "آئٹمز: {item_count} | ٹوٹل: PKR {total}\n"
    "ادائیگی: {payment_method} ({payment_status})\n"
    "{payment_link_or_dash}"
)

OWNER_PAYMENT_RECEIVED = (
    "✅ ادائیگی موصول!\n\n"
    "آرڈر: #{order_number}\n"
    "کسٹمر: {customer_name}\n"
    "رقم: PKR {amount}\n"
    "گیٹ وے: {gateway}\n"
    "حوالہ: {reference}\n"
    "وقت: {time}\n\n"
    "ڈسپیچ کے لیے تیار ہے 🚚"
)

OWNER_PAYMENT_FAILED = (
    "❌ ادائیگی ناکام\n\n"
    "آرڈر: #{order_number}\n"
    "کسٹمر: {customer_name}\n"
    "رقم: PKR {amount}\n"
    "گیٹ وے: {gateway}\n"
    "خطا: {error}\n"
    "کوششیں: {attempts}\n\n"
    "دستی فالو اپ ضروری ہے۔"
)

OWNER_ESCALATION = (
    "⚠️ کسٹمر ایسکلیشن\n\n"
    "کسٹمر: ****{phone_suffix}\n"
    "وجہ: {reason}\n"
    "{conversation_snippet}\n\n"
    "براہ کرم جلد جواب دیں۔"
)

OWNER_DAILY_SUMMARY = (
    "📊 آج کا خلاصہ — {date}\n\n"
    "آرڈرز: {confirmed} ✅ | {pending} ⏳ | {cancelled} ❌\n"
    "آمدنی: PKR {revenue}\n"
    "موصول ادائیگیاں: PKR {payments_received}\n"
    "بقایا: PKR {outstanding}\n\n"
    "ٹاپ آئٹم: {top_item} ({top_qty} یونٹ)\n"
    "نئے کسٹمرز: {new_customers}"
)

OWNER_LOW_STOCK = (
    "⚠️ کم سٹاک الرٹ\n"
    "{medicine_name} — صرف {quantity} {unit} بچا ہے\n"
    "ری آرڈر حد: {threshold} {unit}"
)

OWNER_SUBSCRIPTION_7_DAYS = (
    "⚠️ سبسکرپشن 7 دن میں ایکسپائر ہو گی۔\n"
    "تجدید کریں: {renewal_link}"
)

OWNER_SUBSCRIPTION_1_DAY = (
    "🔴 فوری — سبسکرپشن کل ایکسپائر ہو گی!\n"
    "تجدید کریں: {renewal_link}"
)

OWNER_DISCOUNT_REQUEST = (
    "💬 ڈسکاؤنٹ درخواست\n"
    "{customer_name} | آرڈر #{order_number}\n"
    "درخواست: {requested_percent}%\n"
    "آرڈر ٹوٹل: PKR {total}\n\n"
    "جواب دیں:\n"
    "APPROVE {suggested_percent} یا REJECT"
)

OWNER_NEW_CUSTOMER = (
    "👋 نیا کسٹمر\n"
    "{customer_name} — {shop_name}\n"
    "فون: ****{phone_suffix}\n"
    "پہلا آرڈر لگانے کی کوشش کی"
)

OWNER_PAYMENT_MISMATCH = (
    "⚠️ ادائیگی میں فرق\n"
    "آرڈر #{order_number} | {customer_name}\n"
    "متوقع: PKR {expected}\n"
    "گیٹ وے رپورٹ: PKR {received}\n"
    "فرق: PKR {difference}\n"
    "دستی تصدیق ضروری ہے۔"
)

OWNER_WEEKLY_REPORT = (
    "📋 ہفتہ وار رپورٹ تیار — {week_label}\n"
    "ایکسل بھیجا جا رہا ہے۔"
)

OWNER_SYSTEM_ALERT = (
    "🚨 سسٹم الرٹ\n\n"
    "مسئلہ: {issue}\n"
    "وقت: {time}\n\n"
    "خود کار بحالی کی کوشش کی گئی۔ ڈیش بورڈ چیک کریں۔"
)

# ── Sales Rep Notifications ──────────────────────────────────────────

REP_ORDER_SUBMITTED = (
    "✅ آرڈر جمع ہو گیا\n"
    "#{order_number} | {customer_name}\n"
    "ٹوٹل: PKR {total}\n"
    "حالت: پراسیسنگ"
)

REP_COMMISSION_UPDATE = (
    "💰 کمیشن اپ ڈیٹ\n"
    "{month_label}\n\n"
    "سیلز ٹارگٹ: PKR {target}\n"
    "حاصل: PKR {achieved} ({percent}%)\n"
    "کمیشن: PKR {commission}\n\n"
    "مہینے میں {days_remaining} دن باقی۔"
)

REP_VISIT_REMINDER = (
    "📍 وزٹ یاد دہانی\n"
    "{customer_name} کا وزٹ {days_since} دن سے نہیں ہوا۔\n"
    "آخری آرڈر: {last_order_date}"
)

REP_DAILY_SUMMARY = (
    "📊 آج آپ کا خلاصہ\n\n"
    "جمع کردہ آرڈرز: {orders_count}\n"
    "کل قیمت: PKR {total_value}\n"
    "نئے ممکنہ گاہک: {prospects_added}\n"
    "درج وزٹ: {visits_logged}"
)
