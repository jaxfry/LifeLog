# LifeLog Development Cheat Sheet

Quick reference for common development tasks and key information.

---

## 🔥 Critical Security Issues

```
✅ API AUTHENTICATION - COMPLETED
❌ NO RATE LIMITING - ADD BEFORE PRODUCTION
✅ HEALTH CHECKS - COMPLETED
```

**Remaining Critical:**
1. Rate limiting (4 hours) - Still needs implementation

---

## 📊 System Stats

| Metric | Value |
|--------|-------|
| Lines of Code | ~4,200 |
| Python Files | 61 |
| Test Coverage | ~30% (target: 80%) |
| Extensions | 1 (ActivityWatch) |
| Time to v1.0 | 12-14 weeks |

---

## 🏗️ Architecture at a Glance

```
┌─────────────────┐
│  Client (Tray)  │ Collects data from extensions
└────────┬────────┘
         │ HTTP POST /api/v1/ingest
         ↓
┌─────────────────┐
│  FastAPI Server │ Validates, stores, processes
├─────────────────┤
│  PostgreSQL DB  │ 4 domains: Data/Config/Audit/Infra
├─────────────────┤
│  Redis + ARQ    │ Async task queue
├─────────────────┤
│  LiteLLM        │ AI timeline generation
└─────────────────┘
```

---

## 🗄️ Database Schema (Quick)

**Raw Logs (L1)** → Immutable inbox
- `payload_hash` for deduplication
- Links to device + extension

**Events (L2)** → Normalized stream
- `source_log_id` for lineage
- `is_superseded` for versioning

**Sessions (L3-A)** → Time chunks
- Groups events
- `needs_rebuild` flag

**Timeline (L3-B)** → AI narrative
- Linked to session
- Linked to prompt version

---

## 🚀 Quick Start Commands

### Server
```bash
cd server
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Client
```bash
cd lifelog_client
pip install -r requirements.txt
python install.py    # First time setup
python main.py       # Run client
```

### Tests
```bash
cd server
pytest tests/
```

---

## 🔑 API Endpoints (Current)

### Ingestion
- `POST /api/v1/ingest` - Ingest logs ⚠️ NO AUTH

### Data
- `GET /api/v1/timeline` - Get timeline entries
- `GET /api/v1/sessions` - Get sessions
- `GET /api/v1/logs` - Get raw logs
- `GET /api/v1/events` - Get events

### Admin
- `POST /api/v1/devices` - Register device
- `GET /api/v1/devices` - List devices
- `POST /api/v1/admin/test/sessionizer` - Test sessionizer
- `POST /api/v1/admin/generate-summary/{date}` - Generate summary

### Client
- `GET /api/v1/client/extensions` - List extensions
- `GET /api/v1/client/download/{ext_id}` - Download extension

---

## 📝 File Structure Quick Reference

```
LifeLog/
├── server/
│   ├── app/
│   │   ├── api/          # API routes
│   │   ├── core/         # Business logic
│   │   ├── models/       # DB models (data, config, audit)
│   │   ├── loader/       # Extension loading
│   │   └── workers/      # ARQ workers
│   ├── extensions/       # Server extensions
│   ├── tests/            # Test suite
│   └── alembic/          # DB migrations
│
├── lifelog_client/
│   ├── core/             # Client logic
│   └── extensions/       # Client extensions
│
└── docs/                 # Documentation
    ├── INDEX.md          # Start here!
    ├── DEVELOPMENT_ROADMAP.md
    ├── QUICK_START_IMPROVEMENTS.md
    └── guides/
```

---

## 🎯 Priority Matrix

| Task | Priority | Time | Impact | Status |
|------|----------|------|--------|--------|
| Authentication | 🔴 CRITICAL | 8h | Blocks production | ✅ Done |
| Health checks | 🔴 CRITICAL | 3h | Monitoring | ✅ Done |
| Rate limiting | 🔴 CRITICAL | 4h | Security | ❌ Todo |
| Web dashboard | 🟡 HIGH | 60h | Makes usable | ❌ Todo |
| More extensions | 🟡 HIGH | 8h each | Adds value | ❌ Todo |
| Test coverage | 🟡 HIGH | 40h | Quality | ❌ Todo |
| AI enhancements | 🟢 MEDIUM | 30h | Differentiation | ❌ Todo |
| Data export | 🟢 MEDIUM | 12h | User control | ❌ Todo |
| Mobile app | 🔵 LOW | 80h+ | Nice to have | ❌ Todo |

---

## 🐛 Known TODOs in Code

1. `server/app/core/daily_summary.py:27` - Timezone handling
   - Currently defaults to UTC
   - Should respect user's primary timezone
   - Note: Timezone-aware datetime usage has been fixed (deprecated utcnow() replaced)

---

## 🔧 Development Tools to Add

```bash
# Code quality
pip install ruff black mypy

