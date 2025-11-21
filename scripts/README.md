# Development Test Scripts

This directory contains simple test scripts for manual testing during development.

## Scripts

### test_api.py
Tests basic API functionality including:
- Root endpoint
- Ingest endpoint
- Duplicate detection

Usage:
```bash
python test_api.py
```

### test_async_processing.py
Tests the async processing flow:
- Ingests a log entry
- Verifies it's queued for processing

Usage:
```bash
python test_async_processing.py
```

### test_aw_client.py
Tests ActivityWatch client integration.

Usage:
```bash
python test_aw_client.py
```

### test_processing.py
Tests data processing pipeline.

Usage:
```bash
python test_processing.py
```

## Notes

- These scripts require the LifeLog server to be running on `http://localhost:8000`
- They are intended for manual testing and development
- For automated testing, see `server/tests/`
