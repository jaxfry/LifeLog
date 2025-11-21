# LifeLog Client

The client application for LifeLog that runs on user devices to collect and sync data to the central server.

## Features

- **System tray integration** for easy access
- **Automatic data collection** through extensions
- **Local buffering** for offline operation
- **Automatic sync** with central server
- **Extension management** with auto-updates

## Project Structure

```
lifelog_client/
├── core/
│   ├── config.py           # Configuration management
│   ├── database.py         # Local SQLite buffer
│   ├── extension_manager.py # Extension lifecycle
│   └── sync_engine.py      # Server synchronization
├── extensions/             # Installed extensions
│   └── com.lifelog.aw/    # ActivityWatch extension
├── install.py              # Setup wizard
└── main.py                 # Main entry point
```

## Installation

### Prerequisites

- Python 3.11+
- Active LifeLog server instance

### Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the installation wizard:
   ```bash
   python install.py
   ```
   
   You will be prompted for:
   - Server URL (e.g., `http://localhost:8000`)
   - Device name
   - API key (obtained from server)

3. Start the client:
   ```bash
   python main.py
   ```

## Usage

### System Tray

Once running, the LifeLog client appears in your system tray with these options:

- **Sync Now** - Manually trigger data synchronization
- **Open Config** - View configuration file location
- **Quit** - Stop the client

### Configuration

Configuration is stored in `~/.lifelog/config.json` (or similar OS-specific location).

Manual configuration:
```json
{
  "server_url": "http://localhost:8000",
  "device_id": "your-device-id",
  "api_key": "your-api-key"
}
```

## Extensions

The client automatically downloads and manages extensions from the server.

### Extension Updates

Extensions are checked for updates every 6 hours. Updates are automatically downloaded and applied.

### Extension Structure

Each extension runs as a separate process and outputs JSON data to stdout:

```python
import json
import time

while True:
    data = collect_data()
    print(json.dumps(data))
    time.sleep(60)
```

The client captures this output and buffers it locally before syncing to the server.

## Local Buffer

Data is temporarily stored in a local SQLite database (`~/.lifelog/buffer.db`) before being synced to the server. This ensures:

- **Offline operation** - Data collection continues without server connection
- **Retry logic** - Failed syncs are automatically retried
- **Data integrity** - No data loss during network issues

## Synchronization

### Sync Interval

Default: Every 30 seconds

Configure by modifying `SyncEngine` initialization in `main.py`:
```python
sync_engine = SyncEngine(interval=60)  # Sync every 60 seconds
```

### Deduplication

The client calculates a SHA256 hash of each payload and sends it to the server. The server uses this hash to avoid storing duplicates.

## Logging

Logs are written to:
- `lifelog_client.log` in the current directory
- Console output

## Troubleshooting

### Client Won't Start

1. Verify configuration:
   ```bash
   python install.py
   ```

2. Check server connectivity:
   ```bash
   curl http://your-server-url/
   ```

3. Review logs in `lifelog_client.log`

### Extensions Not Running

1. Check extension directory exists: `extensions/`
2. Verify extension manifest is valid JSON
3. Check extension logs in console output
4. Ensure extension dependencies are installed

### Sync Issues

1. Verify server URL is correct
2. Check API key is valid
3. Ensure server is accessible
4. Review sync logs for error messages

### High CPU/Memory Usage

1. Check extension processes:
   ```bash
   ps aux | grep python
   ```

2. Review extension code for infinite loops or memory leaks
3. Reduce sync frequency if needed

## Development

### Running in Development Mode

```bash
python main.py
```

The client will run in the foreground and log to the console.

### Creating Custom Extensions

1. Create extension directory:
   ```
   extensions/com.your.extension/
   ```

2. Add `manifest.json`:
   ```json
   {
     "id": "com.your.extension",
     "name": "Your Extension",
     "version": "1.0.0",
     "client": {
       "type": "python",
       "file": "collector.py"
     }
   }
   ```

3. Add `collector.py`:
   ```python
   import json
   import time
   
   while True:
       data = {"your": "data"}
       print(json.dumps(data))
       time.sleep(60)
   ```

4. Add `processor.py` (server-side):
   ```python
   def normalize(payload):
       return [{
           "type": "your_event_type",
           "data": payload
       }]
   ```

## Security

- API keys are stored locally in plain text - ensure proper file permissions
- Use HTTPS for production server connections
- Extensions run with full user privileges - only install trusted extensions

## Platform Support

- **Linux**: Tested on Ubuntu 20.04+
- **macOS**: Requires additional system tray dependencies
- **Windows**: Requires additional system tray dependencies

## Performance

- Minimal resource usage when idle
- Extension processes are monitored and restarted if they crash
- Local buffer prevents data loss
- Efficient JSON-based communication

## API

The client interacts with these server endpoints:

- `POST /api/v1/ingest` - Submit collected data
- `GET /api/v1/client/extensions` - List available extensions
- `GET /api/v1/client/download/{id}` - Download extension package

## Contributing

When contributing extensions or client improvements:

1. Test thoroughly on your platform
2. Follow Python best practices
3. Add appropriate error handling
4. Document any new configuration options
5. Update this README as needed
