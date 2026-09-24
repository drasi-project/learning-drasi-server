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

# Setup Database Script
# Starts PostgreSQL (and optional Debezium profile services) and seeds the
# Building Comfort hierarchy. Usage:
#   bash scripts/setup-database.sh           # postgres only (recommended before Path 1)
#   bash scripts/setup-database.sh http      # postgres + Debezium Server
#                                           # Prefer start-demo-http.sh / start-debezium-server.sh
#                                           # so Drasi is listening before the snapshot.
#   bash scripts/setup-database.sh kafka     # postgres + Kafka + Connect

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE_DIR="$SCRIPT_DIR/../database"
PROFILE="${1:-}"

echo "=== Drasi Server Debezium Integration - Database Setup ==="
echo

if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "Error: Docker daemon is not running"
    exit 1
fi

if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "Error: docker compose is not installed"
    exit 1
fi

echo "Using: $COMPOSE_CMD"
echo

cd "$DATABASE_DIR"

echo "Stopping any existing tutorial containers..."
$COMPOSE_CMD --profile http --profile kafka down -v 2>/dev/null || true

COMPOSE_ARGS=(up -d)
if [ -n "$PROFILE" ]; then
    echo "Starting stack with profile: $PROFILE"
    COMPOSE_ARGS=(--profile "$PROFILE" up -d)
else
    echo "Starting PostgreSQL only..."
fi

$COMPOSE_CMD "${COMPOSE_ARGS[@]}"

echo "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker exec debezium-integration-postgres pg_isready -h localhost -U postgres -d building_comfort &> /dev/null; then
        echo "PostgreSQL is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Error: PostgreSQL failed to start within the timeout"
    echo "Check logs with: docker logs debezium-integration-postgres"
    exit 1
fi

echo "Applying schema and seed data..."
docker exec -i debezium-integration-postgres \
    psql -v ON_ERROR_STOP=1 -U postgres -d building_comfort < "$DATABASE_DIR/init.sql"

echo
echo "Seeded rooms:"
docker exec debezium-integration-postgres psql -U drasi_user -d building_comfort -c \
    "SELECT id, name, temperature, humidity, co2, floor_id FROM \"Room\" ORDER BY id;"

if [ "$PROFILE" = "kafka" ]; then
    echo
    echo "Waiting for Kafka Connect REST API..."
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt 40 ]; do
        if curl -sf "http://localhost:${CONNECT_HOST_PORT:-8083}/connectors" >/dev/null 2>&1; then
            echo "Kafka Connect is ready!"
            break
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "  Waiting for Connect... ($RETRY_COUNT/40)"
        sleep 3
    done
    if [ $RETRY_COUNT -eq 40 ]; then
        echo "Error: Kafka Connect did not become ready"
        echo "Check logs with: docker logs debezium-integration-connect"
        exit 1
    fi

    echo "Registering Debezium PostgreSQL connector..."
    # Delete any previous registration so re-runs are idempotent.
    curl -sf -X DELETE "http://localhost:${CONNECT_HOST_PORT:-8083}/connectors/building-comfort-connector" >/dev/null 2>&1 || true
    sleep 1
    curl -sf -X POST "http://localhost:${CONNECT_HOST_PORT:-8083}/connectors" \
        -H "Content-Type: application/json" \
        --data @"$DATABASE_DIR/connect/register-postgres.json"
    echo
    echo "Connector status:"
    sleep 3
    curl -sf "http://localhost:${CONNECT_HOST_PORT:-8083}/connectors/building-comfort-connector/status" || true
    echo
fi

echo
echo "=== Database setup complete! ==="
echo
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: ${POSTGRES_HOST_PORT:-5752}"
echo "  Database: building_comfort"
echo "  User: drasi_user"
echo "  Password: drasi_password"
if [ "$PROFILE" = "http" ]; then
    echo "  Debezium Server: running (HTTP sink → host port ${HTTP_SOURCE_PORT:-9080})"
    echo
    echo "Note: Debezium should only snapshot after Drasi's HTTP source is up."
    echo "Prefer: bash scripts/start-demo-http.sh"
    echo "Or:     bash scripts/start-server.sh http   # terminal 1"
    echo "        bash scripts/start-debezium-server.sh --reset-offsets  # terminal 2"
elif [ "$PROFILE" = "kafka" ]; then
    echo "  Kafka (host): localhost:${KAFKA_HOST_PORT:-19092}"
    echo "  Connect REST: http://localhost:${CONNECT_HOST_PORT:-8083}"
fi
