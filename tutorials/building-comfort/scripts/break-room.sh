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

# Break Room Script
# Pushes a room to deliberately uncomfortable values (temperature=40,
# humidity=20, co2=700) so its comfort level drops out of the 40-50 band and
# alerts fire. Mirrors the "Break" button from the original tutorial.

set -e

CONTAINER="${POSTGRES_CONTAINER:-building-comfort-postgres}"
DB="${POSTGRES_DATABASE:-building_comfort}"
DB_USER="${POSTGRES_USER:-drasi_user}"

ROOM_ID="${1:-}"

if [ -z "$ROOM_ID" ]; then
    echo "Usage: $0 <room_id>"
    echo
    echo "Example:"
    echo "  $0 room_01_01_01"
    echo
    echo "Room ids: room_01_<floor>_<room>, floors 01-03, rooms 01-03"
    exit 1
fi

# Validate the room id (letters, digits, and underscores) so a malformed value
# can't produce a confusing SQL error or be used to inject SQL.
if ! printf '%s' "$ROOM_ID" | grep -Eq '^[A-Za-z0-9_]+$'; then
    echo "Error: invalid room id '$ROOM_ID' (expected letters, digits, and underscores)."
    exit 1
fi

# Fail fast if the database container isn't running.
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Error: the ${CONTAINER} container is not running."
    echo "Run ./scripts/setup-database.sh first."
    exit 1
fi

echo "Breaking $ROOM_ID -> temperature=40 humidity=20 co2=700"

docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -c \
    "UPDATE \"Room\" SET temperature=40, humidity=20, co2=700 WHERE id='$ROOM_ID' RETURNING id, name, temperature, humidity, co2;"

echo
echo "Done. Watch the room turn red on the dashboard at http://localhost:${DASHBOARD_PORT:-3000}"
