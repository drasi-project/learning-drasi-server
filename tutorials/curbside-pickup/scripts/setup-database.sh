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
# Starts PostgreSQL (Retail Operations / orders) and MySQL (Physical
# Operations / vehicles), both with change data capture enabled, and seeds them.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATABASE_DIR="$TUTORIAL_DIR/database"

# Load tutorial environment defaults if a .env file is present.
if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

MYSQL_ROOT_PW="${MYSQL_ROOT_PASSWORD:-root_admin}"
MYSQL_DB="${MYSQL_DATABASE:-PhysicalOperations}"

echo "=== Drasi Server Curbside Pickup - Database Setup ==="
echo

if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "Error: Docker daemon is not running"
    echo "Please start Docker and try again"
    exit 1
fi

if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "Error: docker-compose is not installed"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "Using: $COMPOSE_CMD"
echo

echo "Stopping any existing database containers..."
cd "$DATABASE_DIR"
$COMPOSE_CMD down -v 2>/dev/null || true

echo "Starting PostgreSQL and MySQL..."
$COMPOSE_CMD up -d

# --- PostgreSQL ------------------------------------------------------------
echo
echo "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Probe over TCP (-h localhost), not the Unix socket, to avoid the postgres
    # image's first-init temporary-server race.
    if docker exec curbside-pickup-postgres pg_isready -h localhost -U postgres -d RetailOperations &> /dev/null; then
        echo "PostgreSQL is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Error: PostgreSQL failed to start within the timeout"
    echo "Check logs with: docker logs curbside-pickup-postgres"
    exit 1
fi

echo "Applying Retail Operations schema and seed data..."
docker exec -i curbside-pickup-postgres \
    psql -v ON_ERROR_STOP=1 -U postgres -d RetailOperations < "$DATABASE_DIR/postgres-init.sql"

# --- MySQL -----------------------------------------------------------------
echo
echo "Waiting for MySQL to be ready..."
MAX_RETRIES=40
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Authenticate over TCP against the target database. MySQL's first-init
    # temporary server runs with --skip-networking (socket only), so a TCP
    # connection only succeeds once the real server is up with the configured
    # root password and MYSQL_DATABASE created - avoiding a cold-init race that
    # a plain `mysqladmin ping` (which passes even on auth failure) would miss.
    if docker exec -e MYSQL_PWD="$MYSQL_ROOT_PW" curbside-pickup-mysql mysql -h 127.0.0.1 -uroot -e "USE ${MYSQL_DB}" &> /dev/null; then
        echo "MySQL is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 3
done
if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Error: MySQL failed to start within the timeout"
    echo "Check logs with: docker logs curbside-pickup-mysql"
    exit 1
fi

echo "Applying Physical Operations schema, seed data, and replication grants..."
docker exec -i -e MYSQL_PWD="$MYSQL_ROOT_PW" curbside-pickup-mysql mysql -uroot < "$DATABASE_DIR/mysql-init.sql"

# --- Verify ----------------------------------------------------------------
echo
echo "Seeded orders (PostgreSQL):"
docker exec curbside-pickup-postgres psql -U drasi_user -d RetailOperations -c \
    "SELECT id, customer_name, plate, status FROM orders ORDER BY id;"

echo
echo "Seeded vehicles (MySQL):"
docker exec -e MYSQL_PWD="$MYSQL_ROOT_PW" curbside-pickup-mysql mysql -uroot -e \
    "SELECT plate, customer_name, location FROM ${MYSQL_DB}.vehicles ORDER BY plate;"

echo
echo "=== Database setup complete! ==="
echo
echo "  PostgreSQL: localhost:${POSTGRES_HOST_PORT:-5742}  (db RetailOperations)"
echo "  MySQL:      localhost:${MYSQL_HOST_PORT:-3309}  (db PhysicalOperations)"
echo
echo "Next step: run ./scripts/start-server.sh to start Drasi Server"
