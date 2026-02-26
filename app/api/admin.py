"""Protected admin API for TELETRAAN system management.

All endpoints require the ``X-Admin-Key`` header matching
``Settings.admin_api_key``.  Provides distributor lifecycle management,
system status, gateway/AI health, forced syncs, and announcements.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.constants import SubscriptionStatus
from app.db.models.distributor import DistributorCreate, DistributorUpdate
from app.db.repositories import (
    analytics_repo,
    customer_repo,
    distributor_repo,
    order_repo,
    payment_repo,
    session_repo,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ═══════════════════════════════════════════════════════════════════
# AUTHENTICATION DEPENDENCY
# ═══════════════════════════════════════════════════════════════════


async def verify_admin_key(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> str:
    """Validate the admin API key from the request header.

    Args:
        x_admin_key: Value of the ``X-Admin-Key`` header.

    Returns:
        The validated key string.

    Raises:
        HTTPException: 401 if the key is missing or invalid.
    """
    settings = get_settings()
    if x_admin_key != settings.admin_api_key:
        logger.warning("admin.auth_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key.",
        )
    return x_admin_key


# ═══════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════


class CreateDistributorRequest(BaseModel):
    """Request body for creating a new distributor."""

    business_name: str = Field(..., min_length=1, max_length=255)
    owner_name: str = Field(..., min_length=1, max_length=255)
    whatsapp_number: str = Field(..., min_length=10, max_length=20)
    whatsapp_phone_number_id: str = Field(..., min_length=1)
    city: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    email: Optional[str] = Field(default=None, max_length=255)
    plan_id: Optional[UUID] = None
    trial_days: int = Field(default=14, ge=1, le=90)
    notes: Optional[str] = Field(default=None, max_length=2000)


class ExtendSubscriptionRequest(BaseModel):
    """Request body for extending a distributor's subscription."""

    days: int = Field(..., ge=1, le=365, description="Number of days to extend.")


class AnnouncementRequest(BaseModel):
    """Request body for sending an announcement to distributors."""

    message: str = Field(..., min_length=1, max_length=2000)
    distributor_ids: Optional[list[str]] = Field(
        default=None,
        description="Specific distributor UUIDs. If omitted, sends to all active.",
    )


class AdminResponse(BaseModel):
    """Standard admin API response wrapper."""

    success: bool
    message: str
    data: Any = None


# ═══════════════════════════════════════════════════════════════════
# DISTRIBUTOR MANAGEMENT
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/distributors",
    response_model=AdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def create_distributor(body: CreateDistributorRequest) -> AdminResponse:
    """Create a new distributor with an initial trial subscription.

    The trial period defaults to 14 days if not specified.
    """
    now = datetime.now(tz=timezone.utc)
    trial_end = now + timedelta(days=body.trial_days)

    create_data = DistributorCreate(
        business_name=body.business_name,
        owner_name=body.owner_name,
        whatsapp_number=body.whatsapp_number,
        whatsapp_phone_number_id=body.whatsapp_phone_number_id,
        city=body.city,
        address=body.address,
        email=body.email,
        plan_id=body.plan_id,
        subscription_status=SubscriptionStatus.TRIAL,
        subscription_start=now,
        trial_end=trial_end,
        notes=body.notes,
    )

    distributor = await distributor_repo.create(create_data)
    logger.info(
        "admin.distributor_created",
        distributor_id=str(distributor.id),
        business_name=body.business_name,
    )
    return AdminResponse(
        success=True,
        message=f"Distributor '{body.business_name}' created.",
        data={"distributor_id": str(distributor.id)},
    )


@router.get(
    "/distributors",
    response_model=AdminResponse,
    summary="List all distributors",
    dependencies=[Depends(verify_admin_key)],
)
async def list_distributors() -> AdminResponse:
    """Return a summary of all active (non-deleted) distributors."""
    distributors = await distributor_repo.get_active_distributors()
    items = [
        {
            "id": str(d.id),
            "business_name": d.business_name,
            "owner_name": d.owner_name,
            "city": d.city,
            "subscription_status": d.subscription_status,
            "is_active": d.is_active,
        }
        for d in distributors
    ]
    return AdminResponse(
        success=True,
        message=f"{len(items)} active distributors.",
        data=items,
    )


