#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# LifeLog Agent Installer & Setup Wizard – portable edition
# -----------------------------------------------------------------------------
# This script replaces the previous "LifeLog Daemon" installer. The new
# branding (Agent) reflects that the program may collect data from multiple
# local sources, not just ActivityWatch. At install‑time, the user can choose
# which sources to enable.
# -----------------------------------------------------------------------------
set -Eeuo pipefail

# Attempt to enable inherit_errexit when supported (bash 4.4+)
if ( set -o | grep -q inherit_errexit ); then
    shopt -s inherit_errexit
fi

# ──────────────────────────────────────────────────────────────────────────────
# Styling helpers
# ──────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
PURPLE='\033[0;35m'; CYAN='\033[0;36m'; WHITE='\033[1;37m'; BOLD='\033[1m'
DIM='\033[2m'; NC='\033[0m'

[[ -t 1 && -z ${NO_COLOR-} ]] && _COLOR_OK=1 || _COLOR_OK=0
c() { [[ $_COLOR_OK == 1 ]] && printf '%b' "$1"; }

# ──────────────────────────────────────────────────────────────────────────────
# Default configuration
# ──────────────────────────────────────────────────────────────────────────────
LIFELOG_DIR="$HOME/.lifelog"
AGENT_DIR="$LIFELOG_DIR/agent"
CONFIG_FILE="$LIFELOG_DIR/config.env"
LOG_FILE="$LIFELOG_DIR/agent.log"
SERVICE_NAME="lifelog-agent"
GITHUB_REPO="your-username/lifelog"   # ← change me
PYTHON_MIN_VERSION="3.8"

# Runtime/config vars (populated later)
INSTALL_TYPE="" SERVER_ENDPOINT="" AUTH_TOKEN=""
DEVICE_ID="" COLLECTION_INTERVAL=60 SEND_INTERVAL=300
LOG_LEVEL="INFO" AUTO_START=true PYTHON_CMD=""

# Data‑source toggles (set by choose_sources)
ENABLE_ACTIVITYWATCH=true   # default on
# More sources can be added here in the future

# ──────────────────────────────────────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────────────────────────────────────
print_banner() {
    clear 2>/dev/null || true
    echo -e "${CYAN}${BOLD}"
    cat <<'EOF'
╭─────────────────────────────────────────────────────────────────╮
│                                                                 │
│  ██╗     ██╗███████╗███████╗██╗      ██████╗  ██████╗           │
│  ██║     ██║██╔════╝██╔════╝██║     ██╔═══██╗██╔════╝           │
│  ██║     ██║█████╗  █████╗  ██║     ██║   ██║██║  ███╗          │
│  ██║     ██║██╔══╝  ██╔══╝  ██║     ██║   ██║██║   ██║          │
│  ███████╗██║██║     ███████╗███████╗╚██████╔╝╚██████╔╝          │
│  ╚══════╝╚═╝╚═╝     ╚══════╝╚══════╝ ╚═════╝  ╚═════╝           │
│                                                                 │
│               🚀  Personal Data‑Collection Agent                │
│                                                                 │
╰─────────────────────────────────────────────────────────────────╯
EOF
    echo -e "${NC}\n${WHITE}${BOLD}Welcome to the LifeLog Agent Installer!${NC}"
    echo -e "${DIM}Automatically collect & ship your activity streams${NC}\n"
}

step()  { echo -e "${BLUE}${BOLD}▶${NC} ${WHITE}$*${NC}"; }
ok()    { echo -e "${GREEN}${BOLD}✓${NC} ${GREEN}$*${NC}"; }
warn()  { echo -e "${YELLOW}${BOLD}⚠${NC} ${YELLOW}$*${NC}"; }
fail()  { echo -e "${RED}${BOLD}✗${NC} ${RED}$*${NC}"; exit 1; }
info()  { echo -e "${CYAN}${BOLD}ℹ${NC} ${CYAN}$*${NC}"; }
sep()   { echo -e "${DIM}─────────────────────────────────────────────────────────────────${NC}"; }

