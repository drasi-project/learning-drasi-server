#!/bin/bash
# Post-create script for the Drasi Server OTel Observability tutorial

set -e

echo "🔧 Initializing Drasi Server OTel Observability tutorial environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TUTORIAL_DIR="$REPO_ROOT/tutorials/otel-observability"

echo "🐘 Installing system dependencies (PostgreSQL client, curl)..."
sudo apt-get update && sudo apt-get install -y postgresql-client curl

if ! command -v k3d &> /dev/null; then
    echo "☸️  Installing k3d..."
    curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | sudo bash
fi

echo "⬇️  Downloading Drasi Server binary..."
cd "$TUTORIAL_DIR"
bash scripts/download.sh

echo ""
echo "✅ Drasi Server OTel Observability tutorial environment is ready!"
echo "   Next: follow README.md (you are already in tutorials/otel-observability)"