@router.get(
    "/distributors/{distributor_id}",
    response_model=AdminResponse,
    summary="Get distributor details",
    dependencies=[Depends(verify_admin_key)],
)
async def get_distributor(distributor_id: str) -> AdminResponse:
    """Fetch full details of a single distributor."""
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distributor {distributor_id} not found.",
        )
    return AdminResponse(
        success=True,
        message="Distributor found.",
        data={
            "id": str(distributor.id),
            "business_name": distributor.business_name,
            "owner_name": distributor.owner_name,
            "whatsapp_number": distributor.whatsapp_number,
            "city": distributor.city,
            "email": distributor.email,
            "subscription_status": distributor.subscription_status,
            "subscription_start": (
                distributor.subscription_start.isoformat()
                if distributor.subscription_start
                else None
            ),
            "subscription_end": (
                distributor.subscription_end.isoformat()
                if distributor.subscription_end
                else None
            ),
            "trial_end": (
                distributor.trial_end.isoformat()
                if distributor.trial_end
                else None
            ),
            "is_active": distributor.is_active,
            "onboarding_completed": distributor.onboarding_completed,
            "created_at": distributor.created_at.isoformat(),
        },
    )


@router.post(
    "/distributors/{distributor_id}/suspend",
    response_model=AdminResponse,
    summary="Suspend a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def suspend_distributor(distributor_id: str) -> AdminResponse:
    """Suspend a distributor — sets status to SUSPENDED and is_active=False."""
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distributor {distributor_id} not found.",
        )

    update = DistributorUpdate(
        subscription_status=SubscriptionStatus.SUSPENDED,
        is_active=False,
    )
    await distributor_repo.update(distributor_id, update)
    logger.info(
        "admin.distributor_suspended",
        distributor_id=distributor_id,
    )
    return AdminResponse(
        success=True,
        message=f"Distributor {distributor_id} suspended.",
    )


@router.post(
    "/distributors/{distributor_id}/unsuspend",
    response_model=AdminResponse,
    summary="Unsuspend (reactivate) a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def unsuspend_distributor(distributor_id: str) -> AdminResponse:
    """Re-activate a previously suspended distributor."""
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distributor {distributor_id} not found.",
        )

    update = DistributorUpdate(
        subscription_status=SubscriptionStatus.ACTIVE,
        is_active=True,
    )
    await distributor_repo.update(distributor_id, update)
    logger.info(
        "admin.distributor_unsuspended",
        distributor_id=distributor_id,
    )
    return AdminResponse(
        success=True,
        message=f"Distributor {distributor_id} re-activated.",
    )


@router.post(
    "/distributors/{distributor_id}/extend",
    response_model=AdminResponse,
    summary="Extend distributor subscription",
    dependencies=[Depends(verify_admin_key)],
)
async def extend_subscription(
    distributor_id: str, body: ExtendSubscriptionRequest
) -> AdminResponse:
    """Extend a distributor's subscription_end by the specified days.

    If subscription_end is not set (e.g. trial), uses the current time
    as the base.
    """
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distributor {distributor_id} not found.",
        )

    base = distributor.subscription_end or datetime.now(tz=timezone.utc)
    new_end = base + timedelta(days=body.days)

    update = DistributorUpdate(subscription_end=new_end)
    await distributor_repo.update(distributor_id, update)
    logger.info(
        "admin.subscription_extended",
        distributor_id=distributor_id,
        new_end=new_end.isoformat(),
        days=body.days,
    )
    return AdminResponse(
        success=True,
        message=f"Subscription extended by {body.days} days to {new_end.date()}.",
        data={"new_subscription_end": new_end.isoformat()},
    )


# ═══════════════════════════════════════════════════════════════════
# SYSTEM STATUS
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/status",
    response_model=AdminResponse,
    summary="System status overview",
    dependencies=[Depends(verify_admin_key)],
)
async def system_status() -> AdminResponse:
    """Return system-wide status: DB connectivity, active distributors, config flags."""
    from app.db.client import health_check as db_health_check

    db_ok = await db_health_check()
    settings = get_settings()
    distributors = await distributor_repo.get_active_distributors()

    return AdminResponse(
        success=True,
        message="System status retrieved.",
        data={
            "database": "ok" if db_ok else "unavailable",
            "active_distributors": len(distributors),
            "environment": settings.app_env,
            "ai_provider": settings.active_ai_provider,
            "payment_gateway": settings.active_payment_gateway,
            "feature_flags": {
                "voice_processing": settings.enable_voice_processing,
                "inventory_sync": settings.enable_inventory_sync,
                "excel_reports": settings.enable_excel_reports,
                "channel_b": settings.enable_channel_b,
                "analytics": settings.enable_analytics,
            },
        },
    )


