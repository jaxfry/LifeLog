# LifeLog

LifeLog is a self-hosted, Python-native platform for personal data aggregation, timeline generation, and AI-driven insights.

## Architecture

- **Server**: FastAPI-based backend for data ingestion, processing, and AI timeline generation
- **Web Dashboard**: Modern React-based UI for viewing timeline, analytics, and managing settings
- **Client**: Python client for collecting data from local sources
- **Extensions**: Modular collectors for different data sources (ActivityWatch, GPS, etc.)

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

## Features

### 🌐 Web Dashboard
- **Timeline View**: Browse your AI-generated activity timeline with search and filtering
- **Daily Summaries**: Review daily activities with productivity scores and mood tracking
- **Analytics Dashboard**: Visualize activity patterns with interactive charts
- **Settings Management**: Device management, system configuration, and health monitoring
- **Secure Authentication**: JWT token-based authentication with OAuth2

### 🔒 Security & Authentication
- OAuth2 password flow with JWT tokens
- API key authentication for device clients
- Role-based access control (superuser/regular users)
- Secure password hashing with bcrypt

### 📊 Data Processing
- Automatic data ingestion from multiple sources
- Event deduplication and versioning
- Session grouping with configurable time gaps
- AI-powered timeline generation using LiteLLM
- Daily summary generation with productivity tracking

### 🔌 Extensible Architecture
- Modular extension system for data collectors
- Built-in ActivityWatch integration
- Easy to add new data sources
- Server-side and client-side extension support

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
├── web/                # Web dashboard (React + Vite)
│   ├── src/           # Dashboard source code
│   └── dist/          # Production build
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

### Web Dashboard

1. Install dependencies:
   ```bash
   cd web
   npm install
   ```
2. Configure the dashboard:
   ```bash
   cp .env.example .env
   # Edit .env and set VITE_API_URL to your server URL
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Open your browser to http://localhost:5173

For production deployment:
```bash
npm run build
# Serve the files from the dist/ directory
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
