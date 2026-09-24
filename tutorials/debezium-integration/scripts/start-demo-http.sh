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

# Path 1 demo: PostgreSQL → Drasi HTTP source → Debezium Server snapshot/stream.
#
# Disposable lab only. Start the listener before attempting snapshot delivery:
#   1. Starts PostgreSQL + seed data
#   2. Starts Drasi Server (HTTP webhook on :9080)
#   3. Waits for the webhook health endpoint
#   4. Starts Debezium Server with a fresh offset volume (re-snapshot)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$SCRIPT_DIR/.."
REPO_ROOT="$(cd "$TUTORIAL_DIR/../.." && pwd)"

# 1. Postgres only — Debezium starts later, after Drasi is ready.
bash "$SCRIPT_DIR/setup-database.sh"

# Resolve drasi-server binary the same way start-server.sh does.
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
        echo "Error: drasi-server binary not found. Run ./scripts/download.sh first."
        exit 1
    fi
fi

if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

PLUGINS_DIR="${DRASI_PLUGINS_DIR:-$TUTORIAL_DIR/.drasi-plugins}"
mkdir -p "$PLUGINS_DIR"
CONFIG_FILE="${CONFIG_FILE:-$TUTORIAL_DIR/server-config-http.yaml}"
HTTP_PORT="${HTTP_SOURCE_PORT:-9080}"
SERVER_PORT="${SERVER_PORT:-8380}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"

mkdir -p "$TUTORIAL_DIR/data"
LOG_FILE="${DRASI_LOG_FILE:-$TUTORIAL_DIR/data/drasi-http.log}"
DRASI_PID=""
TAIL_PID=""

cleanup() {
    if [ -n "$TAIL_PID" ]; then
        kill "$TAIL_PID" 2>/dev/null || true
    fi
    if [ -n "$DRASI_PID" ]; then
        kill "$DRASI_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo
echo "=== Starting Drasi Server (HTTP source) in the background ==="
echo "  Config:     $CONFIG_FILE"
echo "  API:        http://localhost:${SERVER_PORT}"
echo "  Dashboard:  http://localhost:${DASHBOARD_PORT}"
echo "  HTTP CDC:   http://localhost:${HTTP_PORT}/debezium"
echo "  Log file:   $LOG_FILE"
echo

"$BIN" --config "$CONFIG_FILE" --plugins-dir "$PLUGINS_DIR" >"$LOG_FILE" 2>&1 &
DRASI_PID=$!

echo "Waiting for HTTP source health on :${HTTP_PORT} ..."
READY=0
for i in $(seq 1 90); do
    if ! ps -p "$DRASI_PID" >/dev/null 2>&1; then
        echo "Error: Drasi Server exited early. Last log lines:"
        tail -n 40 "$LOG_FILE" || true
        exit 1
    fi
    if curl -sf "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "Error: timed out waiting for HTTP source. Last log lines:"
    tail -n 40 "$LOG_FILE" || true
    exit 1
fi
echo "HTTP source is healthy."

# 3. Start Debezium only after Drasi can accept the snapshot.
bash "$SCRIPT_DIR/start-debezium-server.sh" --reset-offsets

echo
echo "Debezium is snapshotting into Drasi. Follow either:"
echo "  tail -f $LOG_FILE"
echo "  docker logs -f debezium-integration-server"
echo
echo "Dashboard: http://localhost:${DASHBOARD_PORT}"
echo "Then drive a change with: bash scripts/break-room.sh room_01_01_01"
echo
echo "Streaming Drasi logs (Ctrl+C stops Drasi and exits)..."
echo "=============================================="
tail -n +1 -f "$LOG_FILE" &
TAIL_PID=$!
wait "$DRASI_PID"