# ═══════════════════════════════════════════════════════════════════
# GATEWAY / AI HEALTH
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/health/gateway",
    response_model=AdminResponse,
    summary="Payment gateway health",
    dependencies=[Depends(verify_admin_key)],
)
async def gateway_health() -> AdminResponse:
    """Report the configured payment gateway and its availability."""
    settings = get_settings()
    gateway_name = settings.active_payment_gateway

    # Check if the gateway has its required credentials configured
    gateway_creds: dict[str, list[str]] = {
        "jazzcash": ["jazzcash_merchant_id", "jazzcash_password"],
        "easypaisa": ["easypaisa_store_id", "easypaisa_hash_key"],
        "safepay": ["safepay_api_key", "safepay_secret_key"],
        "nayapay": ["nayapay_merchant_id", "nayapay_api_key"],
        "bank_transfer": ["bank_account_number", "bank_iban"],
        "dummy": [],
    }

    required = gateway_creds.get(gateway_name, [])
    missing = [f for f in required if not getattr(settings, f, None)]
    configured = len(missing) == 0

    return AdminResponse(
        success=True,
        message="Gateway health retrieved.",
        data={
            "active_gateway": gateway_name,
            "configured": configured,
            "missing_credentials": missing if missing else None,
        },
    )


@router.get(
    "/health/ai",
    response_model=AdminResponse,
    summary="AI provider health",
    dependencies=[Depends(verify_admin_key)],
)
async def ai_health() -> AdminResponse:
    """Report the configured AI provider and key availability."""
    settings = get_settings()
    provider = settings.active_ai_provider
    fallback = settings.ai_fallback_provider

    key_map: dict[str, str] = {
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "cohere": "cohere_api_key",
        "openrouter": "openrouter_api_key",
    }

    primary_key_field = key_map.get(provider, "")
    primary_configured = bool(getattr(settings, primary_key_field, None))

    fallback_configured: bool | None = None
    if fallback:
        fb_key = key_map.get(fallback, "")
        fallback_configured = bool(getattr(settings, fb_key, None))

    return AdminResponse(
        success=True,
        message="AI health retrieved.",
        data={
            "active_provider": provider,
            "primary_configured": primary_configured,
            "fallback_provider": fallback,
            "fallback_configured": fallback_configured,
            "model_override": settings.ai_text_model,
            "premium_model": settings.ai_premium_model,
        },
    )


# ═══════════════════════════════════════════════════════════════════
# OPERATIONS
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/inventory/sync",
    response_model=AdminResponse,
    summary="Force inventory sync for a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def force_inventory_sync(distributor_id: str) -> AdminResponse:
    """Trigger an immediate inventory sync for the specified distributor.

    This enqueues the sync task; the actual sync runs asynchronously.
    """
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distributor {distributor_id} not found.",
        )

    try:
        from app.scheduler.jobs.inventory_jobs import run_inventory_sync

        await run_inventory_sync(distributor_id=distributor_id)
        logger.info(
            "admin.inventory_sync_triggered",
            distributor_id=distributor_id,
        )
        return AdminResponse(
            success=True,
            message=f"Inventory sync triggered for {distributor_id}.",
        )
    except Exception as exc:
        logger.error(
            "admin.inventory_sync_failed",
            distributor_id=distributor_id,
            error=str(exc),
        )
        return AdminResponse(
            success=False,
            message=f"Inventory sync failed: {exc}",
        )


