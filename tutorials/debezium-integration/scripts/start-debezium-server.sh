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

# Disposable lab only: start Debezium Server after Drasi is listening.
# Optionally wipe the lab offset volume so the initial snapshot is re-sent.
#
#   bash scripts/start-debezium-server.sh
#   bash scripts/start-debezium-server.sh --reset-offsets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE_DIR="$SCRIPT_DIR/../database"
RESET_OFFSETS=0

if [ -f "$SCRIPT_DIR/../.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$SCRIPT_DIR/../.env"
    set +a
fi

for arg in "$@"; do
    case "$arg" in
        --reset-offsets|-r)
            RESET_OFFSETS=1
            ;;
        -h|--help)
            echo "Usage: $0 [--reset-offsets]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--reset-offsets]"
            exit 1
            ;;
    esac
done

if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "Error: docker compose is not installed"
    exit 1
fi

cd "$DATABASE_DIR"

HTTP_PORT="${HTTP_SOURCE_PORT:-9080}"
echo "Checking Drasi HTTP source on localhost:${HTTP_PORT}/health ..."
if ! curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
    echo "Error: Drasi HTTP source is not reachable at http://127.0.0.1:${HTTP_PORT}/health"
    echo "Start Drasi first (bash scripts/start-server.sh http), then re-run this script."
    exit 1
fi
echo "HTTP source is up."

if [ "$RESET_OFFSETS" -eq 1 ]; then
    echo "WARNING: deleting disposable lab offsets so the next start re-snapshots."
    $COMPOSE_CMD --profile http stop debezium-server >/dev/null 2>&1 || true
    $COMPOSE_CMD --profile http rm -f debezium-server >/dev/null 2>&1 || true
    docker volume rm debezium-integration_debezium_server_data >/dev/null 2>&1 || true
fi

echo "Starting Debezium Server (HTTP sink → host:${HTTP_PORT}/debezium)..."
fail_startup() {
    echo "Error: $1" >&2
    echo "Recent Debezium Server logs:" >&2
    if ! $COMPOSE_CMD --profile http logs --no-color --tail 40 debezium-server >&2; then
        echo "Unable to retrieve Debezium Server logs." >&2
    fi
    exit 1
}

if ! $COMPOSE_CMD --profile http up -d debezium-server; then
    fail_startup "Compose could not start Debezium Server."
fi

echo "Waiting for Debezium Server container..."
READY=0
STATE="missing"
for i in $(seq 1 30); do
    if ! CONTAINER_ID=$($COMPOSE_CMD --profile http ps -a -q debezium-server); then
        fail_startup "Could not identify the Compose Debezium Server container."
    fi
    STATE="missing"
    if [ -n "$CONTAINER_ID" ]; then
        if ! STATE=$(docker inspect --format '{{.State.Status}}' "$CONTAINER_ID"); then
            fail_startup "Could not inspect Debezium Server container $CONTAINER_ID."
        fi
        case "$STATE" in
            running)
                READY=1
                break
                ;;
            created|restarting)
                ;;
            *)
                fail_startup "Debezium Server container is $STATE."
                ;;
        esac
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    fail_startup "Timed out waiting for Debezium Server container (last state: $STATE)."
fi
echo "Debezium Server container is running; verify snapshot/streaming in the logs and query results."

echo
echo "Tip: follow snapshot/stream logs with:"
echo "  docker logs -f debezium-integration-server"
