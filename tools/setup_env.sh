#!/usr/bin/env bash
# Bootstrap LifeLog development environment.
# - Creates a Python virtual environment
# - Installs Python and Node.js dependencies
# - Copies bundled test data for quick UI exploration
set -euo pipefail

# Determine project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# --- Python environment ---
if [ ! -d ".venv" ]; then
    python -m venv .venv
fi
source .venv/bin/activate

if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

# --- Node.js dependencies ---
if [ -d frontend ]; then
    pushd frontend >/dev/null
    npm install
    popd >/dev/null
fi

# --- Playwright browsers (optional) ---
if [ -f frontend/node_modules/.bin/playwright ]; then
    npx playwright install --with-deps || true
fi

# --- Populate sample test data ---
python -m LifeLog.cli setup-test-data

echo "Environment setup complete."
