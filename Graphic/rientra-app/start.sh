#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  RIENTR@ returns — Quick Start
#  Run this from your Terminal (or iTerm2) to launch the app.
# ─────────────────────────────────────────────────────────────
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │   RIENTR@ returns — Starting up...      │"
echo "  └─────────────────────────────────────────┘"
echo ""

# Make sure dependencies are installed
if [ ! -d "node_modules/electron" ]; then
  echo "→ Installing dependencies (first run only)..."
  npm install
fi

# Export cache path if needed
export NPM_CONFIG_CACHE=/tmp/npm-cache-rientra

# Start Vite dev server + Electron together
export NODE_ENV=development
npm run dev
