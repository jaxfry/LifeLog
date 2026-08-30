#!/usr/bin/env bash
# Quick start script for running the LifeLog agent in development

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if config exists
if [ ! -f "$HOME/.lifelog/agent/config.json" ]; then
    echo "⚠️  No agent configuration found."
    echo ""
    echo "To initialize, run:"
    echo "  python -m lifelog_agent init --server http://localhost:8000 --device-key YOUR_KEY --platform macos"
    echo ""
    echo "To get a device key:"
    echo "  1. Start the LifeLog server (docker compose up)"
    echo "  2. Create a device via POST http://localhost:8000/internal/devices"
    echo "  3. Copy the 'api_key' from the response"
    echo ""
    exit 1
fi

echo "🤖 Starting LifeLog Agent..."
python -m lifelog_agent run
