#!/bin/bash
# Post-create script for the Drasi Server Debezium Integration tutorial

set -e

echo "🔧 Initializing Drasi Server Debezium Integration tutorial environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TUTORIAL_DIR="$REPO_ROOT/tutorials/debezium-integration"

echo "🐘 Installing system dependencies (PostgreSQL client, curl)..."
sudo apt-get update && sudo apt-get install -y postgresql-client curl

echo "⬇️  Downloading Drasi Server binary..."
cd "$TUTORIAL_DIR"
bash scripts/download.sh

echo ""
echo "✅ Debezium Integration tutorial environment is ready!"
echo "   Next: follow README.md (you are already in tutorials/debezium-integration)"
