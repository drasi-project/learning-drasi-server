#!/bin/bash
# Copyright 2026 The Drasi Authors. Licensed under Apache-2.0.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE="$(cd "$REPO_ROOT/.." && pwd)"

if [ ! -f "$WORKSPACE/drasi-server/Cargo.toml" ] || [ ! -f "$WORKSPACE/drasi-core/Cargo.toml" ]; then
    echo "Existing sibling drasi-server/ and drasi-core/ checkouts are required." >&2
    echo "No clone, released binary, or plugin-registry fallback is performed." >&2
    exit 1
fi

missing=()
for package in build-essential pkg-config libssl-dev protobuf-compiler libclang-dev cmake python3 podman podman-compose; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
        missing+=("$package")
    fi
done
if [ "${#missing[@]}" -gt 0 ]; then
    sudo apt-get update -qq
    sudo apt-get install -y "${missing[@]}"
fi

cd "$REPO_ROOT/tutorials/curbside-pickup"
if ! (cd webui && node --input-type=module -e \
    "await Promise.all(['express','dotenv','pg','mysql2/promise'].map(x => import(x)))"); then
    (cd webui && npm ci --no-fund --no-audit)
fi
python3 scripts/demo.py build
echo "Local Server and all five matching plugins built. Run bash scripts/start-demo.sh."
