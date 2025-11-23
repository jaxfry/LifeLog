# Development Scripts

This directory previously contained ad hoc test scripts that have been removed in favor of the professional test suite.

## Testing

For all testing needs, use the comprehensive test suite located in `server/tests/`:

```bash
cd server
pytest tests/
```

The test suite includes:
- Health check tests
- API endpoint tests
- Device management tests
- Data pipeline tests
- Configuration tests
- Daily summary tests

## Running Tests

```bash
# Run all tests
cd server
pytest

# Run specific test file
pytest tests/test_health_endpoints.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app tests/
```
