# SKILL: Testing Protocol
# TELETRAAN Project — Abdullah-Khan-Niazi
# Read this before writing any test.

---

## IDENTITY

This skill defines the complete testing strategy for TELETRAAN. Tests are not an
afterthought. They are written alongside the code they test. The goal is 80%+
coverage on all core business logic modules, with integration tests covering
every external-facing flow.

Untested code is broken code you haven't found yet.

---

## FRAMEWORK AND TOOLS

- **pytest** — test runner
- **pytest-asyncio** — async test support (`asyncio_mode = "auto"` in pyproject.toml)
- **pytest-cov** — coverage reporting
- **pytest-mock** / `unittest.mock` — mocking external dependencies

### pyproject.toml test config
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]

[tool.coverage.run]
source = ["app"]
omit = ["app/main.py", "tests/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

---

## DIRECTORY STRUCTURE

Tests mirror the app directory structure exactly:
```
tests/
├── __init__.py
├── conftest.py           ← Shared fixtures for all tests
├── unit/                 ← No external I/O — all dependencies mocked
│   ├── test_nlu.py
│   ├── test_billing.py
│   ├── test_fuzzy_matcher.py
│   ├── test_state_machine_a.py
│   ├── test_state_machine_b.py
│   ├── test_subscription_manager.py
│   ├── test_payment_gateways.py
│   ├── test_voice_pipeline.py
│   ├── test_message_parser.py
│   ├── test_order_context_store.py
│   ├── test_ai_providers.py
│   └── test_security.py
└── integration/          ← May hit test DB, no real APIs
    ├── test_webhook_flow.py
    ├── test_order_flow.py
    ├── test_onboarding_flow.py
    ├── test_distributor_mgmt.py
    └── test_payment_flow.py
```

---

## conftest.py — REQUIRED FIXTURES

The `conftest.py` must provide these fixtures at minimum:

```
Fixtures:
  mock_settings        — Returns Settings with test values, no real API keys
  mock_db_client       — AsyncMock Supabase client
  mock_ai_provider     — AsyncMock AIProvider returning controlled outputs
  mock_whatsapp_client — AsyncMock WhatsApp client
  mock_payment_gateway — AsyncMock PaymentGateway
  sample_distributor   — A valid Distributor Pydantic model instance
  sample_customer      — A valid Customer Pydantic model instance
  sample_order_context — A valid OrderContext with 2 items
  sample_session       — A valid Session Pydantic model instance
```

---

## UNIT TEST RULES

### What to mock
In unit tests — mock EVERYTHING external:
- Database calls → `AsyncMock` returning typed Pydantic models
- AI provider calls → `AsyncMock` returning controlled `TextCompletionResult`
- WhatsApp client → `AsyncMock` — verify send calls with `assert_called_once_with`
- Payment gateway → `AsyncMock` returning controlled `PaymentLinkResult`
- `datetime.now()` → freeze with `pytest-freezegun` where time matters

### What NOT to mock
- Pure business logic (billing calculations, fuzzy matching, state transitions)
- Pydantic model validation
- Custom exception classes

### Naming convention
```
test_[function_name]_[scenario]_[expected_outcome]

Examples:
  test_calculate_bill_with_bonus_rule_applies_correctly
  test_fuzzy_matcher_typo_paracetamol_matches_threshold
  test_state_machine_cancel_from_any_state_returns_main_menu
  test_payment_dummy_failure_on_amount_ending_999
```

---

## UNIT TEST TARGETS — MINIMUM REQUIRED

### test_billing.py
- Subtotal calculation for multiple items
- Bonus rule (5+1): correct bonus_units_given, correct line total
- Percentage discount: rounded correctly in paisas
- Flat discount applied correctly
- Multiple rules: only highest priority applied when non-stackable
- Stackable rules: all applied in order
- Delivery charge: applied when below free delivery threshold
- Free delivery: when order exceeds threshold
- Credit limit: order blocked when outstanding + total > credit_limit
- Zero quantity item: raises ValidationError

### test_fuzzy_matcher.py
- Exact match: score 100, auto-selected
- Common Urdu typo: "paracitamol" matches "Paracetamol 500mg" above threshold
- Roman Urdu variant: "augmentin" matches "Augmentin 625mg Tablet"
- Below threshold: no match returned
- Multiple matches: returned sorted by score descending, max 10
- Empty catalog: returns empty list, no error

### test_state_machine_a.py
- Every valid state transition executes without error
- Invalid transition raises StateTransitionError
- "cancel" from any non-idle state → returns to main_menu
- "menu" keyword from order_building → returns to main_menu with draft preserved
- Retry counter: increments on failed state, resets on success
- After 3 retries: handoff_requested set in context_flags

### test_order_context_store.py
- create_context: initializes all required fields with correct defaults
- save_context: increments context_version_counter
- load_context: returns None when no pending_order_context in session
- load_context: returns correct OrderContext when present
- save_context: optimistic concurrency — raises OrderContextError on version mismatch
- recompute_billing: correct BillingSummary after adding item
- recompute_billing: correct BillingSummary after discount applied
- finalize_context: sets order_confirmed_at, transitions state to 'confirmed'
- clear_context: sets pending_order_context to null in session

### test_security.py
- HMAC verification: valid signature passes
- HMAC verification: tampered payload fails
- HMAC verification: wrong key fails
- HMAC verification: timing-safe comparison used (no timing attack vulnerability)
- Fernet encrypt/decrypt: roundtrip produces original string
- Fernet: different keys produce different ciphertext
- Rate limiter: under threshold returns False (not throttled)
- Rate limiter: at threshold returns True (throttled)
- Rate limiter: new window resets counter

### test_payment_gateways.py
- Dummy gateway: generate_payment_link returns valid PaymentLinkResult
- Dummy gateway: verify_webhook_signature always returns True
- Dummy gateway: parse_webhook_payload returns success event
- Dummy gateway: amount ending in 999 paisas → parse_webhook_payload returns failed event
- Dummy gateway: NOT activatable when APP_ENV=production (raises ConfigurationError)
- All six gateways: implement all abstract methods (structural check)
- Factory: returns correct class for each ACTIVE_PAYMENT_GATEWAY value
- Factory: raises ConfigurationError for unknown gateway name

### test_ai_providers.py
- All three providers implement all abstract methods (structural check)
- Factory: returns correct provider for each ACTIVE_AI_PROVIDER value
- Provider switch: factory returns different provider on different env value
- Mock Gemini response: TextCompletionResult parsed correctly
- Mock OpenAI response: TextCompletionResult parsed correctly
- Failed API call: returns TextCompletionResult with success=False
- cost_paisas: returns integer, never negative

---

## INTEGRATION TEST RULES

Integration tests may use a real test Supabase project (separate from production).
Configure via `TEST_SUPABASE_URL` and `TEST_SUPABASE_SERVICE_KEY` env vars.
Never use real AI API keys in CI — mock AI provider in integration tests too.
Never use real payment gateway APIs in integration tests — use dummy gateway.

### test_webhook_flow.py
- GET verify: correct challenge token returned
- GET verify: wrong token returns 403
- POST receive: invalid HMAC signature returns 403
- POST receive: valid text message parsed and routed
- POST receive: duplicate message ID returns 200 immediately (deduplicated)
- POST receive: suspended distributor → suspension notice sent, no processing

### test_order_flow.py
- First message from new number → onboarding state entered
- Order building → item added → context persisted in DB
- Fuzzy match shown → customer selects → item confirmed → context updated
- Order confirmation → DB order written → order_items written
- Order confirmation → WhatsApp group message sent
- Quick reorder → context pre-populated from source order

### test_payment_flow.py
- Dummy payment link generated → stored in payments table
- Dummy callback received → payment marked complete
- Subscription extended after successful payment
- Confirmation message sent to distributor after payment
- Duplicate callback → idempotency key blocks double-processing

---

## COVERAGE REQUIREMENTS

Run with:
```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Modules requiring 90%+ coverage (critical paths):
- `app/orders/context_store.py`
- `app/orders/billing_service.py`
- `app/inventory/fuzzy_matcher.py`
- `app/core/security.py`
- `app/payments/base.py`
- `app/payments/gateways/dummy.py`
- `app/ai/base.py`

---

## CI EXPECTATIONS

Every push to main branch must pass:
1. `black --check .`
2. `isort --check-only .`
3. `flake8 .`
4. `pytest --cov=app --cov-fail-under=80`

Never push code that fails any of these checks.
