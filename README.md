# LifeLog

LifeLog is a self-hosted, Python-native platform for personal data aggregation, timeline generation, and AI-driven insights.

## Architecture

- **Server**: FastAPI-based backend for data ingestion, processing, and AI timeline generation
- **Client**: Python client for collecting data from local sources
- **Extensions**: Modular collectors for different data sources (ActivityWatch, GPS, etc.)

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

## Documentation

📖 **[Complete Documentation Index](docs/INDEX.md)** - Start here for all documentation

Key documents:
- **[Quick Start Improvements](docs/QUICK_START_IMPROVEMENTS.md)** - Actionable checklist with time estimates
- **[Development Roadmap](docs/DEVELOPMENT_ROADMAP.md)** - Comprehensive analysis and 12-14 week plan
- **[Architecture Guide](docs/architecture.md)** - System design and technical details
- **[Authentication Guide](docs/guides/IMPLEMENTING_AUTHENTICATION.md)** - Critical security implementation

## Project Structure

```
LifeLog/
├── server/              # FastAPI server
│   ├── app/            # Application code
│   ├── extensions/     # Server-side extensions
│   ├── scripts/        # Utility scripts
│   └── tests/          # Test suite
├── lifelog_client/     # Client application
│   ├── core/          # Core client functionality
│   └── extensions/    # Client-side extensions
├── scripts/           # Development test scripts
└── docs/              # Documentation
```

## Setup

### Server

1. Copy `.env.example` to `server/.env` and configure your environment variables
2. Install dependencies:
   ```bash
   cd server
   pip install -r requirements.txt
   ```
3. Initialize the database:
   ```bash
   alembic upgrade head
   ```
4. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```

### Client

1. Install dependencies:
   ```bash
   cd lifelog_client
   pip install -r requirements.txt
   ```
2. Configure the client:
   ```bash
   python main.py config
   ```
3. Run the client:
   ```bash
   python main.py
   ```

## Configuration

Environment variables (in `server/.env`):

- `GEMINI_API_KEY`: Google Gemini API key for AI features
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_FILE`: Optional path to log file

## Development

### Running Tests

The project includes a comprehensive test suite for all functionality:

```bash
cd server
pytest
```

Test coverage includes:
- Health check endpoints
- API endpoints (ingest, data, admin, client)
- Device management
- Data pipeline integrity
- Configuration management
- Daily summary generation

Run specific tests:
```bash
# Run a specific test file
pytest tests/test_health_endpoints.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app tests/
```

### Server Utility Scripts

The `server/scripts/` directory contains utility scripts for data management:
- `seed_data.py`: Seed test data
- `reset_db.py`: Reset database
- `generate_timeline.py`: Manually trigger timeline generation
- `verify_timeline.py`: Verify timeline integrity
- `verify_summary.py`: Verify daily summary integrity

## Security

⚠️ **IMPORTANT**: Never commit `.env` files or API keys to version control!

1. Always use `.env.example` as a template
2. Keep your `.env` file local only
3. Rotate API keys if they are accidentally exposed

## License

[Add your license here]