prompt() {
    local text=$1 default=${2-} reply
    # Print the prompt to stderr so it's not captured by command substitution
    if [[ -n $default ]]; then
        printf "%s %s" "$(c "$WHITE")$text$(c "$NC")" \
                        "$(c "$DIM")(default: $default)$(c "$NC") " >&2
    else
        printf "%s " "$(c "$WHITE")$text$(c "$NC")" >&2
    fi
    # Read the reply from stdin
    read -r reply || true
    # Echo the result to stdout so it CAN be captured
    echo "${reply:-$default}"
}

yes_no() {
    local text=$1 default=${2:-n} reply opts
    case $default in
        y|Y) opts="Y/n" ;;
        n|N) opts="y/N" ;;
        *)   fail "yes_no(): default must be y or n" ;;
    esac
    while true; do
        printf "%s [%s] " "$(c "$WHITE")$text$(c "$NC")" "$opts"
        read -r reply || true
        reply=${reply:-$default}
        case $reply in
            y|Y) return 0 ;;
            n|N) return 1 ;;
            *)   warn "Please answer y or n." ;;
        esac
    done
}

version_ge() { [ "$(printf '%s\n%s' "$2" "$1" | sort -V | head -1)" = "$2" ]; }

# ──────────────────────────────────────────────────────────────────────────────
# Dependency checks
# ──────────────────────────────────────────────────────────────────────────────
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local ver=$("$cmd" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
            if version_ge "$ver" "$PYTHON_MIN_VERSION"; then
                if "$cmd" -m pip --version &>/dev/null; then
                    PYTHON_CMD="$cmd"; return 0
                else
                    fail "Python at $(command -v "$cmd") but pip missing. Install pip.";
                fi
            fi
        fi
    done
    return 1
}

activitywatch_ok() {
    ( pgrep -fa aw-server &>/dev/null ) || ( curl -fs http://localhost:5600/api/0/info &>/dev/null )
}

check_deps() {
    step "Validating system dependencies…"
    local missing=()

    if find_python; then
        ok "Python: $(command -v "$PYTHON_CMD")"
    else
        missing+=("python>=$PYTHON_MIN_VERSION (with pip)")
    fi

    for c in git curl; do command -v "$c" &>/dev/null || missing+=("$c"); done

    if $ENABLE_ACTIVITYWATCH; then
        if ! activitywatch_ok; then
            warn "ActivityWatch not detected or not running."
            if yes_no "Continue without ActivityWatch source?" n; then
                ENABLE_ACTIVITYWATCH=false
                info "ActivityWatch source disabled for now."
            else
                fail "Please install/start ActivityWatch or disable the source."
            fi
        else
            ok "ActivityWatch running"
        fi
    fi

    if (( ${#missing[@]} )); then
        fail "Missing dependencies: ${missing[*]}"
    fi
    ok "All core dependencies satisfied"
}

# ──────────────────────────────────────────────────────────────────────────────
# Interactive configuration
# ──────────────────────────────────────────────────────────────────────────────
choose_install() {
    sep
    echo -e "${WHITE}${BOLD}Choose installation type:${NC}\n"
    echo -e "${GREEN}1)${NC} Quick     – defaults, local server"
    echo -e "${GREEN}2)${NC} Custom    – choose server / options"
    echo -e "${GREEN}3)${NC} Dev       – local hacking\n"
    while :; do
        local sel
        sel=$(prompt "Enter 1-3:" 1)
        case "$sel" in
            1) INSTALL_TYPE=quick;        break ;;
            2) INSTALL_TYPE=custom;       break ;;
            3) INSTALL_TYPE=development;  break ;;
            *) warn "Invalid choice" ;;
        esac
    done
}

choose_sources() {
    sep
    echo -e "${WHITE}${BOLD}Select data sources to enable:${NC}\n"
    echo -e "${GREEN}1)${NC} ActivityWatch (desktop usage)  ${DIM}[default]${NC}"
    echo -e "${GREEN}2)${NC} None for now\n"
    local sel
    sel=$(prompt "Enter choice:" 1)
    case "$sel" in
        1) ENABLE_ACTIVITYWATCH=true ;;
        2) ENABLE_ACTIVITYWATCH=false ;;
        *) warn "Unknown choice; defaulting to ActivityWatch"; ENABLE_ACTIVITYWATCH=true ;;
    esac

    if $ENABLE_ACTIVITYWATCH; then
        ok "ActivityWatch source enabled"
    else
        info "No local sources selected – agent will install but remain idle until configured."
    fi
}

