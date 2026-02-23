"""PDF generation for catalog sheets and order receipts using ReportLab.

Two primary outputs:

1. **Catalog PDF** — Formatted product catalog for a distributor,
   with medicine name, generic name, form, strength, unit, price,
   stock status.  Grouped by category when available.

2. **Order Receipt PDF** — Printable receipt for a confirmed order
   with customer details, line items, totals, and payment info.

All PDF generation runs via ``asyncio.to_thread()`` to avoid
blocking the event loop.
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from app.db.models.catalog import CatalogItem
from app.db.models.order import Order, OrderItem


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════


_REPORTS_DIR = Path(tempfile.gettempdir()) / "teletraan_reports"

# Brand colours
_PRIMARY_COLOR = (0.184, 0.333, 0.588)  # #2F5496 — dark blue
_HEADER_BG = (0.184, 0.333, 0.588)
_ALT_ROW_BG = (0.941, 0.949, 0.961)  # #F0F2F5 — light grey
_WHITE = (1, 1, 1)
_BLACK = (0, 0, 0)
_GREEN = (0.133, 0.545, 0.133)
_RED = (0.8, 0.1, 0.1)


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _ensure_reports_dir() -> Path:
    """Create the reports directory if it does not exist.

    Returns:
        Path to the reports directory.
    """
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR


def _paisas_to_pkr_str(paisas: int) -> str:
    """Convert paisas to a formatted PKR string.

    Args:
        paisas: Amount in paisas.

    Returns:
        Formatted string e.g. ``"PKR 1,985"`` or ``"PKR 19.50"``.
    """
    rupees = paisas / 100
    if rupees == int(rupees):
        return f"PKR {int(rupees):,}"
    return f"PKR {rupees:,.2f}"


def _mask_phone(phone: str) -> str:
    """Mask a phone number for PII safety.

    Args:
        phone: E.164 formatted number.

    Returns:
        Masked string e.g. ``"****4567"``.
    """
    if len(phone) < 4:
        return "****"
    return f"****{phone[-4:]}"


# ═══════════════════════════════════════════════════════════════════
# CATALOG PDF
# ═══════════════════════════════════════════════════════════════════


def _generate_catalog_pdf_sync(
    filepath: Path,
    items: list[CatalogItem],
    distributor_name: str,
    generated_at: datetime,
) -> bool:
    """Generate a catalog PDF (blocking I/O).

    Args:
        filepath: Where to save the PDF.
        items: All active catalog items.
        distributor_name: Business name for the header.
        generated_at: Timestamp for the footer.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=A4,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
        )

        styles = getSampleStyleSheet()
        elements: list[Any] = []

        # Title
        title_style = ParagraphStyle(
            "CatalogTitle",
            parent=styles["Title"],
            fontSize=18,
            textColor=colors.HexColor("#2F5496"),
            spaceAfter=6 * mm,
        )
        elements.append(Paragraph(f"{distributor_name} — Product Catalog", title_style))

        # Subtitle with date
        subtitle_style = ParagraphStyle(
            "CatalogSubtitle",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=8 * mm,
        )
        date_str = generated_at.strftime("%d %B %Y, %H:%M UTC")
        total_items = len(items)
        in_stock = sum(1 for i in items if i.is_in_stock)
        elements.append(Paragraph(
            f"Generated: {date_str} | Total Products: {total_items} | In Stock: {in_stock}",
            subtitle_style,
        ))

        # Group items by category
        categories: dict[str, list[CatalogItem]] = {}
        for item in items:
            cat = item.category or "Uncategorized"
            categories.setdefault(cat, []).append(item)

        cat_header_style = ParagraphStyle(
            "CatHeader",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=colors.HexColor("#2F5496"),
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
        )
        cell_style = ParagraphStyle(
            "CellText",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
        )

        for category, cat_items in sorted(categories.items()):
            elements.append(Paragraph(f"{category} ({len(cat_items)} items)", cat_header_style))

            # Table header
            table_data: list[list[Any]] = [[
                Paragraph("<b>Medicine</b>", cell_style),
                Paragraph("<b>Form</b>", cell_style),
                Paragraph("<b>Strength</b>", cell_style),
                Paragraph("<b>Unit</b>", cell_style),
                Paragraph("<b>Price</b>", cell_style),
                Paragraph("<b>Stock</b>", cell_style),
            ]]

            for item in cat_items:
                name_text = item.medicine_name
                if item.generic_name:
                    name_text += f"<br/><i><font size='7'>{item.generic_name}</font></i>"

                form_str = (
                    item.form.value if hasattr(item.form, "value") and item.form
                    else str(item.form or "—")
                )
                strength_str = item.strength or "—"
                unit_str = item.unit or "—"
                price_str = _paisas_to_pkr_str(item.price_per_unit_paisas)

                stock_text = "In Stock" if item.is_in_stock else "Out of Stock"
                stock_color = "#228B22" if item.is_in_stock else "#CC1919"
                stock_str = f"<font color='{stock_color}'>{stock_text}</font>"
                if item.is_in_stock and item.stock_quantity > 0:
                    stock_str = f"<font color='{stock_color}'>{item.stock_quantity}</font>"

                table_data.append([
                    Paragraph(name_text, cell_style),
                    Paragraph(form_str, cell_style),
                    Paragraph(strength_str, cell_style),
                    Paragraph(unit_str, cell_style),
                    Paragraph(price_str, cell_style),
                    Paragraph(stock_str, cell_style),
                ])

            # Column widths (total ~17cm for A4 with margins)
            col_widths = [5.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2.5 * cm, 2.5 * cm]

            table = Table(table_data, colWidths=col_widths, repeatRows=1)

            # Table styling
            style_commands: list[Any] = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]

            # Alternating row colours
            for row_idx in range(1, len(table_data)):
                if row_idx % 2 == 0:
                    style_commands.append(
                        ("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F0F2F5"))
                    )

            table.setStyle(TableStyle(style_commands))
            elements.append(table)
            elements.append(Spacer(1, 4 * mm))

        # Footer
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=7,
            textColor=colors.grey,
            alignment=1,  # Center
        )
        elements.append(Spacer(1, 8 * mm))
        elements.append(Paragraph(
            f"Generated by TELETRAAN — {distributor_name}",
            footer_style,
        ))

        doc.build(elements)
        return True

    except Exception as exc:
        logger.error(
            "pdf.catalog_generation_failed",
            path=str(filepath),
            error=str(exc),
        )
        return False


