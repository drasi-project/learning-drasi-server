#!/bin/bash
# Copyright 2026 The Drasi Authors.
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
# Runs the downloaded Drasi Server binary with the OTel Observability config.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TUTORIAL_DIR/../.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$TUTORIAL_DIR/server-config.yaml}"

if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

cd "$TUTORIAL_DIR"

PLATFORM_DIR="$TUTORIAL_DIR/bin/$(uname -s)-$(uname -m)"
BIN="$PLATFORM_DIR/drasi-server"
if [ ! -x "$BIN" ] || ! "$BIN" --version >/dev/null 2>&1; then
    echo "Drasi Server for $(uname -s)-$(uname -m) is missing or not executable."
    echo "Downloading it now..."
    bash "$SCRIPT_DIR/download.sh"
fi
if [ ! -x "$BIN" ]; then
    echo "Error: drasi-server binary not found at $BIN"
    echo "Run ./scripts/download.sh first (or download.ps1 on Windows)."
    exit 1
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

PLUGINS_DIR="${DRASI_PLUGINS_DIR:-$PLATFORM_DIR/plugins}"
mkdir -p "$PLUGINS_DIR"

# source/otel is not on the public registry yet. Build it from drasi-core PR 750
# into PLUGINS_DIR (no-op if the cdylib is already there).
bash "$SCRIPT_DIR/install-otel-plugin.sh"

if ! docker ps 2>/dev/null | grep -q otel-observability-postgres; then
    echo "Warning: the otel-observability-postgres container is not running."
    echo "Run ./scripts/setup-database.sh first."
    echo
fi

echo "=== Drasi Server OTel Observability ==="
echo "  Binary: $BIN"
echo "  Config: $CONFIG_FILE"
echo "  Kubeconfig: $TUTORIAL_DIR/bin/kubeconfig.yaml"
echo "  Plugins: $PLUGINS_DIR"
echo "  API:       http://localhost:${SERVER_PORT:-8380}"
echo "  Dashboard: http://localhost:${DASHBOARD_PORT:-3000}"
echo "  OTLP:      ${OTEL_GRPC_BIND:-0.0.0.0:14317}"
echo "  API docs:  http://localhost:${SERVER_PORT:-8380}/api/v1/docs/"
echo
echo "Press Ctrl+C to stop the server."
echo "=============================================="
echo

# The in-cluster Collector backs off while Drasi is down. Restart it now so
# the first export after listen is immediate instead of 30s later.
KUBECONFIG_FILE="$TUTORIAL_DIR/bin/kubeconfig.yaml"
if [ -f "$KUBECONFIG_FILE" ] && command -v kubectl >/dev/null 2>&1; then
    if kubectl --kubeconfig "$KUBECONFIG_FILE" get deploy otel-collector >/dev/null 2>&1; then
        echo "Restarting the OTel Collector so it reconnects immediately..."
        kubectl --kubeconfig "$KUBECONFIG_FILE" rollout restart deploy/otel-collector >/dev/null
    fi
fi

exec "$BIN" --config "$CONFIG_FILE" --plugins-dir "$PLUGINS_DIR"
