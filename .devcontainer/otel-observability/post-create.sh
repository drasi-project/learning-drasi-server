#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TUTORIAL_DIR="$REPO_ROOT/tutorials/otel-observability"

if [ ! -f "$REPO_ROOT/../drasi-server/Cargo.toml" ] || [ ! -f "$REPO_ROOT/../drasi-core/lib/Cargo.toml" ]; then
    echo "OTel Observability requires existing sibling drasi-server and drasi-core checkouts."
    echo "Open the local parent-mounted dev container; no release download or clone fallback is used."
    exit 1
fi

sudo apt-get update
sudo apt-get install -y build-essential cmake clang libclang-dev pkg-config \
    libjq-dev libssl-dev protobuf-compiler python3 curl postgresql-client

if ! command -v k3d >/dev/null 2>&1; then
    case "$(uname -m)" in
        x86_64) ARCH=amd64 ;;
        aarch64|arm64) ARCH=arm64 ;;
        *) echo "Unsupported k3d architecture"; exit 1 ;;
    esac
    DOWNLOAD="$(mktemp -d)"
    curl -fsSL "https://github.com/k3d-io/k3d/releases/download/v5.8.3/checksums.txt" -o "$DOWNLOAD/checksums.txt"
    curl -fsSL "https://github.com/k3d-io/k3d/releases/download/v5.8.3/k3d-linux-$ARCH" -o "$DOWNLOAD/k3d-linux-$ARCH"
    (
        cd "$DOWNLOAD"
        grep "_dist/k3d-linux-$ARCH$" checksums.txt | sed 's@_dist/@@' | sha256sum -c -
    )
    sudo install -m 755 "$DOWNLOAD/k3d-linux-$ARCH" /usr/local/bin/k3d
    rm "$DOWNLOAD/checksums.txt" "$DOWNLOAD/k3d-linux-$ARCH"
    rmdir "$DOWNLOAD"
fi

cd "$TUTORIAL_DIR"
python3 scripts/demo.py build
echo "Local Server and matching plugins built. Follow README.md to start the store scenario."
