# LifeLog Agent (Python)

A lightweight cross-platform agent that installs and supervises client collectors, queues data offline, and ingests to a LifeLog server.

Features
- Device-auth with X-Device-Key
- Polls `/api/v1/device/extensions?platform=...` for installed collectors
- Downloads signed packages from `/api/v1/device/extensions/{slug}/{version}/package` and verifies SHA-256 header
- Runs collectors in subprocesses (stdio protocol), restarts with backoff
- Local SQLite queue with capped size and retry/backoff to `/ingest`
- Simple config: stored locally and synced via `/api/v1/device/config`

Assumptions (MVP)
- Collector `slug` corresponds to the server-side SOURCE actor slug to emit to.
- Extensions include any needed client files in their package; entrypoint is relative to the package root.
- Platform identifiers: `macos`, `windows`, `linux`.

Install (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r clients/agent/requirements.txt
python -m lifelog_agent --help
```

Quickstart

```bash
# Initialize with server URL and device key (writes ~/.lifelog/agent/config.json)
python -m lifelog_agent init --server http://localhost:8000 --device-key YOUR_KEY --platform macos

# Optionally set per-collector config
python -m lifelog_agent config set example-extension test-collector api_key ABC123

# Run the agent (foreground)
python -m lifelog_agent run
```

Configuration
- Local config: `~/.lifelog/agent/config.json`
- Server device config: `/api/v1/device/config` (merged shallowly)
- Recommended structure:
```json
{
  "agent": { "poll_interval_sec": 300 },
  "collectors": {
    "example-extension": {
      "test-collector": { "api_key": "..." }
    }
  }
}
```

Stdio Protocol for collectors
- Output newline-delimited JSON records. Types:
  - `{ "type": "raw_log", "data": { ... } }` → sent to `/ingest` with `source_actor_slug = <collector_slug>`
  - `{ "type": "status", "message": "..." }` → logged
- Environment variables provided:
  - `LIFELOG_SERVER_URL`, `LIFELOG_DEVICE_ID` (if known), `LIFELOG_SOURCE_ACTOR_SLUG`, `LIFELOG_COLLECTOR_CONFIG_JSON`

Notes
- This is an MVP. Sandbox and permission policies are minimal. Run collectors you trust.
- For production services (LaunchAgents/systemd), wrap `python -m lifelog_agent run` accordingly.
