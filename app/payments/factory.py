"""Payment gateway factory — gateway instantiation and selection.

The factory reads ``ACTIVE_PAYMENT_GATEWAY`` from settings and
returns the appropriate concrete ``PaymentGateway`` instance.
Supports per-distributor overrides via ``preferred_payment_gateway``.

Usage::

    from app.payments.factory import get_gateway

    gateway = get_gateway()            # system default
    gateway = get_gateway("safepay")   # explicit selection
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import PaymentGatewayError
from app.payments.base import PaymentGateway
from app.payments.gateways.bank_transfer import BankTransferGateway
from app.payments.gateways.dummy_gateway import DummyGateway
from app.payments.gateways.easypaisa import EasyPaisaGateway
from app.payments.gateways.jazzcash import JazzCashGateway
from app.payments.gateways.nayapay import NayaPayGateway
from app.payments.gateways.safepay import SafePayGateway


# ── Gateway registry ────────────────────────────────────────────────
# Maps gateway name → class.  Adding a new gateway = add one line.
_GATEWAY_REGISTRY: dict[str, type[PaymentGateway]] = {
    "jazzcash": JazzCashGateway,
    "easypaisa": EasyPaisaGateway,
    "safepay": SafePayGateway,
    "nayapay": NayaPayGateway,
    "bank_transfer": BankTransferGateway,
    "dummy": DummyGateway,
}

# ── Singleton cache ─────────────────────────────────────────────────
# Gateways are stateless (credentials read from settings each call)
# so a single instance per gateway type suffices.
_GATEWAY_CACHE: dict[str, PaymentGateway] = {}


def get_gateway(
    gateway_name: Optional[str] = None,
    *,
    distributor_preferred: Optional[str] = None,
) -> PaymentGateway:
    """Return a payment gateway instance.

    Resolution order:
    1. Explicit ``gateway_name`` argument.
    2. Distributor's ``preferred_payment_gateway`` override.
    3. System default from ``ACTIVE_PAYMENT_GATEWAY`` env var.

    Args:
        gateway_name: Explicit gateway name override.
        distributor_preferred: Per-distributor gateway preference
            (from distributor model).

    Returns:
        Concrete ``PaymentGateway`` instance.

    Raises:
        PaymentGatewayError: If the gateway name is unknown or
            dummy is requested in production.
    """
    settings = get_settings()

    # Resolve gateway name
    name = gateway_name or distributor_preferred or settings.active_payment_gateway
    name = name.lower().strip()

    # Production guard for dummy gateway
    if name == "dummy" and settings.app_env == "production":
        raise PaymentGatewayError(
            "Dummy gateway is blocked in production. "
            "Set ACTIVE_PAYMENT_GATEWAY to a real gateway.",
            operation="get_gateway",
        )

    # Validate gateway name
    if name not in _GATEWAY_REGISTRY:
        raise PaymentGatewayError(
            f"Unknown payment gateway: '{name}'. "
            f"Available: {', '.join(sorted(_GATEWAY_REGISTRY.keys()))}",
            operation="get_gateway",
        )

    # Return cached or create new
    if name not in _GATEWAY_CACHE:
        _GATEWAY_CACHE[name] = _GATEWAY_REGISTRY[name]()
        logger.info("payment.factory.gateway_created", gateway=name)

    return _GATEWAY_CACHE[name]


def get_all_gateway_names() -> list[str]:
    """Return all registered gateway names.

    Returns:
        Sorted list of gateway name strings.
    """
    return sorted(_GATEWAY_REGISTRY.keys())


def get_available_gateways() -> list[str]:
    """Return gateway names that are available in the current environment.

    In production, dummy is excluded.

    Returns:
        Sorted list of available gateway names.
    """
    settings = get_settings()
    names = list(_GATEWAY_REGISTRY.keys())
    if settings.app_env == "production":
        names = [n for n in names if n != "dummy"]
    return sorted(names)


def clear_gateway_cache() -> None:
    """Clear the singleton gateway cache.

    Used by tests to ensure a clean state.
    """
    _GATEWAY_CACHE.clear()
