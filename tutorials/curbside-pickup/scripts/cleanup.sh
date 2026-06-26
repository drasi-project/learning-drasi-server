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

# Cleanup Script
# Stops Drasi Server and removes the PostgreSQL and SQL Server containers.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATABASE_DIR="$TUTORIAL_DIR/database"
REMOVE_VOLUMES="${1:-}"

echo "=== Drasi Server Curbside Pickup - Cleanup ==="
echo

echo "Stopping Drasi Server processes..."
pkill -f "drasi-server.*curbside" 2>/dev/null || true

if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "Warning: docker-compose not found, skipping container cleanup"
    echo
    echo "=== Cleanup complete! ==="
    exit 0
fi

echo "Stopping database containers..."
cd "$DATABASE_DIR"

if [ "$REMOVE_VOLUMES" = "--volumes" ] || [ "$REMOVE_VOLUMES" = "-v" ]; then
    echo "Removing containers and volumes..."
    $COMPOSE_CMD down -v
else
    echo "Removing containers (keeping volumes)..."
    $COMPOSE_CMD down
fi

echo
echo "=== Cleanup complete! ==="
echo
echo "Options:"
echo "  $0           # Stop containers, keep data volumes"
echo "  $0 --volumes # Stop containers and remove data volumes"
