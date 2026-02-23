"""Order logging to WhatsApp group and Excel file.

After an order is confirmed, it must be logged to two destinations:

1. **WhatsApp group** — A formatted order summary is sent to the
   distributor's designated WhatsApp group (identified by
   ``Distributor.whatsapp_group_id``).

2. **Excel file** — A row is appended to the current month's Excel
   order log via ``excel_generator.append_order_row()``.

After each successful log, the ``whatsapp_logged_at`` or
``excel_logged_at`` timestamp is updated on the order record so
logging is idempotent (never logged twice).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from app.core.config import get_settings
from app.db.models.order import Order, OrderItem, OrderUpdate
from app.db.repositories.customer_repo import CustomerRepository
from app.db.repositories.distributor_repo import DistributorRepository
from app.db.repositories.order_repo import OrderRepository
from app.notifications.whatsapp_notifier import WhatsAppNotifier
from app.whatsapp.message_types import build_text_message

if TYPE_CHECKING:
    from app.db.models.customer import Customer
    from app.db.models.distributor import Distributor


# ═══════════════════════════════════════════════════════════════════
# FORMAT HELPERS
# ═══════════════════════════════════════════════════════════════════


def _paisas_to_pkr(paisas: int) -> str:
    """Convert paisas to formatted PKR string.

    Args:
        paisas: Amount in paisas (1 PKR = 100 paisas).

    Returns:
        Formatted string e.g. ``"PKR 1,985"`` or ``"PKR 19.50"``.
    """
    rupees = paisas / 100
    if rupees == int(rupees):
        return f"PKR {int(rupees):,}"
    return f"PKR {rupees:,.2f}"


def _mask_phone(phone: str) -> str:
    """Mask phone number for logging — show only last 4 digits.

    Args:
        phone: E.164 formatted phone number.

    Returns:
        Masked string e.g. ``"****4567"``.
    """
    if len(phone) < 4:
        return "****"
    return f"****{phone[-4:]}"


def _format_item_line(item: OrderItem) -> str:
    """Format a single order item line for WhatsApp group message.

    Args:
        item: The order item to format.

    Returns:
        Formatted line e.g. ``"• Paracetamol 500mg × 5 strips — PKR 175"``.
    """
    name = item.medicine_name
    qty = item.quantity_ordered
    unit = item.unit or "pcs"
    total = _paisas_to_pkr(item.line_total_paisas)

    line = f"• {name} × {qty} {unit} — {total}"

    # Mention discount if applied
    if item.discount_paisas > 0:
        line += f"\n  ↳ Discount: {_paisas_to_pkr(item.discount_paisas)}"

    # Mention bonus units if given
    if item.bonus_units_given > 0:
        line += f"\n  ↳ Bonus: +{item.bonus_units_given} {unit}"

    return line


def format_whatsapp_group_message(
    order: Order,
    items: list[OrderItem],
    customer_name: str,
    shop_name: str,
    customer_phone: str,
    address: str,
    city: str,
) -> str:
    """Build the formatted WhatsApp group message for an order.

    Follows the message format defined in the system design overview:
    order number, date, customer, shop, address, items, total, status.

    Args:
        order: The confirmed order.
        items: List of order items.
        customer_name: Customer full name.
        shop_name: Shop / pharmacy name.
        customer_phone: Customer phone (will be partially masked).
        address: Delivery address.
        city: Customer city.

    Returns:
        Formatted message string ready for WhatsApp.
    """
    confirmed_at = order.updated_at or order.created_at
    date_str = confirmed_at.strftime("%d %b %Y")
    time_str = confirmed_at.strftime("%-I:%M %p") if hasattr(
        confirmed_at, "strftime"
    ) else confirmed_at.strftime("%I:%M %p")

    item_lines = "\n".join(_format_item_line(item) for item in items)

    # Build discount line if order-level discount exists
    discount_line = ""
    if order.discount_paisas > 0:
        discount_line = f"\n💲 Discount: -{_paisas_to_pkr(order.discount_paisas)}"

    # Build delivery charges line
    delivery_line = ""
    if order.delivery_charges_paisas > 0:
        delivery_line = (
            f"\n🚚 Delivery: {_paisas_to_pkr(order.delivery_charges_paisas)}"
        )

    # Status mapping
    status_display = {
        "pending": "PENDING",
        "confirmed": "CONFIRMED — Awaiting Dispatch",
        "processing": "PROCESSING",
        "dispatched": "DISPATCHED",
        "delivered": "DELIVERED",
        "cancelled": "CANCELLED",
    }.get(order.status, order.status.upper() if isinstance(order.status, str) else str(order.status).upper())

    # Mask phone for PII safety
    masked_phone = _mask_phone(customer_phone)

    # Payment method display
    payment_display = ""
    if order.payment_method:
        method = str(order.payment_method)
        payment_display = f"\n💳 Payment: {method.replace('_', ' ').title()}"

    message = (
        f"📦 *NAYA ORDER — #{order.order_number}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Tarikh: {date_str} | {time_str}\n"
        f"👤 Customer: {customer_name}\n"
        f"🏪 Dukaan: {shop_name}\n"
        f"📍 Pata: {address or 'N/A'}"
        f"{f', {city}' if city else ''}\n"
        f"📞 Number: {masked_phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"ITEMS:\n"
        f"{item_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
        f"{discount_line}"
        f"{delivery_line}"
        f"{payment_display}\n"
        f"💰 TOTAL: {_paisas_to_pkr(order.total_paisas)}\n"
        f"📊 Status: {status_display}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    return message


# ═══════════════════════════════════════════════════════════════════
# WHATSAPP GROUP LOGGING
# ═══════════════════════════════════════════════════════════════════


async def log_order_to_whatsapp_group(
    order: Order,
    items: list[OrderItem],
    *,
    order_repo: OrderRepository | None = None,
    customer_repo: CustomerRepository | None = None,
    distributor_repo: DistributorRepository | None = None,
    notifier: WhatsAppNotifier | None = None,
) -> bool:
    """Send a formatted order summary to the distributor's WhatsApp group.

    Fetches the distributor and customer records if not already loaded,
    formats the message, sends it via the WhatsApp client, and updates
    ``order.whatsapp_logged_at`` on success.

    Args:
        order: The confirmed order to log.
        items: Line items for the order.
        order_repo: Order repository instance.
        customer_repo: Customer repository instance.
        distributor_repo: Distributor repository instance.
        notifier: WhatsApp notifier instance.

    Returns:
        ``True`` if the message was sent successfully, ``False`` otherwise.
    """
    # Skip if already logged
    if order.whatsapp_logged_at is not None:
        logger.debug(
            "order_log.whatsapp_already_logged",
            order_number=order.order_number,
        )
        return True

    dist_repo = distributor_repo or DistributorRepository()
    cust_repo = customer_repo or CustomerRepository()
    o_repo = order_repo or OrderRepository()
    wa_notifier = notifier or WhatsAppNotifier()

    try:
        # Fetch distributor
        distributor = await dist_repo.get_by_id(str(order.distributor_id))
        if not distributor:
            logger.warning(
                "order_log.distributor_not_found",
                distributor_id=str(order.distributor_id),
                order_number=order.order_number,
            )
            return False

        # Check if group logging is configured
        if not distributor.whatsapp_group_id:
            logger.info(
                "order_log.no_whatsapp_group",
                order_number=order.order_number,
                distributor=distributor.business_name,
            )
            # Not a failure — just not configured
            return False

        # Fetch customer
        customer = await cust_repo.get_by_id(
            str(order.customer_id),
            distributor_id=str(order.distributor_id),
        )
        customer_name = customer.name if customer else "Unknown"
        shop_name = customer.shop_name if customer else "Unknown"
        customer_phone = customer.whatsapp_number if customer else "N/A"
        address = customer.address if customer else (order.delivery_address or "N/A")
        city = customer.city if customer else ""

        # Format the message
        message = format_whatsapp_group_message(
            order=order,
            items=items,
            customer_name=customer_name,
            shop_name=shop_name,
            customer_phone=customer_phone,
            address=address,
            city=city,
        )

        # Send to group
        msg_id = await wa_notifier.send_text(
            phone_number_id=distributor.whatsapp_phone_number_id,
            to=distributor.whatsapp_group_id,
            text=message,
            distributor_id=str(distributor.id),
            recipient_type="group",
            notification_type="order_log",
        )

        if msg_id:
            # Update whatsapp_logged_at
            now = datetime.now(timezone.utc)
            await o_repo.update(
                str(order.id),
                OrderUpdate(whatsapp_logged_at=now),
                distributor_id=str(order.distributor_id),
            )
            logger.info(
                "order_log.whatsapp_sent",
                order_number=order.order_number,
                group_id=distributor.whatsapp_group_id,
                message_id=msg_id,
            )
            return True

        logger.warning(
            "order_log.whatsapp_send_failed",
            order_number=order.order_number,
        )
        return False

    except Exception as exc:
        logger.error(
            "order_log.whatsapp_error",
            order_number=order.order_number,
            error=str(exc),
        )
        return False


# ═══════════════════════════════════════════════════════════════════
# EXCEL FILE LOGGING
# ═══════════════════════════════════════════════════════════════════


async def log_order_to_excel(
    order: Order,
    items: list[OrderItem],
    *,
    order_repo: OrderRepository | None = None,
    customer_repo: CustomerRepository | None = None,
) -> bool:
    """Append an order row to the current month's Excel log.

    Delegates to ``excel_generator.append_order_row()`` for the actual
    spreadsheet manipulation.  Updates ``order.excel_logged_at`` on
    success.

    Args:
        order: The confirmed order to log.
        items: Line items for the order.
        order_repo: Order repository instance.
        customer_repo: Customer repository instance.

    Returns:
        ``True`` if the row was appended successfully, ``False`` otherwise.
    """
    settings = get_settings()

    if not settings.enable_excel_reports:
        logger.debug(
            "order_log.excel_disabled",
            order_number=order.order_number,
        )
        return False

    # Skip if already logged
    if order.excel_logged_at is not None:
        logger.debug(
            "order_log.excel_already_logged",
            order_number=order.order_number,
        )
        return True

    cust_repo = customer_repo or CustomerRepository()
    o_repo = order_repo or OrderRepository()

    try:
        # Fetch customer for name/shop
        customer = await cust_repo.get_by_id(
            str(order.customer_id),
            distributor_id=str(order.distributor_id),
        )
        customer_name = customer.name if customer else "Unknown"
        shop_name = customer.shop_name if customer else "Unknown"
        city = customer.city if customer else ""

        # Lazy import to avoid circular imports and only load
        # openpyxl when actually needed
        from app.reporting.excel_generator import append_order_row

        success = await append_order_row(
            order=order,
            items=items,
            customer_name=customer_name,
            shop_name=shop_name,
            city=city,
        )

        if success:
            now = datetime.now(timezone.utc)
            await o_repo.update(
                str(order.id),
                OrderUpdate(excel_logged_at=now),
                distributor_id=str(order.distributor_id),
            )
            logger.info(
                "order_log.excel_appended",
                order_number=order.order_number,
            )
            return True

        logger.warning(
            "order_log.excel_append_failed",
            order_number=order.order_number,
        )
        return False

    except Exception as exc:
        logger.error(
            "order_log.excel_error",
            order_number=order.order_number,
            error=str(exc),
        )
        return False


# ═══════════════════════════════════════════════════════════════════
# COMBINED LOGGING
# ═══════════════════════════════════════════════════════════════════


async def log_confirmed_order(
    order_id: str,
    distributor_id: str,
    *,
    order_repo: OrderRepository | None = None,
    customer_repo: CustomerRepository | None = None,
    distributor_repo: DistributorRepository | None = None,
    notifier: WhatsAppNotifier | None = None,
) -> dict[str, bool]:
    """Log a confirmed order to both WhatsApp group and Excel.

    This is the main entry point called after an order is confirmed.
    Fetches the order and items once, then writes to both destinations.

    Args:
        order_id: UUID string of the confirmed order.
        distributor_id: Distributor UUID for tenant scope.
        order_repo: Order repository instance.
        customer_repo: Customer repository instance.
        distributor_repo: Distributor repository instance.
        notifier: WhatsApp notifier instance.

    Returns:
        Dict with ``"whatsapp"`` and ``"excel"`` keys indicating success.
    """
    o_repo = order_repo or OrderRepository()
    c_repo = customer_repo or CustomerRepository()
    d_repo = distributor_repo or DistributorRepository()
    wa_notifier = notifier or WhatsAppNotifier()

    results: dict[str, bool] = {"whatsapp": False, "excel": False}

    try:
        order, items = await o_repo.get_order_with_items(
            order_id, distributor_id,
        )
    except Exception as exc:
        logger.error(
            "order_log.fetch_failed",
            order_id=order_id,
            error=str(exc),
        )
        return results

    # WhatsApp group logging
    results["whatsapp"] = await log_order_to_whatsapp_group(
        order,
        items,
        order_repo=o_repo,
        customer_repo=c_repo,
        distributor_repo=d_repo,
        notifier=wa_notifier,
    )

    # Excel file logging
    results["excel"] = await log_order_to_excel(
        order,
        items,
        order_repo=o_repo,
        customer_repo=c_repo,
    )

    logger.info(
        "order_log.complete",
        order_number=order.order_number,
        whatsapp_logged=results["whatsapp"],
        excel_logged=results["excel"],
    )

    return results
