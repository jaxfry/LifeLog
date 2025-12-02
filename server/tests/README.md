# LifeLog Test Suite

This directory contains the comprehensive test suite for the LifeLog server.

## ⚠️ Database Safety

**Tests are configured to NEVER touch your production database.**

By default, tests run against an **in-memory SQLite database** to ensure complete isolation from production data.

### How It Works

1. **Automatic Protection**: The test suite will refuse to run if it detects `DATABASE_URL` points to a production database (contains "lifelog_db", "prod", or "production") without `TEST_DATABASE_URL` being explicitly set.

2. **Default Behavior**: If no `TEST_DATABASE_URL` is set, tests use `sqlite+aiosqlite:///:memory:` (in-memory SQLite).

3. **Integration Tests**: For tests requiring PostgreSQL features (like pgvector), explicitly set `TEST_DATABASE_URL`:
   ```bash
   TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lifelog_test pytest -m integration
   ```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TEST_DATABASE_URL` | Database URL for tests (default: in-memory SQLite) |
| `DATABASE_URL` | Ignored during tests (overridden by conftest.py) |

## Test Categories

### Unit Tests
Unit tests test individual components in isolation without requiring external services (database, Redis, etc.).

Run unit tests only:
```bash
pytest -m unit
```

### Integration Tests
Integration tests require external services like PostgreSQL and Redis to be running.

Run integration tests only:
```bash
TEST_DATABASE_URL=postgresql+asyncpg://lifelog:lifelogpassword@localhost:5432/lifelog_test pytest -m integration
```

## Running Tests

### All Tests
```bash
pytest
```

### Specific Test File
```bash
pytest tests/test_health_endpoints.py
```

### With Verbose Output
```bash
pytest -v
```

### With Coverage Report
```bash
pytest --cov=app tests/
```

### Running Specific Tests
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests (requires services)
pytest -m integration

# Run tests matching a pattern
pytest -k "health"
```

## Test Files

- `test_health_endpoints.py` - Health check endpoints (basic, liveness, readiness)
- `test_api_endpoints.py` - Core API endpoints (devices, logs, events)
- `test_config_endpoints.py` - Configuration management endpoints
- `test_device_management.py` - Device lifecycle management
- `test_daily_summary.py` - Daily summary generation
- `test_pipeline_integrity.py` - End-to-end data pipeline tests (requires running server)

## Prerequisites

### For Unit Tests
- Python 3.12+
- pytest and dependencies from requirements.txt

### For Integration Tests
In addition to unit test requirements:
- PostgreSQL running on localhost:5432
- Redis running on localhost:6379
- Database initialized with Alembic migrations
- LifeLog server running (for pipeline tests)

## Configuration

Test configuration is in `pytest.ini` in the server root directory.

Shared fixtures are defined in `conftest.py`.

## Best Practices

1. **Unit tests** should be fast and not require external services
2. **Integration tests** should properly clean up after themselves
3. Use the `@pytest.mark.unit` and `@pytest.mark.integration` markers appropriately
4. Use the `async_client` fixture from conftest.py for HTTP testing
5. Tests should be idempotent and independent
