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

# Simulate Script
# Hands-free demo driver: every few seconds it picks a random room and assigns
# new random sensor readings, so the dashboard stays alive without any manual
# input. Some readings land inside the comfortable band (40-50) and some fall
# outside it, exercising the alert queries. Press Ctrl+C to stop.

set -e

CONTAINER="${POSTGRES_CONTAINER:-building-comfort-postgres}"
DB="${POSTGRES_DATABASE:-building_comfort}"
DB_USER="${POSTGRES_USER:-drasi_user}"
INTERVAL="${1:-3}"

if ! docker ps 2>/dev/null | grep -q "$CONTAINER"; then
    echo "Error: the $CONTAINER container is not running."
    echo "Run ./scripts/setup-database.sh first."
    exit 1
fi

# Pull the live list of room ids from the database.
mapfile -t ROOMS < <(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -tAc 'SELECT id FROM "Room" ORDER BY id;')

if [ "${#ROOMS[@]}" -eq 0 ]; then
    echo "Error: no rooms found. Did the database seed correctly?"
    exit 1
fi

echo "Simulating sensor changes every ${INTERVAL}s across ${#ROOMS[@]} rooms."
echo "Watch the dashboard at http://localhost:${DASHBOARD_PORT:-3000}. Press Ctrl+C to stop."
echo

cleanup() { echo; echo "Simulation stopped."; exit 0; }
trap cleanup INT TERM

while true; do
    ROOM="${ROOMS[$((RANDOM % ${#ROOMS[@]}))]}"
    # Ranges chosen to straddle the comfortable band so alerts come and go.
    TEMPERATURE=$((RANDOM % 31 + 55))   # 55 - 85
    HUMIDITY=$((RANDOM % 36 + 20))      # 20 - 55
    CO2=$((RANDOM % 900 + 5))           # 5 - 904

    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -qtAc \
        "UPDATE \"Room\" SET temperature=$TEMPERATURE, humidity=$HUMIDITY, co2=$CO2 WHERE id='$ROOM';" >/dev/null

    echo "$(date '+%H:%M:%S')  $ROOM -> temp=$TEMPERATURE humidity=$HUMIDITY co2=$CO2"
    sleep "$INTERVAL"
done
