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
    libjq-dev libonig-dev libssl-dev protobuf-compiler python3

# Debian's libjq-dev does not provide the pkg-config metadata used by jq-sys.
if [ -z "${JQ_LIB_DIR:-}" ]; then
    JQ_LIB_DIR="/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
fi
export JQ_LIB_DIR

cd "$TUTORIAL_DIR"
if [ ! -f "$REPO_ROOT/../drasi-core/Cargo.lock" ]; then
    echo "Generating Core's missing workspace Cargo.lock..."
    cargo generate-lockfile --manifest-path "$REPO_ROOT/../drasi-core/Cargo.toml"
fi

echo "Synchronizing Server's workspace Cargo.lock with the local Core checkout..."
cargo update --manifest-path "$REPO_ROOT/../drasi-server/Cargo.toml" --workspace

echo "Building matching ComputationGraph Server and plugins..."
python3 scripts/demo.py build

echo ""
echo "✅ Drasi Server Building Comfort tutorial environment is ready!"
echo "   Next: follow README.md (you are already in tutorials/building-comfort)"
