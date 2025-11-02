# LifeLog Agent - Edge Cases & Production Readiness

## Current Implementation Status

### ✅ What We Handle Well

1. **Collector Crashes**
   - Auto-restart with exponential backoff (1s → 2s → 4s → ... → 60s max)
   - Keeps retrying indefinitely
   
2. **Network Failures**
   - SQLite queue persists data offline
   - Failed sends stay in queue for retry
   
3. **Invalid Data**
   - JSON parse errors are caught and logged as warnings
   - Agent continues running

4. **Server Downtime**
   - Queue accumulates data locally (up to 50MB)
   - Automatic retry on next flush cycle

### ❌ Critical Missing Pieces

## 1. Device Restart / Persistence

**Current Problem**: Agent ONLY runs when manually started
- If Mac restarts → agent stops
- User logs out → agent stops
- Terminal closes → agent stops

**Solution Needed**: System Service Integration

### For macOS - LaunchAgent

Create: `~/Library/LaunchAgents/com.lifelog.agent.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lifelog.agent</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOU/.lifelog/agent/venv/bin/python</string>
        <string>-m</string>
        <string>lifelog_agent</string>
        <string>run</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>/Users/YOU/.lifelog/agent</string>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>
    
    <key>StandardOutPath</key>
    <string>/Users/YOU/.lifelog/agent/agent.log</string>
    
    <key>StandardErrorPath</key>
    <string>/Users/YOU/.lifelog/agent/agent_error.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    
    <!-- Restart if crashes -->
    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
```

**Commands**:
```bash
# Load (start now and on login)
launchctl load ~/Library/LaunchAgents/com.lifelog.agent.plist

# Unload (stop)
launchctl unload ~/Library/LaunchAgents/com.lifelog.agent.plist

# View status
launchctl list | grep lifelog
```

### For Linux - systemd

Create: `~/.config/systemd/user/lifelog-agent.service`

```ini
[Unit]
Description=LifeLog Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/home/YOU/.lifelog/agent/venv/bin/python -m lifelog_agent run
WorkingDirectory=/home/YOU/.lifelog/agent
Restart=always
RestartSec=30
StandardOutput=append:/home/YOU/.lifelog/agent/agent.log
StandardError=append:/home/YOU/.lifelog/agent/agent_error.log

[Install]
WantedBy=default.target
```

**Commands**:
```bash
systemctl --user enable lifelog-agent  # Start on login
systemctl --user start lifelog-agent   # Start now
systemctl --user status lifelog-agent  # Check status
```

## 2. Laptop Lid Closed / Sleep

**Current Problem**: No power management awareness
- Agent keeps polling while Mac is asleep (wastes battery)
- Queue may grow during sleep
- Timestamps may be incorrect after wake

**Solution**: Sleep/Wake Detection

Add to `runner.py`:

```python
import platform
from datetime import datetime, timezone

class PowerManager:
    def __init__(self):
        self.last_wake = datetime.now(timezone.utc)
        self.sleep_callback_registered = False
        
    async def setup(self):
        """Register sleep/wake callbacks"""
        if platform.system() == "Darwin":
            # macOS - use subprocess to monitor system power
            asyncio.create_task(self._monitor_macos_power())
    
    async def _monitor_macos_power(self):
        """Monitor macOS power events via pmset log"""
        import subprocess
        proc = await asyncio.create_subprocess_exec(
            "pmset", "-g", "log",
            stdout=asyncio.subprocess.PIPE
        )
        async for line in proc.stdout:
            if b"Wake" in line:
                self.last_wake = datetime.now(timezone.utc)
                logger.info("System woke up - resuming collection")
            elif b"Sleep" in line:
                logger.info("System going to sleep - pausing collection")

# In runner.py:
async def run_agent(cfg: AgentConfig):
    power_mgr = PowerManager()
    await power_mgr.setup()
    
    # ... existing code ...
    
    # Before polling, check if just woke up
    if datetime.now(timezone.utc) - power_mgr.last_wake < timedelta(minutes=1):
        # Just woke up - collectors may have stale data
        # Could signal collectors to reset their timestamps
        pass
```

**Better Alternative**: Just rely on the system service to handle this
- LaunchAgent/systemd will pause when system sleeps
- Automatically resume on wake

## 3. Easy Configuration (AW Port, etc.)

**Current Problem**: Config is hardcoded in device metadata or local JSON

**Solution**: Add configuration management commands

```bash
# Set AW port for a specific collector
python -m lifelog_agent config set activitywatch-connector activitywatch-source aw_base_url http://localhost:5601

# View current config
python -m lifelog_agent config show

# Reset to defaults
python -m lifelog_agent config reset
```

Also support environment variables:

```bash
# Override config via env vars
LIFELOG_AW_BASE_URL=http://localhost:5601 python -m lifelog_agent run
```

## 4. Battery Impact & Efficiency

**Current Issues**:
- Polls server every 5 minutes (300s default)
- Collectors poll every 15s
- No backoff when on battery
- No CPU throttling