conf_quick() {
    SERVER_ENDPOINT="http://localhost:8001/api/v1/ingest"
    AUTH_TOKEN="quick-$RANDOM"
    DEVICE_ID="$(hostname)-$RANDOM"
    ok "Quick config applied"
}

conf_custom() {
    SERVER_ENDPOINT=$(prompt "LifeLog server endpoint URL:" "https://your-lifelog-server.com/api/v1/ingest")
    AUTH_TOKEN=$(prompt "Auth token (leave blank to generate):")
    [[ -z $AUTH_TOKEN ]] && AUTH_TOKEN="token-$(openssl rand -hex 12 2>/dev/null || date +%s)" \
        && info "Generated token: $AUTH_TOKEN"
    DEVICE_ID=$(prompt "Device ID:" "$(hostname)-$(whoami)")
    COLLECTION_INTERVAL=$(prompt "Collection interval (s):" 60)
    SEND_INTERVAL=$(prompt "Send interval (s):" 300)
    LOG_LEVEL=$(prompt "Log level [DEBUG|INFO|WARN|ERROR]:" INFO)
    ok "Custom config captured"
}

conf_dev() {
    SERVER_ENDPOINT="http://localhost:8001/api/v1/ingest"
    AUTH_TOKEN="dev-$RANDOM"
    DEVICE_ID="dev-$(hostname)"
    COLLECTION_INTERVAL=30 SEND_INTERVAL=60 LOG_LEVEL=DEBUG
    ok "Dev config applied"
}

# ──────────────────────────────────────────────────────────────────────────────
# Installation helpers
# ──────────────────────────────────────────────────────────────────────────────
create_dirs() {
    step "Creating directories"
    mkdir -p "$AGENT_DIR" "$LIFELOG_DIR/logs"
    ok "Directories ready"
}

download_agent() {
    step "Downloading LifeLog agent from GitHub (${GITHUB_REPO})"
    local tmp
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' RETURN

    git clone --quiet --depth 1 "https://github.com/${GITHUB_REPO}.git" "$tmp/repo" \
        || fail "git clone failed"

    if [[ -d $tmp/repo/agent ]]; then
        cp -R "$tmp/repo/agent/"* "$AGENT_DIR/"
    else
        cp -R "$tmp/repo/"* "$AGENT_DIR/"
    fi
    ok "Agent source downloaded"
}

install_python_deps() {
    step "Installing Python requirements"
    cat > "$AGENT_DIR/requirements.txt" <<'REQ'
requests>=2.25.0
apscheduler>=3.8.0
python-dotenv>=0.19.0
aw-client>=0.5.6   # used only if ActivityWatch source is enabled
REQ
    "$PYTHON_CMD" -m pip install --quiet --upgrade --user -r "$AGENT_DIR/requirements.txt" \
        || fail "pip install failed"
    ok "Python deps installed"
}

gen_config() {
    step "Writing config (${CONFIG_FILE})"
    {
      echo "# ── generated: $(date) ──"
      echo "CENTRAL_SERVER_ENDPOINT=\"$SERVER_ENDPOINT\""
      echo "SERVER_AUTH_TOKEN=\"$AUTH_TOKEN\""
      echo "DEVICE_ID=\"$DEVICE_ID\""
      echo "COLLECTION_INTERVAL_SECONDS=$COLLECTION_INTERVAL"
      echo "BATCH_SEND_INTERVAL_SECONDS=$SEND_INTERVAL"
      echo "LOG_LEVEL=\"$LOG_LEVEL\""
      echo "LOG_FILE=\"$LOG_FILE\""
      echo "ENABLE_ACTIVITYWATCH=$ENABLE_ACTIVITYWATCH"
    } > "$CONFIG_FILE"
    ok "Config file created"
}

