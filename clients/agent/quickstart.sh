#!/usr/bin/env bash
# Complete quickstart for ActivityWatch extension demo

set -e

echo "🎯 LifeLog ActivityWatch Extension Quickstart"
echo "=============================================="
echo ""

# Configuration
SERVER_URL="http://localhost:8000"
PLATFORM="macos"

# Step 1: Check server
echo "1️⃣  Checking server..."
if ! curl -s "${SERVER_URL}/health" > /dev/null 2>&1; then
    echo "❌ Server not reachable at ${SERVER_URL}"
    echo "   Start it with: docker compose up -d --build"
    exit 1
fi
echo "✅ Server is running"
echo ""

# Step 1.5: Get JWT token
echo "🔐 Getting authentication token..."
TOKEN_RESPONSE=$(curl -s -X POST "${SERVER_URL}/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to get authentication token"
    echo "   Make sure default credentials are: username=admin, password=admin123"
    exit 1
fi
echo "✅ Authenticated"
echo ""

# Step 2: Register extension
echo "2️⃣  Registering ActivityWatch extension..."
REGISTER_RESPONSE=$(curl -s -X POST "${SERVER_URL}/internal/extensions/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "slug": "activitywatch-connector",
    "name": "ActivityWatch Connector",
    "version": "1.0.0",
    "config": {}
  }')

if echo "$REGISTER_RESPONSE" | grep -q "slug"; then
    echo "✅ Extension registered successfully"
else
    echo "⚠️  Extension might already be registered (this is OK)"
fi
echo ""

# Step 3: Set up actor routing
echo "3️⃣  Setting up actor routing..."
ROUTING_RESPONSE=$(curl -s -X POST "${SERVER_URL}/internal/actor-routing/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "source_actor_slug": "activitywatch-source",
    "processor_actor_slug": "aw-processor"
  }')

if echo "$ROUTING_RESPONSE" | grep -q "source_actor_slug"; then
    echo "✅ Actor routing configured"
else
    echo "⚠️  Routing might already exist (this is OK)"
fi
echo ""

# Step 4: Create device if needed
echo "4️⃣  Creating device for agent..."
DEVICE_RESPONSE=$(curl -s -X POST "${SERVER_URL}/internal/devices/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{
    \"name\": \"Development Mac\",
    \"platform\": \"${PLATFORM}\",
    \"client_metadata\": {
      \"agent\": {
        \"poll_interval_sec\": 30
      },
      \"collectors\": {
        \"activitywatch-connector\": {
          \"activitywatch-source\": {
            \"aw_base_url\": \"http://127.0.0.1:5600\",
            \"interval_sec\": 15
          }
        }
      }
    }
  }")

DEVICE_KEY=$(echo "$DEVICE_RESPONSE" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)

if [ -z "$DEVICE_KEY" ]; then
    echo "❌ Failed to create device. Response:"
    echo "$DEVICE_RESPONSE"
    exit 1
fi

echo "✅ Device created with key: ${DEVICE_KEY}"
echo ""

# Step 5: Initialize agent
echo "5️⃣  Initializing agent..."
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "📦 Setting up virtual environment..."
    ./setup.sh
fi

source .venv/bin/activate

python -m lifelog_agent init \
  --server "${SERVER_URL}" \
  --device-key "${DEVICE_KEY}" \
  --platform "${PLATFORM}"

echo "✅ Agent initialized"
echo ""

echo "🎉 Setup complete!"
echo ""
echo "To run the agent:"
echo "  ./run.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  python -m lifelog_agent run"
echo ""
echo "Note: Make sure ActivityWatch is running at http://127.0.0.1:5600"
echo "      Install from: https://activitywatch.net"
echo ""