### Optimizations Needed:

#### A. Adaptive Polling

```python
class AdaptiveConfig:
    def __init__(self, cfg: AgentConfig):
        self.base_interval = cfg.poll_interval_sec
        self.on_battery = self._is_on_battery()
        
    def _is_on_battery(self) -> bool:
        """Detect power source"""
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True,
                text=True
            )
            return "Battery Power" in result.stdout
        return False
    
    def get_poll_interval(self) -> int:
        """Return adaptive interval based on power state"""
        if self.on_battery:
            return self.base_interval * 2  # Poll less frequently on battery
        return self.base_interval
    
    def get_collector_interval(self, default: int) -> int:
        """Collector-specific interval"""
        if self.on_battery:
            return max(default * 2, 30)  # At least 30s on battery
        return default
```

#### B. Intelligent Wake

```python
# Instead of constant polling, use event-driven approach
# Wake only when:
# 1. Queue has data to send
# 2. Config needs refresh (every 15 min)
# 3. Extension check (every hour)

async def run_agent_efficient(cfg: AgentConfig):
    last_config_sync = 0
    last_extension_sync = 0
    
    while True:
        now = time.time()
        
        # Always flush queue if it has data
        if queue.has_data():
            await flush_queue(client, queue)
        
        # Config sync every 15 min
        if now - last_config_sync > 900:
            await sync_config(cfg, client)
            last_config_sync = now
        
        # Extension check every hour
        if now - last_extension_sync > 3600:
            await sync_extensions(cfg, client, sup)
            last_extension_sync = now
        
        # Adaptive sleep
        sleep_time = 30 if queue.has_data() else 300
        await asyncio.sleep(sleep_time)
```

#### C. CPU/Memory Limits

```python
# Limit collector CPU usage
import resource

def set_resource_limits():
    """Prevent runaway collectors from killing battery"""
    # Limit CPU time per process (soft, hard) in seconds
    resource.setrlimit(resource.RLIMIT_CPU, (60, 120))
    
    # Limit memory to 100MB per collector
    resource.setrlimit(resource.RLIMIT_AS, (100 * 1024 * 1024, 150 * 1024 * 1024))
```

## 5. Internet Cuts Out

**Current**: ✅ Partially handled
- Queue persists data
- Retry on next flush

**Improvement Needed**: Exponential backoff on network errors

```python
class RetryManager:
    def __init__(self):
        self.consecutive_failures = 0
        self.last_failure = None
    
    def backoff_seconds(self) -> int:
        """Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)"""
        return min(2 ** self.consecutive_failures, 30)
    
    def record_success(self):
        self.consecutive_failures = 0
    
    def record_failure(self):
        self.consecutive_failures += 1
        self.last_failure = time.time()

# In flush_queue:
retry_mgr = RetryManager()

async def flush_queue(client, queue, retry_mgr):
    try:
        # ... existing flush logic ...
        retry_mgr.record_success()
    except Exception:
        retry_mgr.record_failure()
        # Wait before next attempt
        await asyncio.sleep(retry_mgr.backoff_seconds())
```

## 6. Logging & Debugging

**Current**: ❌ No logging infrastructure

**Needed**: Structured logging with rotation

```python
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_file = CONFIG_DIR / "agent.log"
    
    handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[handler, logging.StreamHandler()]
    )

logger = logging.getLogger("lifelog.agent")
```

## Priority Recommendations

### Must Have (Before Production):

1. **✅ System Service Integration** (LaunchAgent/systemd)
   - Auto-start on login
   - Auto-restart on crash
   - Essential for "constantly running"

2. **✅ Proper Logging**
   - Debug crashes
   - Monitor health
   - Rotate logs automatically

3. **✅ Network Retry Logic**
   - Exponential backoff
   - Max retries
   - Alert on persistent failures

### Should Have (Soon):

4. **🔶 Power Management**
   - Detect battery state
   - Adaptive polling intervals
   - Sleep/wake awareness

5. **🔶 Configuration UI**
   - Easy port changes
   - View current settings
   - Validate configs

6. **🔶 Health Monitoring**
   - Last successful sync timestamp
   - Queue size metrics
   - Collector status

### Nice to Have (Future):

7. **⭐ GUI Status Bar App**
   - macOS menu bar icon
   - Show sync status
   - Quick config access

8. **⭐ Update Mechanism**
   - Auto-update extensions
   - Agent version check
   - Rollback on failure

9. **⭐ Analytics**
   - Battery usage stats
   - Network data usage
   - Performance metrics

## Immediate Next Steps

Create these files to make it production-ready:

1. `clients/agent/install.sh` - Sets up LaunchAgent/systemd service
2. `clients/agent/lifelog_agent/logging.py` - Structured logging
3. `clients/agent/lifelog_agent/retry.py` - Network retry logic
4. Update `runner.py` - Add power management awareness
5. `clients/agent/lifelog_agent/health.py` - Health check endpoint

Would you like me to implement any of these?