create_launcher() {
    step "Creating launcher script"
    local launcher="$LIFELOG_DIR/lifelog-agent"
    cat > "$launcher" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
LIFELOG_DIR="${LIFELOG_DIR:-$HOME/.lifelog}"
CONFIG_FILE="$LIFELOG_DIR/config.env"
[[ -f "$CONFIG_FILE" ]] && set -a && source "$CONFIG_FILE" && set +a
AGENT_DIR="$LIFELOG_DIR/agent"
PYTHON_CMD="${PYTHON_CMD:-python3}"
cd "$AGENT_DIR"
exec "$PYTHON_CMD" agent.py "$@"
LAUNCH
    chmod +x "$launcher"
    mkdir -p "$HOME/.local/bin"
    ln -sf "$launcher" "$HOME/.local/bin/lifelog-agent"
    ok "Launcher ready (run: lifelog-agent)"
}

setup_systemd() {
    if ! command -v systemctl &>/dev/null; then
        warn "Systemd not available; skipping autostart."
        return
    fi
    local svc="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
    mkdir -p "$(dirname "$svc")"
    cat > "$svc" <<EOF
[Unit]
Description=LifeLog Agent
After=graphical-session.target

[Service]
Type=simple
ExecStart=$LIFELOG_DIR/lifelog-agent
EnvironmentFile=$CONFIG_FILE
Restart=always

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    if $AUTO_START; then
        systemctl --user enable --now "$SERVICE_NAME"
        ok "systemd service enabled & started"
    else
        ok "systemd service installed (not enabled)"
    fi
}

setup_launchd() {
    local plist="$HOME/Library/LaunchAgents/com.lifelog.agent.plist"
    mkdir -p "$(dirname "$plist")"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.lifelog.agent</string>
    <key>ProgramArguments</key><array><string>$LIFELOG_DIR/lifelog-agent</string></array>
    <key>RunAtLoad</key><${AUTO_START:+true}${AUTO_START:-false}/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LIFELOG_DIR/logs/agent.out.log</string>
    <key>StandardErrorPath</key><string>$LIFELOG_DIR/logs/agent.err.log</string>
</dict></plist>
EOF
    if $AUTO_START; then
        launchctl load -w "$plist"
        ok "launchd agent loaded"
    else
        ok "launchd agent installed (not loaded)"
    fi
}

setup_autostart() {
    case "$(uname -s)" in
        Linux*)  setup_systemd ;;
        Darwin*) setup_launchd ;;
        *)       warn "Autostart not supported on this OS" ;;
    esac
}

self_test() {
    step "Running self-test"
    "$PYTHON_CMD" - <<'PY'
import json, os, pathlib, sys
root = pathlib.Path(os.environ['LIFELOG_DIR']) / 'agent'
missing = [str(p) for p in (root / 'agent.py',).findall() if not p.exists()]  # noqa
if missing:
    print(json.dumps({"error": "missing", "files": missing}))
    sys.exit(1)
PY
    ok "Self-test passed"
}

# ──────────────────────────────────────────────────────────────────────────────
# Main execution flow
# ──────────────────────────────────────────────────────────────────────────────
main() {
    [[ $EUID -eq 0 ]] && fail "Please run as a regular user, not root."

    print_banner
    info "Using Bash $(bash --version | head -1)"
    yes_no "Continue installation?" y || { warn "Aborted"; exit 0; }

    choose_sources
    check_deps
    choose_install
    case $INSTALL_TYPE in
        quick)        conf_quick ;;
        custom)       conf_custom ;;
        development)  conf_dev ;;
    esac

    AUTO_START=$( yes_no "Start agent automatically on login?" y && echo true || echo false )

    sep; step "Installing…"
    create_dirs
    download_agent
    install_python_deps
    gen_config
    create_launcher
    $AUTO_START && setup_autostart || true
    self_test

    sep
    ok "Installation complete!"
    echo -e "Run ${CYAN}lifelog-agent${NC} (or reboot) to start the agent."
}

main "$@"
