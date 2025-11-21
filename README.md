# LifeLog System

A self-hosted, Python-native platform for personal data aggregation, timeline generation, and AI-driven insights.

## Philosophy

**"Rebuild the Present from the Past."** LifeLog prioritizes infinite reprocessing capabilities, allowing you to reanalyze your historical data as your understanding and tools evolve.

## Architecture

- **Central Server**: Python-based FastAPI server for data ingestion and processing
- **Distributed Clients**: Lightweight clients that collect data from various sources
- **Extension Model**: "Managed Trust" - Extensions are Python packages executed by the Core, capable of full data analysis and network I/O

## Tech Stack

- **Language**: Python 3.11+
- **API**: FastAPI (Async)
- **ORM**: SQLModel (Pydantic + SQLAlchemy)
- **Database**: PostgreSQL 16+ (JSONB for Logs, pgvector for Embeddings)
- **Task Queue**: Redis + ARQ
- **Scheduler**: APScheduler (Cron management)
- **AI Client**: LiteLLM

## Project Structure

```
LifeLog/
├── server/              # Central server application
│   ├── app/            # FastAPI application
│   │   ├── api/        # API endpoints
│   │   ├── core/       # Core business logic
│   │   ├── models/     # Database models
│   │   ├── loader/     # Extension loader
│   │   └── workers/    # Background workers
│   ├── extensions/     # Installed extensions
│   ├── scripts/        # Utility scripts
│   └── tests/          # Test suite
├── lifelog_client/     # Client application
│   ├── core/          # Client core logic
│   └── extensions/    # Client-side extensions
└── docs/              # Documentation
```

## Quick Start

### Server Setup

1. **Prerequisites**
   - Python 3.11+
   - PostgreSQL 16+
   - Redis

2. **Install Dependencies**
   ```bash
   cd server
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Run Database Migrations**
   ```bash
   alembic upgrade head
   ```

5. **Start the Server**
   ```bash
   uvicorn app.main:app --reload
   ```

### Client Setup

1. **Install Dependencies**
   ```bash
   cd lifelog_client
   pip install -r requirements.txt
   ```

2. **Configure Client**
   ```bash
   python install.py
   ```

3. **Run Client**
   ```bash
   python main.py
   ```

## Key Features

### 4-Domain Database Schema

1. **Data Pipeline (Lineage & Versioning)**
   - Raw Logs → Events → Sessions → Timeline
   - Full reprocessing capability

2. **Administration & Config**
   - Device management
   - Extension registry
   - Versioned prompts

3. **Accounting**
   - AI usage tracking
   - Cost monitoring

4. **Infrastructure**
   - Binary storage
   - Dead letter queue

### Smart Ingestion

- Automatic deduplication using payload hashing
- Client-side hash calculation
- Efficient bandwidth usage

### Extension Ecosystem

Extensions are Python packages with:
- `manifest.json`: Permissions and dependencies
- `processor.py`: Data normalization
- `collector.py` (optional): Data collection

### AI & Prompt Management

- Prompts stored as data, not code
- Version tracking for reproducibility
- Cost tracking per AI call

## Security

⚠️ **Important**: Never commit sensitive data to version control!

- Use `.env` files for secrets (see `.env.example`)
- API keys are hashed before storage
- Extensions run in controlled environment

## Development

### Running Tests

```bash
cd server
pytest tests/
```

### Code Style

- Follow PEP 8
- Use type hints
- Add docstrings to public APIs

## Documentation

See the `docs/` directory for detailed documentation:
- `architechture.md`: System architecture details
- `sessionizer_plan.md`: Session grouping logic

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

[Add your license here]

## Support

[Add support information here]
