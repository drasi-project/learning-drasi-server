#!/bin/bash
# Post-create script for the Drasi Server Curbside Pickup tutorial

set -e

echo "🔧 Initializing Drasi Server Curbside Pickup tutorial environment..."

# Resolve the tutorial directory from this script's location so it works
# regardless of the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TUTORIAL_DIR="$REPO_ROOT/tutorials/curbside-pickup"

# Download the pre-built Drasi Server binary into the tutorial directory.
# Invoke via `bash` so we don't depend on the executable bit, which can be lost
# on Windows bind-mounts where chmod is not permitted on the mounted filesystem.
echo "⬇️  Downloading Drasi Server binary..."
cd "$TUTORIAL_DIR"
bash scripts/download.sh

# Install the TUI dependencies ahead of time so the first run is fast.
if command -v npm &> /dev/null; then
    echo "📦 Installing TUI dependencies..."
    (cd "$TUTORIAL_DIR/tui" && npm install --no-fund --no-audit)
fi

echo ""
echo "✅ Drasi Server Curbside Pickup tutorial environment is ready!"
echo "   Next: follow README.md (you are already in tutorials/curbside-pickup)"
echo "   - Terminal 1: ./scripts/start-demo.sh"
echo "   - Terminal 2: ./scripts/start-tui.sh"
