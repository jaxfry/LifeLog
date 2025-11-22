# LifeLog Test Suite

This directory contains the comprehensive test suite for the LifeLog server.

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
pytest -m integration
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
