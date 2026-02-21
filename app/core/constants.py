"""TELETRAAN constants, enums, state names, limits, and timeouts.

Every magic string used anywhere in the application is defined here
as a ``StrEnum`` member or module-level constant.  Business logic
must import from this module — never use inline string literals for
states, statuses, or categories.
"""

from __future__ import annotations

from enum import StrEnum


# ═══════════════════════════════════════════════════════════════════
# CHANNELS
# ═══════════════════════════════════════════════════════════════════


class ChannelType(StrEnum):
    """WhatsApp channel identifier."""

    A = "A"
    B = "B"


# ═══════════════════════════════════════════════════════════════════
# SUBSCRIPTION
# ═══════════════════════════════════════════════════════════════════


class SubscriptionStatus(StrEnum):
    """Distributor subscription lifecycle states."""

    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRING = "expiring"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════════════════════════════
# SESSION / FSM
# ═══════════════════════════════════════════════════════════════════


class SessionStateA(StrEnum):
    """Channel A finite-state-machine states."""

    IDLE = "idle"
    ONBOARDING_NAME = "onboarding_name"
    ONBOARDING_SHOP = "onboarding_shop"
    ONBOARDING_ADDRESS = "onboarding_address"
    ONBOARDING_CONFIRM = "onboarding_confirm"
    MAIN_MENU = "main_menu"
    ORDER_ITEM_COLLECTION = "order_item_collection"
    ORDER_ITEM_CONFIRMATION = "order_item_confirmation"
    ORDER_AMBIGUITY_RESOLUTION = "order_ambiguity_resolution"
    ORDER_BILL_PREVIEW = "order_bill_preview"
    ORDER_DISCOUNT_REQUEST = "order_discount_request"
    ORDER_FINAL_CONFIRMATION = "order_final_confirmation"
    CATALOG_BROWSING = "catalog_browsing"
    COMPLAINT_DESCRIPTION = "complaint_description"
    COMPLAINT_CATEGORY = "complaint_category"
    COMPLAINT_CONFIRM = "complaint_confirm"
    PROFILE_VIEW = "profile_view"
    PROFILE_EDIT = "profile_edit"
    INQUIRY_RESPONSE = "inquiry_response"
    HANDOFF = "handoff"


class SessionStateB(StrEnum):
    """Channel B finite-state-machine states."""

    IDLE = "idle"
    GREETING = "greeting"
    SERVICE_SELECTION = "service_selection"
    SERVICE_DETAIL = "service_detail"
    QUALIFICATION_NAME = "qualification_name"
    QUALIFICATION_BUSINESS = "qualification_business"
    QUALIFICATION_CITY = "qualification_city"
    QUALIFICATION_RETAILER_COUNT = "qualification_retailer_count"
    DEMO_BOOKING = "demo_booking"
    PROPOSAL_SENT = "proposal_sent"
    PAYMENT_PENDING = "payment_pending"
    ONBOARDING_SETUP = "onboarding_setup"
    FOLLOW_UP = "follow_up"
    SUPPORT = "support"
    HANDOFF = "handoff"


# ═══════════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════════


class OrderStatus(StrEnum):
    """Order lifecycle states."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    PARTIALLY_FULFILLED = "partially_fulfilled"


class PaymentStatus(StrEnum):
    """Order payment states."""

    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    CREDIT = "credit"


class PaymentMethod(StrEnum):
    """Accepted payment methods."""

    CASH = "cash"
    CREDIT = "credit"
    JAZZCASH = "jazzcash"
    EASYPAISA = "easypaisa"
    SAFEPAY = "safepay"
    NAYAPAY = "nayapay"
    BANK_TRANSFER = "bank_transfer"
    DUMMY = "dummy"


class OrderFlowStep(StrEnum):
    """Steps within the order context draft lifecycle."""

    ITEM_COLLECTION = "item_collection"
    ITEM_CONFIRMATION = "item_confirmation"
    BILL_PREVIEW = "bill_preview"
    DISCOUNT_REQUEST = "discount_request"
    FINAL_CONFIRMATION = "final_confirmation"
    COMPLETE = "complete"


class InputMethod(StrEnum):
    """How the customer supplied an order item."""

    TEXT = "text"
    VOICE = "voice"
    BUTTON_SELECTION = "button_selection"


# ═══════════════════════════════════════════════════════════════════
# PAYMENTS (GATEWAY)
# ═══════════════════════════════════════════════════════════════════


class GatewayType(StrEnum):
    """Payment gateway identifiers."""

    JAZZCASH = "jazzcash"
    EASYPAISA = "easypaisa"
    SAFEPAY = "safepay"
    NAYAPAY = "nayapay"
    BANK_TRANSFER = "bank_transfer"
    DUMMY = "dummy"
    MANUAL = "manual"


class GatewayPaymentStatus(StrEnum):
    """Gateway-level payment states."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentType(StrEnum):
    """What the payment is for."""

    SUBSCRIPTION_FEE = "subscription_fee"
    SETUP_FEE = "setup_fee"
    ORDER_PAYMENT = "order_payment"


