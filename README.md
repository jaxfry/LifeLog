# LifeLog

> **⚠️ Development Status**: LifeLog is currently **~70% implemented** and **not ready for production use**. It's suitable for development, testing, and experimentation. See [READINESS.md](READINESS.md) for detailed status.

## Overview

LifeLog is an **extension-first, modular platform** for personal data aggregation and AI-driven insights. It features a server-side data pipeline that processes raw logs into a canonical event timeline with AI enrichment.

### What Works Now
- ✅ Server-side data pipeline (raw logs → events → enrichment)
- ✅ Dynamic extension loading and managed schemas
- ✅ AI integration (embeddings, synthesis, LiteLLM support)
- ✅ REST APIs for ingestion and timeline queries
- ✅ JWT and device-key authentication

### What's Missing
- ❌ Client applications (no desktop/mobile apps yet)
- ❌ Web UI for viewing your data
- ❌ Real-time streaming (WebSocket/SSE)
- ❌ Automatic reprocessing on version changes

**[📖 Read Full Readiness Status](READINESS.md)**

## Quickstart: Bootstrap Development Data

After running migrations, you can seed the database with a test device, extension, actors, and event type for development:

```zsh
# Run inside the server container
# (or from host if you have dependencies installed)
docker compose exec server python scripts/bootstrap_lifelog.py
```

This will create:
- Device: name `dev-device`, key `test-device-key`
- Extension: `test-extension` with actors `test-source` and `test-processor`
- Event type: `test-event` owned by `test-extension`

You can now:
- Ingest with header `X-Device-Key: test-device-key`
- Trigger processing for ingested raw logs
- View timeline events

## Architecture & Documentation

- **[Architecture Guide](docs/architechture.md)**: Complete system design and data flow
- **[Dynamic Extensions Guide](docs/dynamic-extensions.md)**: How to build extensions
- **[Extension README](server/extensions/README.md)**: Quick reference for developers
- **[Readiness Status](READINESS.md)**: What works, what doesn't, and the roadmap

## Development Setup

### Using Docker (Recommended)

```bash
# 1. Copy environment files
cp .env.docker.example .env.docker
cp .env.example .env.docker  # Contains database and auth config
# Edit .env.docker with your database and auth settings

# 2. Start the stack
docker compose up -d --build

# 3. Run database migrations
docker compose exec server alembic upgrade head

# 4. Access the API
open http://localhost:8000/docs
```

### Local Development

```bash
# 1. Install dependencies
cd server
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env with your settings

# 3. Run migrations
alembic upgrade head

# 4. Start the server
uvicorn lifelog.main:app --reload
```

## Quick API Test

```bash
# Get an authentication token
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=admin123"

# View the timeline (use token from above)
curl http://localhost:8000/api/v1/timeline \
  -H "Authorization: Bearer YOUR_TOKEN"

# Ingest data (requires device API key)
curl -X POST http://localhost:8000/ingest \
  -H "X-Device-Key: YOUR_DEVICE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_actor_slug": "test-source",
    "data": {"message": "Hello LifeLog!"}
  }'
```

## Creating Extensions

Extensions are the primary way to add functionality to LifeLog. See the [example extension](server/extensions/example-extension/) for a working reference.

```bash
# 1. Create extension directory
mkdir server/extensions/my-extension

# 2. Create manifest.json (see example-extension for structure)

# 3. Create __init__.py with your actor classes

# 4. Restart server (extension auto-loads)
docker compose restart server

# 5. Register in database
curl -X POST http://localhost:8000/internal/extensions/from-manifest \
  -H "Content-Type: application/json" \
  -d @server/extensions/my-extension/manifest.json
```

## Contributing

LifeLog welcomes contributions! Priority areas:

1. **Client Applications**: Build desktop/mobile data collectors
2. **Web Dashboard**: Create a UI for viewing timeline data  
3. **Extensions**: Build useful data processors and enrichers
4. **Documentation**: Improve guides and examples
5. **Testing**: Add test coverage and report bugs

See repository issues for current priorities.

## License

MIT
