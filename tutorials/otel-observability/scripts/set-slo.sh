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

# Set SLO Script
# Updates checkout's latency_p99_ms threshold in PostgreSQL.

set -e

CONTAINER="${POSTGRES_CONTAINER:-otel-observability-postgres}"
DB="${POSTGRES_DATABASE:-otel_observability}"
DB_USER="${POSTGRES_USER:-drasi_user}"
THRESHOLD="${1:-}"

if [ -z "$THRESHOLD" ] || ! printf '%s' "$THRESHOLD" | grep -Eq '^[0-9]+([.][0-9]+)?$'; then
    echo "Usage: $0 <threshold_ms>"
    echo
    echo "Examples:"
    echo "  $0 1000   # raise the SLO — an active alert resolves immediately"
    echo "  $0 750    # restore the default policy"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Error: the ${CONTAINER} container is not running."
    echo "Run ./scripts/setup-database.sh first."
    exit 1
fi

echo "Setting checkout latency_p99_ms threshold to $THRESHOLD"

docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -c \
    "UPDATE service_slo_policy SET threshold_ms = $THRESHOLD WHERE service_name = 'checkout' AND metric_name = 'latency_p99_ms' RETURNING service_name, metric_name, threshold_ms;"

echo
echo "Done. Watch the dashboard at http://localhost:${DASHBOARD_PORT:-3000}"
