# LifeLog Server

The central server component of the LifeLog system, built with FastAPI and PostgreSQL.

## Features

- **RESTful API** for data ingestion and retrieval
- **Async processing** with ARQ task queue
- **AI-powered timeline generation** using LiteLLM
- **Extension system** for flexible data processing
- **Automatic data deduplication** via payload hashing

## Project Structure

```
server/
├── app/
│   ├── api/              # API endpoints
│   │   ├── admin.py      # Device management
│   │   ├── client.py     # Client/extension endpoints
│   │   ├── data.py       # Data retrieval
│   │   ├── deps.py       # Dependencies
│   │   └── ingest.py     # Data ingestion
│   ├── core/             # Core business logic
│   │   ├── db.py         # Database connection
│   │   ├── ingestion.py  # Deduplication logic
│   │   ├── processing.py # Event processing
│   │   ├── prompts.py    # LLM prompt management
│   │   ├── scheduler.py  # Task scheduling
│   │   ├── sessionizer.py # Event grouping
│   │   └── timeline_processor.py # AI timeline generation
│   ├── loader/           # Extension loader
│   ├── models/           # Database models
│   │   ├── audit.py      # Audit models
│   │   ├── config.py     # Configuration models
│   │   └── data.py       # Data models
│   └── workers/          # Background workers
├── alembic/              # Database migrations
├── extensions/           # Installed extensions
├── scripts/              # Utility scripts
└── tests/                # Test suite
```

## API Endpoints

### Ingestion
- `POST /api/v1/ingest` - Ingest log data with automatic deduplication

### Data Retrieval
- `GET /api/v1/timeline` - Retrieve processed timeline entries
- `GET /api/v1/sessions` - Retrieve grouped event sessions
- `GET /api/v1/events` - Retrieve normalized events
- `GET /api/v1/logs` - Retrieve raw logs

### Device Management
- `POST /api/v1/devices` - Register a new device
- `GET /api/v1/devices` - List all devices
- `GET /api/v1/devices/{id}` - Get device details
- `PATCH /api/v1/devices/{id}` - Update device
- `DELETE /api/v1/devices/{id}` - Delete device
- `POST /api/v1/devices/{id}/rotate-key` - Rotate API key

### Client/Extensions
- `GET /api/v1/client/extensions` - List available extensions
- `GET /api/v1/client/download/{id}` - Download extension package

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 5.0+

### Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. Run migrations:
   ```bash
   alembic upgrade head
   ```

4. Start the server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Docker Setup

```bash
docker-compose up -d
```

## Configuration

Key environment variables (see `.env.example`):

- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `GEMINI_API_KEY` - Google Gemini API key for AI features

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Database Migrations

Create a new migration:
```bash
alembic revision --autogenerate -m "Description"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback:
```bash
alembic downgrade -1
```

### Utility Scripts

- `scripts/reset_db.py` - Reset database
- `scripts/seed_data.py` - Seed test data
- `scripts/test_endpoints.py` - Test API endpoints
- `scripts/generate_timeline.py` - Generate timeline manually
- `scripts/verify_timeline.py` - Verify timeline integrity

## Extensions

Extensions are Python packages that normalize raw data into events. Each extension should have:

- `manifest.json` - Metadata and configuration
- `processor.py` - Normalization function
- `collector.py` (optional) - Data collection script

### Example Extension Structure

```
extensions/com.lifelog.example/
├── manifest.json
├── processor.py
└── collector.py (optional)
```

## Logging

The server uses Python's `logging` module. Configure log level via environment or code.

## Security

- API keys are hashed using SHA256
- Always use `.env` files for secrets
- Never commit credentials to version control
- Extensions run in controlled environment

## Performance

- Async operations throughout
- Database connection pooling
- Task queue for heavy processing
- Payload hash-based deduplication reduces redundant processing

## Troubleshooting

### Database Connection Issues
- Verify PostgreSQL is running
- Check `DATABASE_URL` in `.env`
- Ensure database exists

### Redis Connection Issues
- Verify Redis is running
- Check `REDIS_URL` in `.env`

### AI Processing Not Working
- Verify `GEMINI_API_KEY` is set
- Check API quota limits
- Review logs for error messages

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