@router.post(
    "/announce",
    response_model=AdminResponse,
    summary="Send announcement to distributors",
    dependencies=[Depends(verify_admin_key)],
)
async def send_announcement(body: AnnouncementRequest) -> AdminResponse:
    """Send a WhatsApp text message to one or more distributors.

    If ``distributor_ids`` is provided, sends only to those distributors.
    Otherwise sends to all active distributors.
    """
    if body.distributor_ids:
        targets: list[dict[str, Any]] = []
        for did in body.distributor_ids:
            d = await distributor_repo.get_by_id(did)
            if d is not None:
                targets.append(
                    {
                        "id": str(d.id),
                        "whatsapp_number": d.whatsapp_number,
                        "phone_number_id": d.whatsapp_phone_number_id,
                    }
                )
    else:
        all_active = await distributor_repo.get_active_distributors()
        targets = [
            {
                "id": str(d.id),
                "whatsapp_number": d.whatsapp_number,
                "phone_number_id": d.whatsapp_phone_number_id,
            }
            for d in all_active
        ]

    if not targets:
        return AdminResponse(
            success=False,
            message="No distributors found to send announcement.",
        )

    sent = 0
    failed = 0
    for target in targets:
        try:
            from app.whatsapp.client import whatsapp_client
            from app.whatsapp.message_types import build_text_message

            payload = build_text_message(
                target["whatsapp_number"], body.message
            )
            await whatsapp_client.send_message(
                phone_number_id=target["phone_number_id"],
                payload=payload,
            )
            sent += 1
        except Exception as exc:
            failed += 1
            logger.error(
                "admin.announcement_send_failed",
                distributor_id=target["id"],
                error=str(exc),
            )

    logger.info(
        "admin.announcement_sent",
        total=len(targets),
        sent=sent,
        failed=failed,
    )
    return AdminResponse(
        success=True,
        message=f"Announcement sent to {sent}/{len(targets)} distributors.",
        data={"sent": sent, "failed": failed},
    )


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD DATA ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/dashboard/overview",
    response_model=AdminResponse,
    summary="Dashboard overview metrics",
    dependencies=[Depends(verify_admin_key)],
)
async def dashboard_overview() -> AdminResponse:
    """Aggregate metrics for the admin dashboard home screen."""
    from app.db.client import health_check as db_health_check

    settings = get_settings()
    db_ok = await db_health_check()
    distributors = await distributor_repo.get_active_distributors()

    total_orders = 0
    total_revenue = 0
    total_customers = 0
    active_sessions = 0
    pending_orders = 0
    recent_orders_list: list[dict] = []

    for d in distributors:
        did = str(d.id)
        try:
            customers = await customer_repo.get_active_customers(did, limit=1000)
            total_customers += len(customers)
        except Exception:
            pass
        try:
            recent = await order_repo.get_recent_orders(did, hours=24)
            total_orders += len(recent)
            for o in recent:
                total_revenue += o.total_paisas
                if o.status == "pending":
                    pending_orders += 1
                recent_orders_list.append({
                    "id": str(o.id),
                    "order_number": o.order_number,
                    "distributor_id": did,
                    "distributor_name": d.business_name,
                    "status": o.status if isinstance(o.status, str) else o.status.value,
                    "total_paisas": o.total_paisas,
                    "payment_status": o.payment_status if isinstance(o.payment_status, str) else o.payment_status.value,
                    "created_at": o.created_at.isoformat(),
                })
        except Exception:
            pass

    recent_orders_list.sort(key=lambda x: x["created_at"], reverse=True)

    return AdminResponse(
        success=True,
        message="Dashboard overview.",
        data={
            "database": "ok" if db_ok else "unavailable",
            "environment": settings.app_env,
            "ai_provider": settings.active_ai_provider,
            "payment_gateway": settings.active_payment_gateway,
            "total_distributors": len(distributors),
            "total_customers": total_customers,
            "orders_today": total_orders,
            "revenue_today_paisas": total_revenue,
            "pending_orders": pending_orders,
            "recent_orders": recent_orders_list[:20],
            "distributors": [
                {
                    "id": str(d.id),
                    "business_name": d.business_name,
                    "owner_name": d.owner_name,
                    "city": d.city,
                    "whatsapp_number": d.whatsapp_number,
                    "subscription_status": d.subscription_status if isinstance(d.subscription_status, str) else d.subscription_status.value,
                    "is_active": d.is_active,
                    "onboarding_completed": d.onboarding_completed,
                    "created_at": d.created_at.isoformat(),
                }
                for d in distributors
            ],
            "feature_flags": {
                "voice_processing": settings.enable_voice_processing,
                "inventory_sync": settings.enable_inventory_sync,
                "excel_reports": settings.enable_excel_reports,
                "channel_b": settings.enable_channel_b,
                "analytics": settings.enable_analytics,
                "credit_accounts": settings.enable_credit_accounts,
            },
        },
    )


