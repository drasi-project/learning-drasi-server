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

# Reset Script
# Returns the demo to its starting state: every order back to 'preparing' and
# every vehicle back to 'Parking'. The dashboards clear and you can run through
# the scenario again.

set -e

# Stop Git Bash (MSYS) from rewriting container-absolute paths passed to
# `docker exec`. Harmless on Linux/macOS.
export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

SA_PASSWORD="${MSSQL_SA_PASSWORD:-Drasi_Passw0rd!}"
SQLCMD="/opt/mssql-tools18/bin/sqlcmd"
NOW_MS="$(($(date +%s) * 1000))"

echo "Resetting orders to 'preparing' (PostgreSQL)..."
docker exec curbside-pickup-postgres \
    psql -v ON_ERROR_STOP=1 -U drasi_user -d RetailOperations \
    -c "UPDATE orders SET status='preparing', updated_at=$NOW_MS;"

echo "Resetting vehicles to 'Parking' (SQL Server)..."
docker exec curbside-pickup-mssql "$SQLCMD" -S localhost -U sa -P "$SA_PASSWORD" -C -b \
    -Q "UPDATE PhysicalOperations.dbo.vehicles SET location='Parking', updated_at=$NOW_MS;"

echo
echo "Reset complete. Both dashboards should now be empty."