# ═══════════════════════════════════════════════════════════════════
# COMPLAINTS
# ═══════════════════════════════════════════════════════════════════


class ComplaintCategory(StrEnum):
    """Customer complaint categories."""

    WRONG_ITEM = "wrong_item"
    LATE_DELIVERY = "late_delivery"
    DAMAGED_GOODS = "damaged_goods"
    EXPIRED_MEDICINE = "expired_medicine"
    SHORT_QUANTITY = "short_quantity"
    BILLING_ERROR = "billing_error"
    OTHER = "other"


class ComplaintStatus(StrEnum):
    """Complaint lifecycle states."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"


class ComplaintPriority(StrEnum):
    """Complaint urgency levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ═══════════════════════════════════════════════════════════════════
# SUPPORT TICKETS
# ═══════════════════════════════════════════════════════════════════


class SupportTicketCategory(StrEnum):
    """Distributor support ticket categories."""

    BOT_ISSUE = "bot_issue"
    BILLING = "billing"
    SETUP = "setup"
    FEATURE_REQUEST = "feature_request"
    GATEWAY_ISSUE = "gateway_issue"
    OTHER = "other"


class SupportTicketStatus(StrEnum):
    """Support ticket lifecycle states."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ═══════════════════════════════════════════════════════════════════
# PROSPECTS (CHANNEL B)
# ═══════════════════════════════════════════════════════════════════


class ProspectStatus(StrEnum):
    """Sales prospect lifecycle states."""

    NEW = "new"
    QUALIFIED = "qualified"
    DEMO_BOOKED = "demo_booked"
    PROPOSAL_SENT = "proposal_sent"
    PAYMENT_PENDING = "payment_pending"
    CONVERTED = "converted"
    LOST = "lost"
    WAITLISTED = "waitlisted"


# ═══════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════


class RecipientType(StrEnum):
    """Who the notification is sent to."""

    CUSTOMER = "customer"
    DISTRIBUTOR = "distributor"
    PROSPECT = "prospect"
    OWNER = "owner"


class DeliveryStatus(StrEnum):
    """WhatsApp message delivery status."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# ═══════════════════════════════════════════════════════════════════
# AUDIT
# ═══════════════════════════════════════════════════════════════════


class ActorType(StrEnum):
    """Who performed the action in an audit record."""

    CUSTOMER = "customer"
    DISTRIBUTOR = "distributor"
    OWNER = "owner"
    SYSTEM = "system"
    SCHEDULER = "scheduler"


class StatusChangeActor(StrEnum):
    """Who changed an order status."""

    CUSTOMER = "customer"
    DISTRIBUTOR = "distributor"
    SYSTEM = "system"
    SCHEDULER = "scheduler"


# ═══════════════════════════════════════════════════════════════════
# INVENTORY
# ═══════════════════════════════════════════════════════════════════


class SyncSource(StrEnum):
    """How catalog data was imported."""

    GOOGLE_DRIVE = "google_drive"
    SUPABASE_UPLOAD = "supabase_upload"
    MANUAL_API = "manual_api"


