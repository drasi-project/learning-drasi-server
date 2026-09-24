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

# Start (or restart) Debezium Server after Drasi's HTTP source is listening.
# Optionally wipe the offset volume so the initial snapshot is re-sent.
#
#   bash scripts/start-debezium-server.sh
#   bash scripts/start-debezium-server.sh --reset-offsets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE_DIR="$SCRIPT_DIR/../database"
RESET_OFFSETS=0

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
if ! curl -sf "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
    echo "Error: Drasi HTTP source is not reachable at http://127.0.0.1:${HTTP_PORT}/health"
    echo "Start Drasi first (bash scripts/start-server.sh http), then re-run this script."
    exit 1
fi
echo "HTTP source is up."

if [ "$RESET_OFFSETS" -eq 1 ]; then
    echo "Resetting Debezium Server offsets so the next start re-snapshots..."
    $COMPOSE_CMD --profile http stop debezium-server >/dev/null 2>&1 || true
    $COMPOSE_CMD --profile http rm -f debezium-server >/dev/null 2>&1 || true
    docker volume rm debezium-integration_debezium_server_data >/dev/null 2>&1 || true
fi

echo "Starting Debezium Server (HTTP sink → host:${HTTP_PORT}/debezium)..."
$COMPOSE_CMD --profile http up -d debezium-server

echo "Waiting for Debezium Server container..."
for i in $(seq 1 30); do
    if docker ps --filter name=debezium-integration-server --format '{{.Status}}' | grep -q Up; then
        echo "Debezium Server is up."
        break
    fi
    sleep 1
done

echo
echo "Tip: follow snapshot/stream logs with:"
echo "  docker logs -f debezium-integration-server"
