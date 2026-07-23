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

# Reset Room Script
# Resets a room (or every room when no id is given) to the comfortable defaults
# temperature=70, humidity=40, co2=10. Mirrors the "Reset" button from the
# original tutorial.

set -e

CONTAINER="${POSTGRES_CONTAINER:-building-comfort-postgres}"
DB="${POSTGRES_DATABASE:-building_comfort}"
DB_USER="${POSTGRES_USER:-drasi_user}"

ROOM_ID="${1:-}"

# Fail fast if the database container isn't running.
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Error: the ${CONTAINER} container is not running."
    echo "Run ./scripts/setup-database.sh first."
    exit 1
fi

# When a specific room is given, validate it (letters, digits, and underscores)
# so a malformed value can't produce a confusing SQL error or inject SQL.
if [ -n "$ROOM_ID" ] && ! printf '%s' "$ROOM_ID" | grep -Eq '^[A-Za-z0-9_]+$'; then
    echo "Error: invalid room id '$ROOM_ID' (expected letters, digits, and underscores)."
    exit 1
fi

if [ -z "$ROOM_ID" ]; then
    echo "Resetting ALL rooms -> temperature=70 humidity=40 co2=10"
    # Drasi's PostgreSQL source propagates one row-change per transaction, so a
    # single multi-row "UPDATE \"Room\" SET ..." would only reach Drasi for one
    # room and the dashboard would not fully reset. Update each room in its own
    # statement/transaction so every change is captured.
    ROOM_IDS=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -tAc \
        'SELECT id FROM "Room" ORDER BY id;')
    COUNT=0
    for id in $ROOM_IDS; do
        docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -c \
            "UPDATE \"Room\" SET temperature=70, humidity=40, co2=10 WHERE id='$id';" \
            >/dev/null
        echo "  reset $id"
        COUNT=$((COUNT + 1))
    done
    echo "Reset $COUNT room(s)."
else
    echo "Resetting $ROOM_ID -> temperature=70 humidity=40 co2=10"
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB" -c \
        "UPDATE \"Room\" SET temperature=70, humidity=40, co2=10 WHERE id='$ROOM_ID' RETURNING id, name, temperature, humidity, co2;"
fi

echo
echo "Done. The dashboard at http://localhost:${DASHBOARD_PORT:-3000} should return to green."
