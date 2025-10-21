# LifeLog Rewrite

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
# LifeLog Rewrite
