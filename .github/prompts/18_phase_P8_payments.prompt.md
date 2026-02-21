# Phase 8 — Payment Gateways (All Five + Dummy)

**Prerequisites:** Phase 7 complete and verified.
**Verify before P9:** Dummy gateway full lifecycle + failure simulation tested; all 5 gateway unit tests passing.

## Steps (execute in order, commit after each)

1. Implement `app/payments/base.py` — abstract `PaymentGateway` base class with full interface  
   See `09_payment_gateway_abstraction.prompt.md` for all methods and response types  
   → Commit: `"payments: define abstract PaymentGateway base class with full interface"`

2. Implement `app/payments/gateways/dummy_gateway.py` — full lifecycle simulation  
   (auto-confirm after delay, 99-paisa = auto-fail, 15-min expiry, BLOCKED in production)  
   → Commit: `"payments: implement dummy gateway with full lifecycle simulation"`

3. Implement `app/payments/gateways/jazzcash.py` — JazzCash merchant API + HMAC-SHA256 verification  
   → Commit: `"payments: implement JazzCash merchant API with HMAC verification"`

4. Implement `app/payments/gateways/easypaisa.py` — EasyPaisa business API + hash verification  
   → Commit: `"payments: implement EasyPaisa business API with hash verification"`

5. Implement `app/payments/gateways/safepay.py` — SafePay hosted checkout URL + HMAC webhook  
   (Visa, Mastercard, UnionPay, mobile wallets; generate_checkout_url + verify_signature)  
   → Commit: `"payments: implement SafePay checkout API with HMAC webhook verification"`

6. Implement `app/payments/gateways/nayapay.py` — NayaPay merchant API + QR code URL + webhook  
   → Commit: `"payments: implement NayaPay merchant API with QR code URL support"`

7. Implement `app/payments/gateways/bank_transfer.py` — bot flow: details → screenshot → owner notify → manual confirm  
   → Commit: `"payments: implement bank transfer flow with screenshot capture and manual confirmation"`

8. Implement `app/payments/factory.py` — env-driven selection, per-distributor override, production guard for dummy  
   → Commit: `"payments: implement gateway factory with env-driven selection and per-distributor override"`

9. Implement `app/payments/webhook_handlers.py` — unified post-payment lifecycle  
   (idempotency check, status update, subscription extension or order payment confirmation, audit log)  
   → Commit: `"payments: implement unified post-payment lifecycle with idempotency guarantees"`

10. Implement `app/api/payments.py` — callback endpoints for all 5 gateways with signature verification  
    (routes: `/api/payments/jazzcash/callback`, `/easypaisa/callback`, `/safepay/callback`,  
    `/nayapay/callback`, `/dummy/callback`)  
    → Commit: `"api: add callback endpoints for all 5 payment gateways with signature verification"`

11. Test dummy gateway full lifecycle — auto-confirm, failure simulation, expiry  
    → Commit: `"tests: verify dummy gateway complete payment lifecycle including failure scenarios"`

12. Write unit tests for all 5 gateways (mock HTTP responses)  
    → Commit: `"tests: add unit tests for all 5 payment gateways with mocked responses"`

13. **PHASE 8 COMPLETE** Commit: `"phase-8: all 5 payment gateways implemented and tested"`