@router.get(
    "/dashboard/distributors/{distributor_id}/customers",
    response_model=AdminResponse,
    summary="List customers for a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def list_distributor_customers(
    distributor_id: str, limit: int = 100, offset: int = 0
) -> AdminResponse:
    """Fetch all customers belonging to a distributor."""
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(status_code=404, detail="Distributor not found.")

    customers = await customer_repo.get_active_customers(
        distributor_id, limit=limit, offset=offset
    )
    items = [
        {
            "id": str(c.id),
            "name": c.name,
            "shop_name": c.shop_name,
            "whatsapp_number": c.whatsapp_number,
            "city": c.city,
            "is_verified": c.is_verified,
            "is_blocked": c.is_blocked,
            "blocked_reason": c.blocked_reason,
            "total_orders": c.total_orders,
            "total_spend_paisas": c.total_spend_paisas,
            "last_order_at": c.last_order_at.isoformat() if c.last_order_at else None,
            "registered_at": c.registered_at.isoformat() if c.registered_at else None,
        }
        for c in customers
    ]
    return AdminResponse(
        success=True,
        message=f"{len(items)} customers.",
        data=items,
    )


@router.post(
    "/dashboard/customers/{customer_id}/block",
    response_model=AdminResponse,
    summary="Block a customer",
    dependencies=[Depends(verify_admin_key)],
)
async def block_customer_endpoint(
    customer_id: str, distributor_id: str, reason: str = "Blocked by admin"
) -> AdminResponse:
    """Block a customer from placing orders."""
    try:
        customer = await customer_repo.block_customer(
            customer_id, distributor_id, reason
        )
        return AdminResponse(
            success=True,
            message=f"Customer {customer.name} blocked.",
            data={"id": str(customer.id), "is_blocked": True},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/dashboard/customers/{customer_id}/unblock",
    response_model=AdminResponse,
    summary="Unblock a customer",
    dependencies=[Depends(verify_admin_key)],
)
async def unblock_customer_endpoint(
    customer_id: str, distributor_id: str
) -> AdminResponse:
    """Unblock a previously blocked customer."""
    try:
        customer = await customer_repo.unblock_customer(
            customer_id, distributor_id
        )
        return AdminResponse(
            success=True,
            message=f"Customer {customer.name} unblocked.",
            data={"id": str(customer.id), "is_blocked": False},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/dashboard/distributors/{distributor_id}/orders",
    response_model=AdminResponse,
    summary="List orders for a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def list_distributor_orders(
    distributor_id: str,
    status_filter: Optional[str] = None,
    hours: int = 168,
) -> AdminResponse:
    """Fetch recent orders for a distributor, optionally filtered by status."""
    distributor = await distributor_repo.get_by_id(distributor_id)
    if distributor is None:
        raise HTTPException(status_code=404, detail="Distributor not found.")

    if status_filter:
        orders = await order_repo.get_orders_by_status(
            distributor_id, status_filter
        )
    else:
        orders = await order_repo.get_recent_orders(distributor_id, hours=hours)

    items = [
        {
            "id": str(o.id),
            "order_number": o.order_number,
            "customer_id": str(o.customer_id),
            "status": o.status if isinstance(o.status, str) else o.status.value,
            "total_paisas": o.total_paisas,
            "subtotal_paisas": o.subtotal_paisas,
            "discount_paisas": o.discount_paisas,
            "delivery_charges_paisas": o.delivery_charges_paisas,
            "payment_status": o.payment_status if isinstance(o.payment_status, str) else o.payment_status.value,
            "payment_method": o.payment_method if isinstance(o.payment_method, str) else (o.payment_method.value if o.payment_method else None),
            "source": o.source if isinstance(o.source, str) else o.source.value,
            "notes": o.notes,
            "created_at": o.created_at.isoformat(),
            "updated_at": o.updated_at.isoformat(),
        }
        for o in orders
    ]
    return AdminResponse(
        success=True,
        message=f"{len(items)} orders.",
        data=items,
    )