class SyncStatus(StrEnum):
    """Inventory sync job states."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class MedicineForm(StrEnum):
    """Standard pharmaceutical dosage forms."""

    TABLET = "tablet"
    CAPSULE = "capsule"
    SYRUP = "syrup"
    INJECTION = "injection"
    SACHET = "sachet"
    CREAM = "cream"
    DROPS = "drops"


# ═══════════════════════════════════════════════════════════════════
# DISCOUNT RULES
# ═══════════════════════════════════════════════════════════════════


class DiscountRuleType(StrEnum):
    """Types of discount rules a distributor can configure."""

    BONUS_UNITS = "bonus_units"
    PERCENTAGE_DISCOUNT = "percentage_discount"
    FLAT_DISCOUNT = "flat_discount"
    MINIMUM_ORDER = "minimum_order"
    TIERED_PRICING = "tiered_pricing"


class DiscountRequestType(StrEnum):
    """How a customer requests a discount on a line item or order."""

    BONUS_UNITS = "bonus_units"
    PERCENTAGE = "percentage"
    FLAT_AMOUNT = "flat_amount"


class DiscountRequestStatus(StrEnum):
    """Discount request lifecycle."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"


# ═══════════════════════════════════════════════════════════════════
# AI
# ═══════════════════════════════════════════════════════════════════


class AIProvider(StrEnum):
    """Supported AI provider identifiers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    OPENROUTER = "openrouter"


class AIConfidence(StrEnum):
    """AI confidence levels for voice/NLU results."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AmbiguityType(StrEnum):
    """Types of ambiguity in order item matching."""

    MULTIPLE_MATCHES = "multiple_matches"
    QUANTITY_UNCLEAR = "quantity_unclear"
    UNIT_UNCLEAR = "unit_unclear"
    STRENGTH_UNCLEAR = "strength_unclear"


# ═══════════════════════════════════════════════════════════════════
# LANGUAGE
# ═══════════════════════════════════════════════════════════════════


class Language(StrEnum):
    """Supported conversation languages."""

    ROMAN_URDU = "roman_urdu"
    URDU = "urdu"
    ENGLISH = "english"


# ═══════════════════════════════════════════════════════════════════
# SCHEDULED MESSAGES
# ═══════════════════════════════════════════════════════════════════


class ScheduledMessageStatus(StrEnum):
    """Scheduled outbound message states."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════════════════════════════
# EXCEL REPORT SCHEDULE
# ═══════════════════════════════════════════════════════════════════


class ExcelReportSchedule(StrEnum):
    """When to send Excel order logs to the distributor."""

    REALTIME = "realtime"
    DAILY_MORNING = "daily_morning"
    DAILY_EVENING = "daily_evening"
    WEEKLY = "weekly"


# ═══════════════════════════════════════════════════════════════════
# ORDER SOURCE
# ═══════════════════════════════════════════════════════════════════


class OrderSource(StrEnum):
    """Where the order originated."""

    WHATSAPP = "whatsapp"
    ADMIN_API = "admin_api"
    QUICK_REORDER = "quick_reorder"


# ═══════════════════════════════════════════════════════════════════
# LIMITS & TIMEOUTS
# ═══════════════════════════════════════════════════════════════════

# Input length limits
MAX_MESSAGE_LENGTH: int = 2000
MAX_NAME_LENGTH: int = 255
MAX_ADDRESS_LENGTH: int = 500
MAX_FREE_TEXT_LENGTH: int = 2000

# Rate limits (per WhatsApp number)
RATE_LIMIT_MESSAGES_PER_MINUTE: int = 30
RATE_LIMIT_VOICE_PER_MINUTE: int = 10
RATE_LIMIT_AI_CALLS_PER_MINUTE: int = 20

# Session
SESSION_EXPIRY_HOURS: int = 24
SESSION_TIMEOUT_MINUTES_DEFAULT: int = 60
CONVERSATION_HISTORY_MAX_TURNS: int = 15

# Orders
MAX_ITEMS_PER_ORDER_DEFAULT: int = 50

# Fuzzy matching
FUZZY_MATCH_THRESHOLD: float = 70.0
FUZZY_MATCH_HIGH_CONFIDENCE: float = 90.0

# AI
AI_CONTEXT_SUMMARY_ITEM_THRESHOLD: int = 8
AI_MAX_PROMPT_INPUT_LENGTH: int = 1500

# Retry
MAX_RETRY_ATTEMPTS: int = 3
RETRY_BACKOFF_MIN_SECONDS: float = 1.0
RETRY_BACKOFF_MAX_SECONDS: float = 8.0

# Pagination
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100
