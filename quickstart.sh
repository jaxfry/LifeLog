#!/usr/bin/env bash

# LifeLog Quickstart (developer-friendly)
#
# What this does:
# 1) Starts the server with Docker Compose
# 2) Waits for the API to become healthy
# 3) Authenticates to the server (single-user admin)
# 4) Creates (or reuses) a device and returns an API key
# 5) Sets up and installs the Python Agent to run in the background
# 6) Prints how to see your timeline
#
# Requirements:
# - macOS or Linux
# - Docker + Docker Compose
# - curl + jq
# - Python 3.11+ (for the Agent)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_URL_DEFAULT="http://localhost:8000"
SERVER_URL="${LIFELOG_SERVER_URL:-$SERVER_URL_DEFAULT}"

# Admin creds (dev defaults; override via env LIFELOG_ADMIN_USER/LIFELOG_ADMIN_PASS)
ADMIN_USER="${LIFELOG_ADMIN_USER:-admin}"
ADMIN_PASS="${LIFELOG_ADMIN_PASS:-admin123}"

OS_NAME="$(uname -s)"

echo "🔧 LifeLog Quickstart"
echo "===================="
echo "Server URL: $SERVER_URL"
echo "OS:         $OS_NAME"
echo ""

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "❌ Missing required command: $1"; exit 1; }; }

need_cmd docker
need_cmd curl
need_cmd jq

start_server() {
  echo "🚀 Starting server (Docker Compose) ..."
  (cd "$ROOT_DIR" && docker compose up -d --build)
}

wait_for_health() {
  echo "⏳ Waiting for API health ($SERVER_URL/health) ..."
  for i in {1..60}; do
    if curl -fsS "$SERVER_URL/health" >/dev/null 2>&1; then
      echo "✅ API is healthy"
      return 0
    fi
    sleep 2
  done
  echo "❌ API did not become healthy in time"
  exit 1
}

get_token() {
  echo "🔐 Getting admin token ..." >&2
  local token
  token=$(curl -fsS -X POST \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" \
    "$SERVER_URL/api/v1/auth/token" | jq -r .access_token || true)
  if [[ -z "${token}" || "${token}" == "null" ]]; then
    echo "❌ Failed to authenticate. Override creds via LIFELOG_ADMIN_USER/LIFELOG_ADMIN_PASS" >&2
    exit 1
  fi
  echo "$token"
}

create_or_rotate_device() {
  local token="$1"; shift
  local name="$1"; shift

  echo "💻 Ensuring device exists: $name" >&2
  # Try to create the device first
  local create_resp
  create_resp=$(curl -fsS -X POST \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"type\":\"$OS_NAME\",\"client_metadata\":{}}" \
    "$SERVER_URL/internal/devices/" 2>/dev/null || true)

  local api_key
  api_key=$(echo "$create_resp" | jq -r .api_key 2>/dev/null || true)
  if [[ -n "$api_key" && "$api_key" != "null" ]]; then
    echo "✅ Created device and received API key" >&2
    echo "$api_key"
    return 0
  fi

  # If we couldn't create (probably already exists), find the device ID and rotate key
  echo "ℹ️  Device may already exist. Rotating key to obtain a fresh API key ..." >&2
  local dev_id
  dev_id=$(curl -fsS -H "Authorization: Bearer $token" "$SERVER_URL/internal/devices/" \
    | jq -r ".[] | select(.name==\"$name\") | .id" | head -n 1)
  if [[ -z "$dev_id" || "$dev_id" == "null" ]]; then
    echo "❌ Could not find device '$name' in list" >&2
    exit 1
  fi
  local rotate_resp
  rotate_resp=$(curl -fsS -X POST -H "Authorization: Bearer $token" \
    "$SERVER_URL/internal/devices/$dev_id/rotate-key")
  local new_key
  new_key=$(echo "$rotate_resp" | jq -r .new_api_key 2>/dev/null || true)
  if [[ -z "$new_key" || "$new_key" == "null" ]]; then
    echo "❌ Failed to rotate API key" >&2
    echo "$rotate_resp" | jq . >&2 || true
    exit 1
  fi
  echo "✅ Rotated device key"
  echo "$new_key"
}

setup_agent() {
  local server_url="$1"; shift
  local device_key="$1"; shift

  echo "🐍 Setting up LifeLog Agent ..."
  (cd "$ROOT_DIR/clients/agent" && \
    bash ./setup.sh >/dev/null)

  # Initialize agent config
  (cd "$ROOT_DIR/clients/agent" && \
    source .venv/bin/activate && \
    python -m lifelog_agent init --server "$server_url" --device-key "$device_key" --platform "$([[ "$OS_NAME" == "Darwin" ]] && echo macos || echo linux)" >/dev/null)

  # Install as background service
  (cd "$ROOT_DIR/clients/agent" && \
    bash ./install.sh >/dev/null || true)

  echo "✅ Agent installed"
}

print_summary() {
  cat <<EOF

🎉 All set!

Server:
  - Docs:        $SERVER_URL/docs
  - Health:      $SERVER_URL/health

Agent:
  - Config:      ~/.lifelog/agent/config.json
  - Logs:        tail -f ~/.lifelog/agent/agent.log

Timeline:
  - Try:         curl -s -X POST -H 'Content-Type: application/x-www-form-urlencoded' \
                   -d 'username=${ADMIN_USER}&password=${ADMIN_PASS}' $SERVER_URL/api/v1/auth/token \
                   | jq -r .access_token | \
                   xargs -I{} curl -s -H "Authorization: Bearer {}" "$SERVER_URL/api/v1/timeline/?limit=10" | jq .

ActivityWatch (optional for computer-activity):
  - Ensure AW is running locally (http://127.0.0.1:5600)

EOF
}


# --- Flow ---
start_server
wait_for_health
TOKEN="$(get_token)"

HOSTNAME_SAFE=$(hostname | tr ' ' '-')
DEVICE_NAME="${LIFELOG_DEVICE_NAME:-${HOSTNAME_SAFE}-LifeLog}"
DEVICE_KEY="$(create_or_rotate_device "$TOKEN" "$DEVICE_NAME")"

setup_agent "$SERVER_URL" "$DEVICE_KEY"
print_summary

echo "✅ Quickstart complete"
