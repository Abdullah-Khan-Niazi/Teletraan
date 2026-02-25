"""Email dispatch via Resend.com — send reports to distributors.

Supports plain-text summaries, Excel file attachments, and PDF
attachments.  Gracefully degrades when ``resend_api_key`` is not
configured — all ``send_*`` methods return ``None`` with a warning log
instead of raising.
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
from datetime import date
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.core.config import get_settings


# ═══════════════════════════════════════════════════════════════════
# EMAIL CLIENT WRAPPER
# ═══════════════════════════════════════════════════════════════════


class EmailDispatcher:
    """Thin wrapper around the Resend SDK for sending reports.

    All methods are async (delegated to ``asyncio.to_thread``).
    If ``resend_api_key`` is not set, every send returns ``None``.
    """

    def __init__(self) -> None:
        self._configured: bool | None = None

    # ── Configuration check ─────────────────────────────────────────

    def _is_configured(self) -> bool:
        """Lazily check whether Resend API key is present."""
        if self._configured is None:
            settings = get_settings()
            self._configured = bool(settings.resend_api_key)
            if not self._configured:
                logger.warning(
                    "email.not_configured",
                    detail="resend_api_key is not set — email dispatch disabled",
                )
        return self._configured

    def _get_from_address(self) -> str:
        """Resolve the sender address from settings."""
        settings = get_settings()
        return settings.email_from_address

    # ── Core send ───────────────────────────────────────────────────

    async def _send_email(
        self,
        *,
        to: list[str],
        subject: str,
        html: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Send an email via Resend.

        All file I/O happens in a thread to avoid blocking the loop.

        Args:
            to: Recipient email addresses.
            subject: Email subject line.
            html: HTML body content.
            attachments: Optional list of Resend attachment dicts
                         (``filename``, ``content`` as base64 bytes).

        Returns:
            Resend API response dict on success, ``None`` on failure.
        """
        if not self._is_configured():
            return None

        if not to:
            logger.warning("email.no_recipients", subject=subject)
            return None

        settings = get_settings()

        def _send_sync() -> dict[str, Any]:
            import resend

            resend.api_key = settings.resend_api_key

            params: dict[str, Any] = {
                "from_": self._get_from_address(),
                "to": to,
                "subject": subject,
                "html": html,
            }

            if attachments:
                params["attachments"] = attachments

            email = resend.Emails.send(params)
            return email  # type: ignore[return-value]

        try:
            result = await asyncio.to_thread(_send_sync)
            logger.info(
                "email.sent",
                to_count=len(to),
                subject=subject,
                email_id=result.get("id") if isinstance(result, dict) else str(result),
            )
            return result if isinstance(result, dict) else {"id": str(result)}
        except Exception as exc:
            logger.error(
                "email.send_failed",
                to_count=len(to),
                subject=subject,
                error=str(exc),
            )
            return None

    # ── Attachment helpers ──────────────────────────────────────────

    @staticmethod
    async def _file_to_attachment(filepath: Path) -> dict[str, Any] | None:
        """Read a local file and encode it as a Resend attachment.

        Args:
            filepath: Path to the file on disk.

        Returns:
            Resend attachment dict or ``None`` if the file is missing.
        """
        if not filepath.exists():
            logger.warning(
                "email.attachment_missing",
                path=str(filepath),
            )
            return None

        def _read_sync() -> dict[str, Any]:
            content = filepath.read_bytes()
            mime_type = mimetypes.guess_type(filepath.name)[0] or "application/octet-stream"
            return {
                "filename": filepath.name,
                "content": list(content),
                "type": mime_type,
            }

        try:
            return await asyncio.to_thread(_read_sync)
        except Exception as exc:
            logger.error(
                "email.attachment_read_failed",
                path=str(filepath),
                error=str(exc),
            )
            return None

    # ── Public API: Daily Summary ───────────────────────────────────

    async def send_daily_summary(
        self,
        *,
        to_email: str,
        distributor_name: str,
        report_date: date,
        summary_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Send the daily analytics summary via email.

        Args:
            to_email: Distributor owner email.
            distributor_name: Business name for the subject line.
            report_date: The date being reported.
            summary_data: Output from ``AnalyticsReportService.get_daily_summary()``.

        Returns:
            Resend response on success, ``None`` on failure.
        """
        subject = f"📊 TELETRAAN Daily Report — {distributor_name} — {report_date}"

        if not summary_data.get("has_data"):
            html = _build_no_data_html(report_date, distributor_name)
        else:
            html = _build_daily_summary_html(summary_data, distributor_name)

        return await self._send_email(
            to=[to_email],
            subject=subject,
            html=html,
        )

    # ── Public API: Excel Report ────────────────────────────────────

    async def send_excel_report(
        self,
        *,
        to_email: str,
        distributor_name: str,
        report_date: date,
        excel_path: Path,
        period_label: str = "Monthly",
    ) -> dict[str, Any] | None:
        """Send an Excel report file as an email attachment.

        Args:
            to_email: Distributor owner email.
            distributor_name: Business name for the subject line.
            report_date: Reference date for the report.
            excel_path: Path to the ``.xlsx`` file.
            period_label: ``"Daily"``, ``"Weekly"``, or ``"Monthly"``.

        Returns:
            Resend response on success, ``None`` on failure.
        """
        attachment = await self._file_to_attachment(excel_path)
        if attachment is None:
            logger.error(
                "email.excel_report_no_file",
                path=str(excel_path),
            )
            return None

        subject = (
            f"📊 TELETRAAN {period_label} Excel Report — "
            f"{distributor_name} — {report_date}"
        )

        html = _build_excel_report_html(
            distributor_name, period_label, report_date,
        )

        return await self._send_email(
            to=[to_email],
            subject=subject,
            html=html,
            attachments=[attachment],
        )

    # ── Public API: Monthly PDF Report ──────────────────────────────

    async def send_monthly_report(
        self,
        *,
        to_email: str,
        distributor_name: str,
        month_label: str,
        summary_data: dict[str, Any],
        excel_path: Path | None = None,
    ) -> dict[str, Any] | None:
        """Send a monthly analytics report email with optional Excel.

        Args:
            to_email: Distributor owner email.
            distributor_name: Business name.
            month_label: Human-readable month (e.g. ``"January 2025"``).
            summary_data: Output from ``AnalyticsReportService.get_monthly_summary()``.
            excel_path: Optional Excel file to attach.

        Returns:
            Resend response on success, ``None`` on failure.
        """
        subject = (
            f"📊 TELETRAAN Monthly Report — {distributor_name} — {month_label}"
        )

        html = _build_monthly_report_html(
            summary_data, distributor_name, month_label,
        )

        attachments: list[dict[str, Any]] = []
        if excel_path:
            attachment = await self._file_to_attachment(excel_path)
            if attachment:
                attachments.append(attachment)

        return await self._send_email(
            to=[to_email],
            subject=subject,
            html=html,
            attachments=attachments or None,
        )

    # ── Public API: Churn Alert ─────────────────────────────────────

    async def send_churn_alert(
        self,
        *,
        to_email: str,
        distributor_name: str,
        churning_customers: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Send a churn risk alert email to the distributor.

        Args:
            to_email: Distributor owner email.
            distributor_name: Business name.
            churning_customers: List of dicts with customer_name,
                                days_inactive, severity.

        Returns:
            Resend response on success, ``None`` on failure.
        """
        if not churning_customers:
            return None

        subject = (
            f"⚠️ TELETRAAN Churn Alert — {distributor_name} — "
            f"{len(churning_customers)} customer(s) at risk"
        )

        html = _build_churn_alert_html(
            distributor_name, churning_customers,
        )

        return await self._send_email(
            to=[to_email],
            subject=subject,
            html=html,
        )


# ═══════════════════════════════════════════════════════════════════
# HTML BUILDERS (private)
# ═══════════════════════════════════════════════════════════════════


def _html_wrapper(title: str, body: str) -> str:
    """Wrap content in a styled HTML email template.

    Args:
        title: Email heading.
        body: Inner HTML content.

    Returns:
        Complete HTML string.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 0; padding: 0; background: #f7f7f7; }}
  .container {{ max-width: 600px; margin: 20px auto; background: #fff;
                border-radius: 8px; overflow: hidden;
                box-shadow: 0 2px 6px rgba(0,0,0,.08); }}
  .header {{ background: #075e54; color: #fff; padding: 20px 24px; }}
  .header h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
  .body {{ padding: 24px; color: #333; line-height: 1.6; }}
  .metric {{ display: inline-block; background: #f0faf0; padding: 12px 16px;
             border-radius: 6px; margin: 4px; text-align: center;
             min-width: 100px; }}
  .metric .value {{ font-size: 22px; font-weight: 700; color: #075e54; }}
  .metric .label {{ font-size: 12px; color: #666; margin-top: 2px; }}
  .section {{ margin-top: 20px; }}
  .section h3 {{ margin-bottom: 8px; color: #075e54; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; }}
  th {{ background: #f9f9f9; font-size: 13px; color: #666; }}
  .footer {{ padding: 16px 24px; text-align: center; font-size: 12px; color: #999;
             border-top: 1px solid #eee; }}
  .badge-warning {{ background: #fff3cd; color: #856404; padding: 2px 8px;
                    border-radius: 4px; font-size: 12px; }}
  .badge-critical {{ background: #f8d7da; color: #721c24; padding: 2px 8px;
                     border-radius: 4px; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>{title}</h1></div>
  <div class="body">{body}</div>
  <div class="footer">
    Powered by TELETRAAN — WhatsApp Automation for Medicine Distributors
  </div>
</div>
</body>
</html>"""


def _build_no_data_html(report_date: date, distributor_name: str) -> str:
    """Build email for days with no analytics data."""
    body = f"""
    <p>Salam, <strong>{_esc(distributor_name)}</strong>!</p>
    <p>Aaj ({report_date}) ka koi order data nahi mila.
       Agar system mein koi issue hai, toh TELETRAAN support se contact karein.</p>
    """
    return _html_wrapper(f"Daily Report — {report_date}", body)


def _build_daily_summary_html(data: dict[str, Any], name: str) -> str:
    """Build rich HTML for the daily analytics summary."""
    body = f"""
    <p>Salam, <strong>{_esc(name)}</strong>! Yeh aaj ka report hai:</p>

    <div style="text-align: center; margin: 16px 0;">
      <div class="metric">
        <div class="value">{data.get('orders_confirmed', 0)}</div>
        <div class="label">Orders</div>
      </div>
      <div class="metric">
        <div class="value">{data.get('revenue', 'PKR 0')}</div>
        <div class="label">Revenue</div>
      </div>
      <div class="metric">
        <div class="value">{data.get('new_customers', 0)}</div>
        <div class="label">New Customers</div>
      </div>
    </div>

    <div class="section">
      <h3>Order Breakdown</h3>
      <table>
        <tr><td>Confirmed</td><td><strong>{data.get('orders_confirmed', 0)}</strong></td></tr>
        <tr><td>Pending</td><td>{data.get('orders_pending', 0)}</td></tr>
        <tr><td>Cancelled</td><td>{data.get('orders_cancelled', 0)}</td></tr>
      </table>
    </div>

    <div class="section">
      <h3>Highlights</h3>
      <table>
        <tr><td>Average Order Value</td><td>{data.get('avg_order', 'N/A')}</td></tr>
        <tr><td>Unique Customers</td><td>{data.get('unique_customers', 0)}</td></tr>
        <tr><td>Top Item</td><td>{_esc(str(data.get('top_item', 'N/A')))}</td></tr>
        <tr><td>Messages Processed</td><td>{data.get('messages_processed', 0)}</td></tr>
        <tr><td>AI Cost</td><td>{data.get('ai_cost', 'N/A')}</td></tr>
      </table>
    </div>
    """
    return _html_wrapper(f"Daily Report — {data.get('date', '')}", body)


def _build_excel_report_html(
    name: str,
    period: str,
    report_date: date,
) -> str:
    """Build HTML body for an email with an Excel attachment."""
    body = f"""
    <p>Salam, <strong>{_esc(name)}</strong>!</p>
    <p>Aapka <strong>{period}</strong> Excel report ({report_date}) attach hai.
       Is mein saare order details hain — download karke review karein.</p>
    <p style="color: #666; font-size: 13px;">
      Agar yeh report galat schedule par aa raha hai, toh TELETRAAN
      se <code>/schedule</code> command se change karein.
    </p>
    """
    return _html_wrapper(f"{period} Excel Report — {report_date}", body)


def _build_monthly_report_html(
    data: dict[str, Any],
    name: str,
    month_label: str,
) -> str:
    """Build HTML for the monthly analytics email."""
    from app.analytics.order_analytics import paisas_to_pkr

    revenue = paisas_to_pkr(data.get("orders_total_paisas", 0))
    mom_rev = data.get("mom_revenue_change", 0)
    mom_rev_str = f"{mom_rev:+.1f}%" if mom_rev else "N/A"

    # Top items table
    top_items_rows = ""
    for i, item in enumerate(data.get("top_items", [])[:5], 1):
        top_items_rows += (
            f"<tr><td>{i}</td>"
            f"<td>{_esc(item['name'])}</td>"
            f"<td>{item['units']}</td>"
            f"<td>{paisas_to_pkr(item['revenue'])}</td></tr>"
        )

    body = f"""
    <p>Salam, <strong>{_esc(name)}</strong>! Is mahine ka summary:</p>

    <div style="text-align: center; margin: 16px 0;">
      <div class="metric">
        <div class="value">{data.get('orders_confirmed', 0)}</div>
        <div class="label">Total Orders</div>
      </div>
      <div class="metric">
        <div class="value">{revenue}</div>
        <div class="label">Revenue</div>
      </div>
      <div class="metric">
        <div class="value">{mom_rev_str}</div>
        <div class="label">vs Last Month</div>
      </div>
    </div>

    <div class="section">
      <h3>Top Medicines</h3>
      <table>
        <tr><th>#</th><th>Medicine</th><th>Units</th><th>Revenue</th></tr>
        {top_items_rows}
      </table>
    </div>

    <div class="section">
      <h3>Key Metrics</h3>
      <table>
        <tr><td>New Customers</td><td>{data.get('new_customers', 0)}</td></tr>
        <tr><td>Customer Growth</td><td>{data.get('mom_customers_change', 0):+.1f}%</td></tr>
        <tr><td>Order Growth</td><td>{data.get('mom_orders_change', 0):+.1f}%</td></tr>
      </table>
    </div>
    """
    return _html_wrapper(f"Monthly Report — {month_label}", body)


def _build_churn_alert_html(
    name: str,
    customers: list[dict[str, Any]],
) -> str:
    """Build HTML for the churn alert email."""
    rows = ""
    for c in customers:
        severity = c.get("severity", "warning")
        badge_class = "badge-critical" if severity == "critical" else "badge-warning"
        rows += (
            f"<tr>"
            f"<td>{_esc(c.get('customer_name', 'Unknown'))}</td>"
            f"<td>{c.get('days_inactive', '?')} days</td>"
            f"<td><span class='{badge_class}'>{severity.upper()}</span></td>"
            f"</tr>"
        )

    body = f"""
    <p>Salam, <strong>{_esc(name)}</strong>!</p>
    <p>⚠️ <strong>{len(customers)} customer(s)</strong> inactive hain aur
       churn risk mein hain. In se jaldi contact karein:</p>

    <table>
      <tr><th>Customer</th><th>Inactive Since</th><th>Severity</th></tr>
      {rows}
    </table>

    <p style="margin-top: 16px; color: #666; font-size: 13px;">
      Critical = 42+ din se inactive | Warning = 21+ din se inactive
    </p>
    """
    return _html_wrapper("⚠️ Churn Risk Alert", body)


def _esc(text: str) -> str:
    """Escape HTML special characters.

    Args:
        text: Raw text.

    Returns:
        HTML-safe text.
    """
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ═══════════════════════════════════════════════════════════════════
# MODULE SINGLETON
# ═══════════════════════════════════════════════════════════════════


email_dispatcher = EmailDispatcher()