async def generate_catalog_pdf(
    items: list[CatalogItem],
    distributor_id: str,
    distributor_name: str,
) -> Path | None:
    """Generate a catalog PDF for a distributor's active products.

    Args:
        items: All active catalog items to include.
        distributor_id: Distributor UUID for the filename.
        distributor_name: Business name for the header.

    Returns:
        Path to the generated PDF on success, ``None`` on failure.
    """
    _ensure_reports_dir()
    filepath = _REPORTS_DIR / f"catalog_{distributor_id}.pdf"
    generated_at = datetime.now(timezone.utc)

    success = await asyncio.to_thread(
        _generate_catalog_pdf_sync,
        filepath,
        items,
        distributor_name,
        generated_at,
    )

    if success:
        logger.info(
            "pdf.catalog_generated",
            distributor_id=distributor_id,
            items_count=len(items),
            path=str(filepath),
        )
        return filepath

    return None


# ═══════════════════════════════════════════════════════════════════
# ORDER RECEIPT PDF
# ═══════════════════════════════════════════════════════════════════


def _generate_receipt_pdf_sync(
    filepath: Path,
    order: Order,
    items: list[OrderItem],
    customer_name: str,
    shop_name: str,
    address: str,
    city: str,
    customer_phone: str,
    distributor_name: str,
) -> bool:
    """Generate an order receipt PDF (blocking I/O).

    Args:
        filepath: Where to save the PDF.
        order: The confirmed order.
        items: Line items.
        customer_name: Customer full name.
        shop_name: Shop name.
        address: Delivery address.
        city: Customer city.
        customer_phone: Customer phone (will be masked).
        distributor_name: Distributor business name.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=A4,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        elements: list[Any] = []

        # Header
        title_style = ParagraphStyle(
            "ReceiptTitle",
            parent=styles["Title"],
            fontSize=16,
            textColor=colors.HexColor("#2F5496"),
            spaceAfter=2 * mm,
        )
        elements.append(Paragraph(f"Order Receipt — #{order.order_number}", title_style))

        # Distributor name
        dist_style = ParagraphStyle(
            "DistName",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.grey,
            spaceAfter=6 * mm,
        )
        elements.append(Paragraph(distributor_name, dist_style))

        # Order info section
        info_style = ParagraphStyle(
            "InfoText",
            parent=styles["Normal"],
            fontSize=9,
            leading=14,
        )

        confirmed_at = order.updated_at or order.created_at
        date_str = confirmed_at.strftime("%d %B %Y, %H:%M")
        masked_phone = _mask_phone(customer_phone)

        # Status
        status = (
            order.status.value
            if hasattr(order.status, "value")
            else str(order.status)
        ).upper()

        info_lines = [
            f"<b>Date:</b> {date_str}",
            f"<b>Customer:</b> {customer_name}",
            f"<b>Shop:</b> {shop_name}",
            f"<b>Address:</b> {address or 'N/A'}{f', {city}' if city else ''}",
            f"<b>Phone:</b> {masked_phone}",
            f"<b>Status:</b> {status}",
        ]

        if order.payment_method:
            payment = (
                order.payment_method.value
                if hasattr(order.payment_method, "value")
                else str(order.payment_method)
            ).replace("_", " ").title()
            info_lines.append(f"<b>Payment:</b> {payment}")

        for line in info_lines:
            elements.append(Paragraph(line, info_style))

        elements.append(Spacer(1, 6 * mm))

        # Items table
        cell_style = ParagraphStyle(
            "CellText",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
        )

        table_data: list[list[Any]] = [[
            Paragraph("<b>#</b>", cell_style),
            Paragraph("<b>Item</b>", cell_style),
            Paragraph("<b>Qty</b>", cell_style),
            Paragraph("<b>Unit Price</b>", cell_style),
            Paragraph("<b>Discount</b>", cell_style),
            Paragraph("<b>Total</b>", cell_style),
        ]]

        for idx, item in enumerate(items, start=1):
            unit_price = _paisas_to_pkr_str(item.price_per_unit_paisas)
            discount = _paisas_to_pkr_str(item.discount_paisas) if item.discount_paisas > 0 else "—"
            line_total = _paisas_to_pkr_str(item.line_total_paisas)

            name_text = item.medicine_name
            if item.unit:
                name_text += f" ({item.unit})"
            if item.bonus_units_given > 0:
                name_text += f"<br/><i><font size='7'>+{item.bonus_units_given} bonus</font></i>"

            table_data.append([
                Paragraph(str(idx), cell_style),
                Paragraph(name_text, cell_style),
                Paragraph(str(item.quantity_ordered), cell_style),
                Paragraph(unit_price, cell_style),
                Paragraph(discount, cell_style),
                Paragraph(line_total, cell_style),
            ])

        col_widths = [1 * cm, 6 * cm, 1.5 * cm, 3 * cm, 2.5 * cm, 3 * cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        style_commands: list[Any] = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("ALIGN", (3, 0), (5, -1), "RIGHT"),
        ]

        # Alternating rows
        for row_idx in range(1, len(table_data)):
            if row_idx % 2 == 0:
                style_commands.append(
                    ("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F0F2F5"))
                )

        table.setStyle(TableStyle(style_commands))
        elements.append(table)

        # Totals section
        elements.append(Spacer(1, 4 * mm))

        totals_style = ParagraphStyle(
            "TotalsText",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            alignment=2,  # Right
        )

        subtotal = _paisas_to_pkr_str(order.subtotal_paisas)
        elements.append(Paragraph(f"<b>Subtotal:</b> {subtotal}", totals_style))

        if order.discount_paisas > 0:
            discount_str = _paisas_to_pkr_str(order.discount_paisas)
            elements.append(Paragraph(
                f"<b>Discount:</b> <font color='#228B22'>-{discount_str}</font>",
                totals_style,
            ))

        if order.delivery_charges_paisas > 0:
            delivery_str = _paisas_to_pkr_str(order.delivery_charges_paisas)
            elements.append(Paragraph(
                f"<b>Delivery:</b> {delivery_str}",
                totals_style,
            ))

        elements.append(Spacer(1, 2 * mm))

        grand_total_style = ParagraphStyle(
            "GrandTotal",
            parent=styles["Normal"],
            fontSize=14,
            textColor=colors.HexColor("#2F5496"),
            alignment=2,  # Right
            spaceBefore=2 * mm,
        )
        total_str = _paisas_to_pkr_str(order.total_paisas)
        elements.append(Paragraph(f"<b>TOTAL: {total_str}</b>", grand_total_style))

        # Footer
        elements.append(Spacer(1, 12 * mm))
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=7,
            textColor=colors.grey,
            alignment=1,  # Center
        )
        elements.append(Paragraph(
            f"Generated by TELETRAAN — {distributor_name} | "
            f"Order #{order.order_number} | {date_str}",
            footer_style,
        ))

        doc.build(elements)
        return True

    except Exception as exc:
        logger.error(
            "pdf.receipt_generation_failed",
            path=str(filepath),
            error=str(exc),
        )
        return False


async def generate_order_receipt(
    order: Order,
    items: list[OrderItem],
    customer_name: str,
    shop_name: str,
    address: str,
    city: str,
    customer_phone: str,
    distributor_name: str,
) -> Path | None:
    """Generate a printable PDF receipt for a confirmed order.

    Args:
        order: The confirmed order.
        items: Line items for the order.
        customer_name: Customer full name.
        shop_name: Shop / pharmacy name.
        address: Delivery address.
        city: Customer city.
        customer_phone: Customer phone number (masked in output).
        distributor_name: Distributor business name.

    Returns:
        Path to the generated PDF on success, ``None`` on failure.
    """
    _ensure_reports_dir()
    filepath = _REPORTS_DIR / f"receipt_{order.order_number}.pdf"

    success = await asyncio.to_thread(
        _generate_receipt_pdf_sync,
        filepath,
        order,
        items,
        customer_name,
        shop_name,
        address,
        city,
        customer_phone,
        distributor_name,
    )

    if success:
        logger.info(
            "pdf.receipt_generated",
            order_number=order.order_number,
            path=str(filepath),
        )
        return filepath

    return None
