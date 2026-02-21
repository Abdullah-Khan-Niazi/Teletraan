---
applyTo: "app/payments/**,app/**/payment*/**,app/**/*gateway*.py,app/**/*payment*.py"
---

# SKILL 09 — PAYMENT GATEWAYS
## Source: `docs/skills/SKILL_payment_gateways.md`

---

## ARCHITECTURE

```
Order Flow / Channel Handler
         ↓
payment_factory.get_gateway()
         ↓
   PaymentGateway (abstract)
         ↓
[jazzcash | easypaisa | safepay | nayapay]
```

Active gateway controlled by `ACTIVE_PAYMENT_GATEWAY` env var.
Switching gateways requires only config change — zero code changes.

---

## ABSTRACT BASE CLASS

```python
class PaymentGateway(ABC):
    @abstractmethod
    async def create_payment_request(
        self,
        order_id: str,
        amount_paisas: int,
        customer_phone: str,
        description: str,
    ) -> PaymentInitResponse: ...

    @abstractmethod
    async def verify_callback(
        self,
        payload: dict,
        raw_body: bytes,
        headers: dict,
    ) -> PaymentCallbackResult: ...

    @abstractmethod
    async def check_payment_status(self, transaction_id: str) -> PaymentStatus: ...

    @abstractmethod
    def get_gateway_name(self) -> str: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

---

## RESPONSE MODELS

```python
class PaymentInitResponse(BaseModel):
    success: bool
    payment_url: str | None         # Redirect URL for customer
    transaction_id: str
    gateway_reference: str          # Gateway's own transaction ID
    expires_at: datetime
    raw_response: dict

class PaymentCallbackResult(BaseModel):
    success: bool
    transaction_id: str             # Our internal ID
    gateway_transaction_id: str     # Gateway's ID
    amount_paisas: int
    signature_valid: bool
    raw_payload: dict
```

---

## IDEMPOTENCY — MANDATORY

Every payment callback must be idempotent:

```python
async def handle_payment_callback(gateway_name: str, payload: dict) -> None:
    gateway_txn_id = payload.get("TxnRefNo") or payload.get("transaction_id")
    
    # Check for duplicate
    existing = await payment_repo.get_by_gateway_txn_id(gateway_txn_id)
    if existing and existing.status == PaymentStatus.COMPLETED:
        logger.info("payment.duplicate_callback_ignored", gateway_txn_id=gateway_txn_id)
        return  # Already processed — skip
    
    # Process payment...
```

---

## WEBHOOK SECURITY

Each gateway uses different signature method:
- **JazzCash**: HMAC-SHA256 of sorted params + salt
- **EasyPaisa**: SHA256 of specific field concatenation  
- **SafePay**: HMAC-SHA256 with webhook secret in header
- **NayaPay**: RSA signature verification with public key

ALL callbacks: verify signature FIRST, before any business logic.
Invalid signature → log warning, return 200 (no processing).

---

## PAYMENT RECORD LIFECYCLE

States: `initiated` → `pending` → `completed` | `failed` | `expired` | `refunded`

Every state transition logged to `payment_gateway_log` table with:
- Full raw request and response payloads
- Calculated signature (for debugging)
- Timestamp, latency_ms

---

## OWNER NOTIFICATION

On successful payment: WhatsApp message to distributor owner within 30 seconds.
On failed payment after all retries: WhatsApp alert with order details.
