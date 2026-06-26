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
# Starts PostgreSQL (Retail Operations / orders) and SQL Server (Physical
# Operations / vehicles), both with change data capture enabled, and seeds them.

set -e

# Stop Git Bash (MSYS) from rewriting container-absolute paths like
# /opt/mssql-tools18/bin/sqlcmd when they are passed to `docker exec`. This is a
# harmless no-op on Linux/macOS.
export MSYS_NO_PATHCONV=1

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

SA_PASSWORD="${MSSQL_SA_PASSWORD:-Drasi_Passw0rd!}"
SQLCMD="/opt/mssql-tools18/bin/sqlcmd"

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

echo "Starting PostgreSQL and SQL Server..."
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

# --- SQL Server ------------------------------------------------------------
echo
echo "Waiting for SQL Server to be ready..."
MAX_RETRIES=40
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker exec curbside-pickup-mssql "$SQLCMD" -S localhost -U sa -P "$SA_PASSWORD" -C -Q "SELECT 1" &> /dev/null; then
        echo "SQL Server is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 3
done
if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Error: SQL Server failed to start within the timeout"
    echo "Check logs with: docker logs curbside-pickup-mssql"
    exit 1
fi

echo "Applying Physical Operations schema, seed data, and enabling CDC..."
# Pipe the script over stdin so this works under docker-outside-of-docker.
docker exec -i curbside-pickup-mssql "$SQLCMD" -S localhost -U sa -P "$SA_PASSWORD" -C -b < "$DATABASE_DIR/mssql-init.sql"

# --- Verify ----------------------------------------------------------------
echo
echo "Seeded orders (PostgreSQL):"
docker exec curbside-pickup-postgres psql -U drasi_user -d RetailOperations -c \
    "SELECT id, customer_name, plate, status FROM orders ORDER BY id;"

echo
echo "Seeded vehicles (SQL Server):"
docker exec curbside-pickup-mssql "$SQLCMD" -S localhost -U sa -P "$SA_PASSWORD" -C -Q \
    "SET NOCOUNT ON; SELECT plate, customer_name, location FROM PhysicalOperations.dbo.vehicles ORDER BY plate;"

echo
echo "=== Database setup complete! ==="
echo
echo "  PostgreSQL: localhost:${POSTGRES_HOST_PORT:-5742}  (db RetailOperations)"
echo "  SQL Server: localhost:${MSSQL_HOST_PORT:-1435}  (db PhysicalOperations)"
echo
echo "Next step: run ./scripts/start-server.sh to start Drasi Server"
