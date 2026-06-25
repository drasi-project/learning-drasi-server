#!/bin/bash
# Post-create script for the Drasi Server Building Comfort tutorial

set -e

echo "🔧 Initializing Drasi Server Building Comfort tutorial environment..."

# Resolve the tutorial directory from this script's location so the script works
# regardless of the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TUTORIAL_DIR="$REPO_ROOT/tutorials/building-comfort"

# Install system dependencies (PostgreSQL client for the helper scripts).
echo "🐘 Installing system dependencies (PostgreSQL client)..."
sudo apt-get update && sudo apt-get install -y postgresql-client

# Download the pre-built Drasi Server binary into the tutorial directory.
# Invoke via `bash` so we don't depend on the executable bit, which can be lost
# on Windows bind-mounts where chmod is not permitted on the mounted filesystem.
echo "⬇️  Downloading Drasi Server binary..."
cd "$TUTORIAL_DIR"
bash scripts/download.sh

echo ""
echo "✅ Drasi Server Building Comfort tutorial environment is ready!"
echo "   Next: follow README.md (you are already in tutorials/building-comfort)"

