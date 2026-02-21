---
applyTo: "tests/**,**/*test*.py,**/conftest.py"
---

# SKILL 21 — TESTING
## Source: `docs/skills/SKILL_testing.md`

---

## MANDATE

80%+ coverage on all core business logic modules.
Tests written alongside the code they test — not after.
Untested code is broken code you haven't found yet.

---

## FRAMEWORK

- **pytest** — test runner
- **pytest-asyncio** — async test support
- **pytest-cov** — coverage reporting
- **pytest-mock** / `unittest.mock` — mocking externals

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

Tests mirror app structure exactly:
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── unit/                    # No external I/O — all mocked
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
└── integration/             # May hit test DB — no real APIs
    ├── test_webhook_flow.py
    ├── test_order_flow.py
    ├── test_onboarding_flow.py
    ├── test_distributor_mgmt.py
    └── test_payment_flow.py
```

---

## conftest.py — REQUIRED FIXTURES

```python
@pytest.fixture
def mock_settings():
    """Return Settings with test values. No real API keys."""
    return Settings(
        GEMINI_API_KEY="test-key",
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_SERVICE_KEY="test-service-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        META_APP_SECRET="test-secret",
        META_VERIFY_TOKEN="test-verify",
        APP_ENV="test",
    )

@pytest.fixture
def mock_db_client(mocker):
    """Mock Supabase client — prevents real DB calls."""
    return mocker.AsyncMock()

@pytest.fixture
def mock_whatsapp_client(mocker):
    """Mock WhatsApp client — no real API calls."""
    return mocker.AsyncMock()

@pytest.fixture
def mock_ai_provider(mocker):
    """Mock AI provider — deterministic responses."""
    provider = mocker.AsyncMock()
    provider.generate_text.return_value = AITextResponse(
        content='{"intent": "add_item", "items": [...]}',
        tokens_used_input=100, tokens_used_output=50,
        finish_reason="stop", raw_response={}, estimated_cost_paisas=1,
    )
    return provider

@pytest.fixture
def sample_order_context():
    """Return a realistic OrderContext with 2 items."""
    return create_empty_context()  # Populated with test data
```

---

## UNIT TEST EXAMPLES

### NLU Test Pattern
```python
@pytest.mark.asyncio
async def test_nlu_extracts_intent_add_item(mock_ai_provider, mock_settings):
    """Test intent extraction for a typical add-item message."""
    nlu = NLUService(ai_provider=mock_ai_provider)
    result = await nlu.classify("1 paracetamol 10 strips chahiye")
    assert result.intent == "add_item"
    assert len(result.items) == 1
    assert result.items[0].name == "paracetamol"
    assert result.items[0].quantity == 10
```

### Repository Test Pattern
```python
@pytest.mark.asyncio
async def test_get_customer_by_number_returns_none_when_not_found(mock_db_client):
    """Test repo returns None when customer doesn't exist."""
    mock_db_client.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.eq.return_value.single.return_value.execute \
        .return_value = MagicMock(data=None)

    repo = CustomerRepository()
    result = await repo.get_by_number(distributor_id="dist-1", whatsapp_number="+923001234567")
    assert result is None
```

---

## RULES

1. **Never test AI provider behavior** — mock it, test your logic around it
2. **Never test the DB** in unit tests — mock DB client
3. **Integration tests** may use a test Supabase project — never production
4. **Test edge cases** especially: empty input, malformed input, injection attempts
5. **Each test function** must be self-contained — no shared mutable state
6. **Test names** must describe the scenario: `test_<function>_<condition>_<expected>`
7. **Commit tests separately** from the feature they test