# Pre-commit hooks
pip install pre-commit
pre-commit install

# Load testing
pip install locust

# Coverage
pip install pytest-cov
pytest --cov=app --cov-report=html
```

---

## 📦 Extension Development (Quick)

### Minimum Files
```
extensions/com.example.myext/
├── manifest.json    # Required
├── processor.py     # Required (server-side)
└── collector.py     # Optional (client-side)
```

### manifest.json
```json
{
  "id": "com.example.myext",
  "version": "1.0.0",
  "client": {
    "type": "python",
    "file": "collector.py"
  }
}
```

### processor.py
```python
def normalize(payload):
    """
    Transform raw data to events.
    Returns: List[Dict[str, Any]]
    """
    return [{
        "type": "event_type",
        "data": {...}
    }]
```

---

## 🧪 Testing Quick Ref

### Run specific test
```bash
pytest tests/test_api_endpoints.py::test_ingest -v
```

### Run with coverage
```bash
pytest --cov=app --cov-report=term-missing
```

### Create test data
```bash
python server/scripts/seed_data.py
```

---

## 🔐 Security Checklist

- [x] Implement API key authentication - COMPLETED
- [ ] Add rate limiting (100 req/min recommended)
- [ ] Enable HTTPS in production
- [ ] Add audit logging
- [x] Implement CORS properly - COMPLETED
- [ ] Add security headers (HSTS, CSP)
- [ ] Regular dependency updates
- [ ] Scan for vulnerabilities

---

## 🎨 Web UI Tech Stack (Recommended)

```
Frontend: React + Vite
Styling: TailwindCSS
Charts: Recharts
State: TanStack Query
Routing: React Router
```

---

## 📈 Success Metrics

### Technical
- Test coverage: 80%+
- API response: <100ms (p95)
- Uptime: 99.9%
- Zero critical vulnerabilities

### Product
- Extensions: 5+ at launch
- Setup time: <5 minutes
- Data sources: 3+ per user
- DAU growth: 10% WoW

---

## 💡 Quick Wins (Do Today)

1. ✅ Fix `architechture.md` → `architecture.md` (5 min) - COMPLETED
2. ✅ Fix deprecated datetime usage (30 min) - COMPLETED
3. Add `.editorconfig` (10 min)
4. Create issue templates (20 min)
5. Improve error messages (1 hour)
6. Add request ID tracking (1 hour)

---

## 🆘 Troubleshooting

### Server won't start
```bash
# Check database
psql $DATABASE_URL

# Check Redis
redis-cli ping

# Check logs
tail -f logs/app.log
```

### Client won't sync
```bash
# Check client log
tail -f lifelog_client.log

# Test server connection
curl http://localhost:8000/health

# Verify API key
curl -H "X-API-Key: your-key" http://localhost:8000/api/v1/timeline
```

### Extensions not loading
```bash
# Check extensions directory
ls -la server/extensions/

# Check manifest
cat server/extensions/com.lifelog.aw/manifest.json

# Check processor
python -c "from server.app.loader.runner import run_normalization; print(run_normalization('com.lifelog.aw', {}))"
```

---

## 📚 External Resources

- FastAPI: https://fastapi.tiangolo.com/
- SQLModel: https://sqlmodel.tiangolo.com/
- LiteLLM: https://docs.litellm.ai/
- ARQ: https://arq-docs.helpmanual.io/
- ActivityWatch: https://activitywatch.net/

---

## 🎯 30-Second Elevator Pitch

**LifeLog** is a privacy-first personal data aggregation platform that:
1. Collects data from multiple sources (ActivityWatch, calendar, music, etc.)
2. Processes it into a timeline
3. Uses AI to generate insights and summaries
4. Self-hosted for complete privacy
5. Extensible via Python extensions

**Unique:** Self-hosted + AI + extensible + privacy-focused

---

**Last Updated:** November 2024  
**For more details:** See [INDEX.md](INDEX.md)
