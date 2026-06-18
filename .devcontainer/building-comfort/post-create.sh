#!/bin/bash
# Post-create script for the Drasi Server Building Comfort tutorial

set -e

echo "🔧 Initializing Drasi Server Building Comfort tutorial environment..."

# Install system dependencies (PostgreSQL client for the helper scripts).
echo "🐘 Installing system dependencies (PostgreSQL client)..."
sudo apt-get update && sudo apt-get install -y postgresql-client

# Download the pre-built Drasi Server binary.
# Invoke via `bash` so we don't depend on the executable bit, which can be lost
# on Windows bind-mounts where chmod is not permitted on the mounted filesystem.
echo "⬇️  Downloading Drasi Server binary..."
bash tutorials/building-comfort/scripts/download.sh

echo ""
echo "✅ Drasi Server Building Comfort tutorial environment is ready!"
echo "   Next: follow tutorials/building-comfort/README.md"