@router.get(
    "/dashboard/orders/{order_id}/detail",
    response_model=AdminResponse,
    summary="Get order detail with items",
    dependencies=[Depends(verify_admin_key)],
)
async def get_order_detail(order_id: str, distributor_id: str) -> AdminResponse:
    """Fetch full order detail including line items."""
    try:
        order, items = await order_repo.get_order_with_items(
            order_id, distributor_id
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Order not found.")

    return AdminResponse(
        success=True,
        message="Order detail.",
        data={
            "order": {
                "id": str(order.id),
                "order_number": order.order_number,
                "customer_id": str(order.customer_id),
                "status": order.status if isinstance(order.status, str) else order.status.value,
                "total_paisas": order.total_paisas,
                "subtotal_paisas": order.subtotal_paisas,
                "discount_paisas": order.discount_paisas,
                "delivery_charges_paisas": order.delivery_charges_paisas,
                "payment_status": order.payment_status if isinstance(order.payment_status, str) else order.payment_status.value,
                "delivery_address": order.delivery_address,
                "notes": order.notes,
                "internal_notes": order.internal_notes,
                "source": order.source if isinstance(order.source, str) else order.source.value,
                "created_at": order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat(),
            },
            "items": [
                {
                    "id": str(item.id),
                    "medicine_name": item.medicine_name,
                    "quantity_ordered": item.quantity_ordered,
                    "quantity_fulfilled": item.quantity_fulfilled,
                    "price_per_unit_paisas": item.price_per_unit_paisas,
                    "line_total_paisas": item.line_total_paisas,
                    "discount_paisas": item.discount_paisas,
                    "unit": item.unit,
                    "is_out_of_stock_order": item.is_out_of_stock_order,
                    "is_unlisted_item": item.is_unlisted_item,
                }
                for item in items
            ],
        },
    )


@router.get(
    "/dashboard/distributors/{distributor_id}/payments",
    response_model=AdminResponse,
    summary="List payments for a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def list_distributor_payments(
    distributor_id: str, status_filter: Optional[str] = None
) -> AdminResponse:
    """Fetch payments for a distributor, optionally filtered by status."""
    payments = await payment_repo.get_distributor_payments(
        distributor_id, status=status_filter
    )
    items = [
        {
            "id": str(p.id),
            "transaction_reference": p.transaction_reference,
            "order_id": str(p.order_id) if p.order_id else None,
            "gateway": p.gateway if isinstance(p.gateway, str) else p.gateway.value,
            "amount_paisas": p.amount_paisas,
            "status": p.status if isinstance(p.status, str) else p.status.value,
            "payment_link": p.payment_link,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "failure_reason": p.failure_reason,
            "created_at": p.created_at.isoformat(),
        }
        for p in payments
    ]
    return AdminResponse(
        success=True,
        message=f"{len(items)} payments.",
        data=items,
    )


@router.get(
    "/dashboard/distributors/{distributor_id}/sessions",
    response_model=AdminResponse,
    summary="List active sessions for a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def list_distributor_sessions(distributor_id: str) -> AdminResponse:
    """Fetch active sessions for a distributor.

    Note: sessions are per-number within a distributor, fetched via
    the repository's list method if available. Falls back to a
    general query.
    """
    from app.db.client import get_db_client

    try:
        client = get_db_client()
        result = await (
            client.table("sessions")
            .select("*")
            .eq("distributor_id", distributor_id)
            .order("last_message_at", desc=True)
            .limit(50)
            .execute()
        )
        sessions_data = result.data or []
    except Exception:
        sessions_data = []

    items = [
        {
            "id": s.get("id"),
            "whatsapp_number": s.get("whatsapp_number"),
            "customer_id": s.get("customer_id"),
            "channel": s.get("channel"),
            "current_state": s.get("current_state"),
            "language": s.get("language"),
            "handoff_mode": s.get("handoff_mode"),
            "last_message_at": s.get("last_message_at"),
            "expires_at": s.get("expires_at"),
        }
        for s in sessions_data
    ]
    return AdminResponse(
        success=True,
        message=f"{len(items)} sessions.",
        data=items,
    )


@router.get(
    "/dashboard/distributors/{distributor_id}/analytics",
    response_model=AdminResponse,
    summary="Analytics events for a distributor",
    dependencies=[Depends(verify_admin_key)],
)
async def distributor_analytics(
    distributor_id: str, event_type: Optional[str] = None
) -> AdminResponse:
    """Fetch recent analytics events for a distributor."""
    events = await analytics_repo.get_distributor_events(
        distributor_id, event_type=event_type, limit=100
    )
    items = [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "event_data": e.event_data,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
    return AdminResponse(
        success=True,
        message=f"{len(items)} events.",
        data=items,
    )
