#!/bin/bash
# Copyright 2025 The Drasi Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Start Server Script
# Runs the downloaded Drasi Server binary with the High Risk Containers config.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TUTORIAL_DIR/../.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$TUTORIAL_DIR/server-config.yaml}"

# Load tutorial environment defaults if a .env file is present.
if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

# Run from the tutorial directory so the Kubernetes source resolves the relative
# kubeconfig path (bin/kubeconfig.yaml) against it.
cd "$TUTORIAL_DIR"

# Locate the drasi-server binary downloaded by scripts/download.sh.
BIN=""
for candidate in "$REPO_ROOT/bin/drasi-server" "$TUTORIAL_DIR/bin/drasi-server" "./bin/drasi-server"; do
    if [ -x "$candidate" ]; then
        BIN="$candidate"
        break
    fi
done

if [ -z "$BIN" ]; then
    if command -v drasi-server &> /dev/null; then
        BIN="drasi-server"
    else
        echo "Error: drasi-server binary not found."
        echo "Run ./scripts/download.sh first (or download.ps1 on Windows)."
        exit 1
    fi
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file not found: $CONFIG_FILE"
    exit 1
fi

if [ ! -f "$TUTORIAL_DIR/bin/kubeconfig.yaml" ]; then
    echo "Warning: kubeconfig not found at $TUTORIAL_DIR/bin/kubeconfig.yaml"
    echo "Run ./scripts/setup-cluster.sh first."
    echo
fi

# Plugins are cached outside the bind-mounted workspace, in a user-owned
# directory. The default plugins location is next to the binary (bin/plugins),
# but on a bind mount (dev container / Windows) that path can be owned by
# another user, so writing the plugin lock file fails with "Permission denied".
# A path under $HOME is always writable by the user running the server and
# persists the cache across runs.
PLUGINS_DIR="${DRASI_PLUGINS_DIR:-$HOME/.drasi/plugins}"
mkdir -p "$PLUGINS_DIR"

if ! docker ps 2>/dev/null | grep -q high-risk-containers-postgres; then
    echo "Warning: the high-risk-containers-postgres container is not running."
    echo "Run ./scripts/setup-database.sh first."
    echo
fi

echo "=== Drasi Server High Risk Containers ==="
echo "  Binary: $BIN"
echo "  Config: $CONFIG_FILE"
echo "  Kubeconfig: $TUTORIAL_DIR/bin/kubeconfig.yaml"
echo "  Plugins: $PLUGINS_DIR"
echo "  API:       http://localhost:${SERVER_PORT:-8380}"
echo "  Dashboard: http://localhost:${DASHBOARD_PORT:-3000}"
echo "  API docs:  http://localhost:${SERVER_PORT:-8380}/api/v1/docs/"
echo
echo "Press Ctrl+C to stop the server."
echo "=============================================="
echo

exec "$BIN" --config "$CONFIG_FILE" --plugins-dir "$PLUGINS_DIR"
