# LifeLog

A personal life-logging platform with a modular extension system and local-first processing.

## Quick Start (one-command)

Fastest path (macOS or Linux):

1) Ensure Docker Desktop (or Docker Engine) is installed and running.
2) From the repo root, run the script:

```zsh
chmod +x ./quickstart.sh
./quickstart.sh
```

What it does:
- Starts the server via Docker Compose and waits for health.
- Logs in with the dev admin (override with LIFELOG_ADMIN_USER/LIFELOG_ADMIN_PASS).
- Creates (or reuses) a device for this machine and fetches the device key.
- Sets up the Python Agent and installs it as a background service.
- Prints how to view your timeline and where logs live.

Defaults:
- Server URL: http://localhost:8000 (override with LIFELOG_SERVER_URL)
- Admin user/pass (dev): admin / admin123

If you prefer manual steps, see the Server and Agent sections below.

## Quickstart: Bootstrap Development Data (optional)

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

## Notes

- Embeddings now run in-process inside the server. The separate embedding microservice has been removed from Docker Compose.
