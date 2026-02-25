"""System analytics — AI usage/cost, gateway performance, error rates.

Queries the analytics_events table for AI and system metrics, then
returns values suitable for merging into a DailyAnalyticsCreate payload.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.db.client import get_db_client


async def compute_system_metrics(
    distributor_id: str,
    target_date: date,
) -> dict[str, Any]:
    """Compute AI and system performance metrics for a single date.

    Queries analytics_events and sessions for the given distributor+date.

    Args:
        distributor_id: Tenant scope.
        target_date: Calendar date.

    Returns:
        Dict with system-related metric keys for the daily aggregation.
    """
    start_ts = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end_ts = start_ts + timedelta(days=1)

    ai_metrics = await _compute_ai_metrics(distributor_id, start_ts, end_ts)
    session_metrics = await _compute_session_metrics(distributor_id, start_ts, end_ts)

    return {**ai_metrics, **session_metrics}


async def _compute_ai_metrics(
    distributor_id: str,
    start_ts: datetime,
    end_ts: datetime,
) -> dict[str, Any]:
    """Compute AI provider cost and call count from analytics_events.

    Args:
        distributor_id: Tenant scope.
        start_ts: Range start.
        end_ts: Range end.

    Returns:
        Dict with ``ai_calls_count`` and ``ai_cost_paisas``.
    """
    client = get_db_client()
    try:
        result = (
            await client.table("analytics_events")
            .select("ai_provider, ai_tokens_used, ai_cost_paisas, duration_ms")
            .eq("distributor_id", distributor_id)
            .gte("occurred_at", start_ts.isoformat())
            .lt("occurred_at", end_ts.isoformat())
            .not_.is_("ai_provider", "null")
            .execute()
        )
    except Exception as exc:
        logger.error(
            "analytics.ai_metrics_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return {"ai_calls_count": 0, "ai_cost_paisas": 0}

    rows = result.data
    total_cost = sum(r.get("ai_cost_paisas", 0) or 0 for r in rows)

    logger.info(
        "analytics.ai_metrics_computed",
        distributor_id=distributor_id,
        ai_calls=len(rows),
        ai_cost=total_cost,
    )

    return {
        "ai_calls_count": len(rows),
        "ai_cost_paisas": total_cost,
    }


async def _compute_session_metrics(
    distributor_id: str,
    start_ts: datetime,
    end_ts: datetime,
) -> dict[str, Any]:
    """Compute session and message metrics from analytics_events.

    Looks for event types: ``message.processed``, ``voice_note.received``,
    ``fallback.triggered``.

    Args:
        distributor_id: Tenant scope.
        start_ts: Range start.
        end_ts: Range end.

    Returns:
        Dict with messages_processed, voice_notes_count,
        fallback_responses, avg_response_ms.
    """
    client = get_db_client()
    try:
        result = (
            await client.table("analytics_events")
            .select("event_type, duration_ms")
            .eq("distributor_id", distributor_id)
            .gte("occurred_at", start_ts.isoformat())
            .lt("occurred_at", end_ts.isoformat())
            .execute()
        )
    except Exception as exc:
        logger.error(
            "analytics.session_metrics_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return {
            "messages_processed": 0,
            "voice_notes_count": 0,
            "fallback_responses": 0,
            "avg_response_ms": 0,
        }

    rows = result.data
    messages = [r for r in rows if r.get("event_type") == "message.processed"]
    voice = [r for r in rows if r.get("event_type") == "voice_note.received"]
    fallbacks = [r for r in rows if r.get("event_type") == "fallback.triggered"]

    durations = [r.get("duration_ms", 0) or 0 for r in messages if r.get("duration_ms")]
    avg_ms = sum(durations) // len(durations) if durations else 0

    return {
        "messages_processed": len(messages),
        "voice_notes_count": len(voice),
        "fallback_responses": len(fallbacks),
        "avg_response_ms": avg_ms,
    }


async def compute_gateway_summary(
    distributor_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Compute payment gateway performance summary.

    Groups analytics_events by payment_gateway for the given range.

    Args:
        distributor_id: Tenant scope.
        start_date: Range start.
        end_date: Range end.

    Returns:
        List of dicts with gateway, count, total_ms, and avg_ms.
    """
    client = get_db_client()
    start_ts = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_ts = datetime.combine(
        end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc,
    )

    try:
        result = (
            await client.table("analytics_events")
            .select("payment_gateway, duration_ms")
            .eq("distributor_id", distributor_id)
            .gte("occurred_at", start_ts.isoformat())
            .lt("occurred_at", end_ts.isoformat())
            .not_.is_("payment_gateway", "null")
            .execute()
        )
    except Exception as exc:
        logger.error(
            "analytics.gateway_summary_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return []

    # Group by gateway
    gateways: dict[str, list[int]] = {}
    for row in result.data:
        gw = row.get("payment_gateway", "unknown")
        ms = row.get("duration_ms", 0) or 0
        gateways.setdefault(gw, []).append(ms)

    return [
        {
            "gateway": gw,
            "count": len(durations),
            "total_ms": sum(durations),
            "avg_ms": sum(durations) // len(durations) if durations else 0,
        }
        for gw, durations in sorted(gateways.items())
    ]
