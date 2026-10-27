#!/bin/bash
# Post-create script for the Drasi Server Building Comfort tutorial

set -euo pipefail

echo "🔧 Initializing Drasi Server Building Comfort tutorial environment..."

# Resolve the tutorial directory from this script's location so the script works
# regardless of the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TUTORIAL_DIR="$REPO_ROOT/tutorials/building-comfort"

if [ ! -f "$REPO_ROOT/../drasi-server/Cargo.toml" ] || [ ! -f "$REPO_ROOT/../drasi-core/lib/Cargo.toml" ]; then
    echo "Building Comfort requires existing sibling ComputationGraph checkouts of drasi-server and drasi-core."
    echo "This container mounts the parent directory; it does not clone repositories or download release binaries."
    exit 1
fi

echo "Installing local-build dependencies..."
sudo apt-get update
sudo apt-get install -y build-essential cmake clang libclang-dev pkg-config \
    libjq-dev libssl-dev protobuf-compiler python3

echo "Building matching ComputationGraph Server and plugins..."
cd "$TUTORIAL_DIR"
if [ ! -f "$REPO_ROOT/../drasi-core/Cargo.lock" ]; then
    echo "Core's workspace Cargo.lock is required for the locked build."
    echo "From this tutorial directory, run:"
    echo "  RUSTUP_TOOLCHAIN=1.95.0 cargo generate-lockfile --manifest-path ../../../drasi-core/Cargo.toml"
    echo "Then rerun: bash ../../.devcontainer/building-comfort/post-create.sh"
    exit 1
fi
python3 scripts/demo.py build

echo ""
echo "✅ Drasi Server Building Comfort tutorial environment is ready!"
echo "   Next: follow README.md (you are already in tutorials/building-comfort)"
