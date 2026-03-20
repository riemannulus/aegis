<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# tests

## Purpose
pytest test suite covering all Aegis modules. Includes unit tests, integration tests, E2E pipeline tests, and mainnet readiness verification. Uses pytest-asyncio for async tests and pytest-playwright for backoffice E2E.

## Key Files

| File | Description |
|------|-------------|
| `test_data_collector.py` | Data collector unit tests |
| `test_feature_engineer.py` | Feature engineering tests (needs 50+ candle rows) |
| `test_models.py` | ML model train/predict/save/load tests |
| `test_paper_trader.py` | Paper trading simulator tests |
| `test_binance_executor.py` | Binance executor tests (mock + optional testnet integration) |
| `test_risk_engine.py` | 2-stage risk engine tests |
| `test_signal_converter.py` | Signal conversion pipeline tests |
| `test_decision_logger.py` | Decision logging tests |
| `test_analytics.py` | PnL and performance metric tests |
| `test_e2e_pipeline.py` | End-to-end trading cycle test with mocked components |
| `test_mainnet_readiness.py` | Architecture verification for mainnet safety (mock only) |
| `test_api_endpoints.py` | FastAPI endpoint tests using TestClient |
| `test_backoffice_e2e.py` | Playwright-based backoffice E2E tests |

## For AI Agents

### Working In This Directory
- Run all tests: `pytest tests/`
- Run specific test: `pytest tests/test_risk_engine.py -v`
- `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio` decorator
- Testnet integration tests: `pytest tests/test_binance_executor.py -v -m testnet` (requires API keys)
- E2E tests require running API + backoffice services
- Never hit real exchange APIs in CI — always mock

### Testing Requirements
- All tests must pass before merging
- New modules should have corresponding test files
- Mock external services (exchange, Telegram)

### Common Patterns
- Mock `settings` and exchange objects for isolation
- Use in-memory SQLite for storage-dependent tests
- `from unittest.mock import patch, MagicMock` for mocking

## Dependencies

### External
- `pytest` — Test framework
- `pytest-asyncio` — Async test support
- `pytest-playwright` — Browser-based E2E tests

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
