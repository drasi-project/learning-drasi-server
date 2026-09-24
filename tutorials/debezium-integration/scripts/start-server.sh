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
# Runs Drasi Server with either the HTTP or Kafka Debezium config.
#   bash scripts/start-server.sh http
#   bash scripts/start-server.sh kafka

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$SCRIPT_DIR/.."
REPO_ROOT="$(cd "$TUTORIAL_DIR/../.." && pwd)"
MODE="${1:-http}"

case "$MODE" in
    http)
        CONFIG_FILE="${CONFIG_FILE:-$TUTORIAL_DIR/server-config-http.yaml}"
        ;;
    kafka)
        CONFIG_FILE="${CONFIG_FILE:-$TUTORIAL_DIR/server-config-kafka.yaml}"
        ;;
    *)
        echo "Usage: $0 [http|kafka]"
        exit 1
        ;;
esac

if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

BIN=""
for candidate in "$TUTORIAL_DIR/bin/drasi-server" "$REPO_ROOT/bin/drasi-server" "./bin/drasi-server"; do
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

PLUGINS_DIR="${DRASI_PLUGINS_DIR:-$TUTORIAL_DIR/.drasi-plugins}"
mkdir -p "$PLUGINS_DIR"

echo "=== Drasi Server Debezium Integration ($MODE) ==="
echo "  Binary: $BIN"
echo "  Config: $CONFIG_FILE"
echo "  Plugins: $PLUGINS_DIR"
echo "  API:       http://localhost:${SERVER_PORT:-8380}"
echo "  Dashboard: http://localhost:${DASHBOARD_PORT:-3000}"
if [ "$MODE" = "http" ]; then
    echo "  HTTP CDC:  http://localhost:${HTTP_SOURCE_PORT:-9080}/debezium"
else
    echo "  Kafka:     ${KAFKA_BOOTSTRAP_SERVERS:-127.0.0.1:19092} topic=${KAFKA_TOPIC:-building.changes}"
fi
echo "  API docs:  http://localhost:${SERVER_PORT:-8380}/api/v1/docs/"
echo
echo "Press Ctrl+C to stop the server."
echo "=============================================="
echo

exec "$BIN" --config "$CONFIG_FILE" --plugins-dir "$PLUGINS_DIR"
