#!/usr/bin/env bash
# Install LifeLog Agent as a system service
# Supports macOS (LaunchAgent), Linux (systemd), and provides Windows instructions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$HOME/.lifelog/agent"
# Prefer per-project venv if present, else per-user agent venv
PROJECT_VENV_PY="${SCRIPT_DIR}/.venv/bin/python"
USER_VENV_PY="$AGENT_DIR/venv/bin/python"
if [ -x "$PROJECT_VENV_PY" ]; then
  VENV_PYTHON="$PROJECT_VENV_PY"
else
  VENV_PYTHON="$USER_VENV_PY"
fi

echo "🔧 LifeLog Agent Service Installer"
echo "===================================="
echo ""

# Detect OS
OS="$(uname -s)"

case "$OS" in
    Darwin)
        echo "📱 Detected: macOS"
        echo ""
        
        # Check if Python exists
        if [ ! -x "$VENV_PYTHON" ]; then
            echo "❌ Python not found at $VENV_PYTHON"
            echo "   Run ./setup.sh in clients/agent first!"
            exit 1
        fi
        
        # Create LaunchAgent plist
        PLIST_DIR="$HOME/Library/LaunchAgents"
        PLIST_PATH="$PLIST_DIR/com.lifelog.agent.plist"
        
        echo "Creating LaunchAgent at $PLIST_PATH..."
        mkdir -p "$PLIST_DIR"
        
        cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lifelog.agent</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>-m</string>
        <string>lifelog_agent</string>
        <string>run</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$AGENT_DIR</string>
    
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
    <string>$AGENT_DIR/agent.log</string>
    
    <key>StandardErrorPath</key>
    <string>$AGENT_DIR/agent_error.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONPATH</key>
        <string>${SCRIPT_DIR}</string>
    </dict>
    
    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
EOF
        
        echo "✅ LaunchAgent created"
        echo ""
        echo "Loading service..."
        launchctl load "$PLIST_PATH" 2>/dev/null || echo "Service already loaded"
        
        echo ""
        echo "🎉 Installation complete!"
        echo ""
        echo "Commands:"
        echo "  Start:   launchctl load $PLIST_PATH"
        echo "  Stop:    launchctl unload $PLIST_PATH"
        echo "  Status:  launchctl list | grep lifelog"
        echo "  Logs:    tail -f $AGENT_DIR/agent.log"
        echo ""
        echo "The agent will now start automatically on login!"
        ;;
        
    Linux)
        echo "🐧 Detected: Linux"
        echo ""
        
        # Check if Python exists
        if [ ! -x "$VENV_PYTHON" ]; then
            echo "❌ Python not found at $VENV_PYTHON"
            echo "   Run ./setup.sh in clients/agent first!"
            exit 1
        fi
        
        # Create systemd user service
        SYSTEMD_DIR="$HOME/.config/systemd/user"
        SERVICE_PATH="$SYSTEMD_DIR/lifelog-agent.service"
        
        mkdir -p "$SYSTEMD_DIR"
        
        echo "Creating systemd service at $SERVICE_PATH..."
        
        cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=LifeLog Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$VENV_PYTHON -m lifelog_agent run
WorkingDirectory=$AGENT_DIR
Restart=always
RestartSec=30
StandardOutput=append:$AGENT_DIR/agent.log
StandardError=append:$AGENT_DIR/agent_error.log

[Install]
WantedBy=default.target
EOF
        
        echo "✅ Systemd service created"
        echo ""
        echo "Enabling and starting service..."
        systemctl --user daemon-reload
        systemctl --user enable lifelog-agent
        systemctl --user start lifelog-agent
        
        echo ""
        echo "🎉 Installation complete!"
        echo ""
        echo "Commands:"
        echo "  Start:   systemctl --user start lifelog-agent"
        echo "  Stop:    systemctl --user stop lifelog-agent"
        echo "  Status:  systemctl --user status lifelog-agent"
        echo "  Logs:    journalctl --user -u lifelog-agent -f"
        echo ""
        echo "The agent will now start automatically on login!"
        ;;
        
    MINGW*|MSYS*|CYGWIN*)
        echo "🪟 Detected: Windows"
        echo ""
        echo "Windows Task Scheduler setup requires manual configuration."
        echo ""
        echo "📝 Instructions:"
        echo ""
        echo "1. Open Task Scheduler (taskschd.msc)"
        echo "2. Create Basic Task..."
        echo "3. Name: LifeLog Agent"
        echo "4. Trigger: When I log on"
        echo "5. Action: Start a program"
        echo "6. Program: $VENV_PYTHON"
        echo "7. Arguments: -m lifelog_agent run"
        echo "8. Start in: $AGENT_DIR"
        echo ""
        echo "Advanced Settings:"
        echo "  - ✅ Run whether user is logged on or not"
        echo "  - ✅ Run with highest privileges (optional)"
        echo "  - ✅ If task fails, restart every: 1 minute"
        echo "  - ✅ Attempt restart up to: 999 times"
        echo ""
        echo "Or use this PowerShell command (Run as Administrator):"
        echo ""
        echo "  \$action = New-ScheduledTaskAction -Execute '$VENV_PYTHON' -Argument '-m lifelog_agent run' -WorkingDirectory '$AGENT_DIR'"
        echo "  \$trigger = New-ScheduledTaskTrigger -AtLogon"
        echo "  \$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)"
        echo "  Register-ScheduledTask -TaskName 'LifeLog Agent' -Action \$action -Trigger \$trigger -Settings \$settings"
        ;;
        
    *)
        echo "❌ Unsupported operating system: $OS"
        echo "Please install manually for your platform."
        exit 1
        ;;
esac
