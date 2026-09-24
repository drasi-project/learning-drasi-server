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

# Cleanup Script
# Stops Drasi Server, removes the PostgreSQL container, and deletes the k3d cluster.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATABASE_DIR="$TUTORIAL_DIR/database"
CLUSTER_NAME="${K3D_CLUSTER_NAME:-otel-observability}"
REMOVE_VOLUMES="${1:-}"

echo "=== Drasi Server OTel Observability - Cleanup ==="
echo

echo "Stopping Drasi Server processes..."
pkill -f "drasi-server.*otel-observability" 2>/dev/null || true

if command -v k3d &> /dev/null; then
    if k3d cluster list 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
        echo "Deleting k3d cluster '$CLUSTER_NAME'..."
        k3d cluster delete "$CLUSTER_NAME"
    fi
else
    echo "Warning: k3d not found, skipping cluster cleanup"
fi

rm -f "$TUTORIAL_DIR/bin/kubeconfig.yaml"

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

echo "Stopping PostgreSQL container..."
cd "$DATABASE_DIR"

if [ "$REMOVE_VOLUMES" = "--volumes" ] || [ "$REMOVE_VOLUMES" = "-v" ]; then
    echo "Removing container and volumes..."
    $COMPOSE_CMD down -v
else
    echo "Removing container (keeping volumes)..."
    $COMPOSE_CMD down
fi

echo
echo "=== Cleanup complete! ==="
echo
echo "Options:"
echo "  $0           # Stop containers + cluster, keep data volumes"
echo "  $0 --volumes # Stop containers + cluster and remove data volumes"
