#!/usr/bin/env bash
# Quick setup script for LifeLog agent

set -e

echo "🚀 Setting up LifeLog Agent..."

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found. Please install Python 3.11+"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Activate the environment:  source .venv/bin/activate"
echo "2. Initialize the agent:      python -m lifelog_agent init --server http://localhost:8000 --device-key YOUR_KEY --platform macos"
echo "3. Run the agent:             python -m lifelog_agent run"
echo ""
