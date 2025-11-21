# LifeLog

LifeLog is a self-hosted, Python-native platform for personal data aggregation, timeline generation, and AI-driven insights.

## Architecture

- **Server**: FastAPI-based backend for data ingestion, processing, and AI timeline generation
- **Client**: Python client for collecting data from local sources
- **Extensions**: Modular collectors for different data sources (ActivityWatch, GPS, etc.)

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

**Note**: The architecture document is currently named `architechture.md` (with typo) in the repository.

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

```bash
cd server
pytest tests/
```

### Test Scripts

The `scripts/` directory contains simple test utilities for development:
- `test_api.py`: Test basic API endpoints
- `test_async_processing.py`: Test async processing flow
- `test_aw_client.py`: Test ActivityWatch integration
- `test_processing.py`: Test data processing

### Server Scripts

The `server/scripts/` directory contains utility scripts:
- `seed_data.py`: Seed test data
- `reset_db.py`: Reset database
- `generate_timeline.py`: Manually trigger timeline generation
- `verify_timeline.py`: Verify timeline integrity

## Security

⚠️ **IMPORTANT**: Never commit `.env` files or API keys to version control!

1. Always use `.env.example` as a template
2. Keep your `.env` file local only
3. Rotate API keys if they are accidentally exposed

## License

[Add your license here]
