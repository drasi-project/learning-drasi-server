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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$TUTORIAL_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$TUTORIAL_DIR/.env"
    set +a
fi

MYSQL_ROOT_PW="${MYSQL_ROOT_PASSWORD:-root_admin}"
MYSQL_DB="${MYSQL_DATABASE:-PhysicalOperations}"

echo "Resetting orders to 'preparing' (PostgreSQL)..."
docker exec curbside-pickup-postgres \
    psql -v ON_ERROR_STOP=1 -U drasi_user -d RetailOperations \
    -c "UPDATE orders SET status='preparing';"

echo "Resetting vehicles to 'Parking' (MySQL)..."
docker exec -e MYSQL_PWD="$MYSQL_ROOT_PW" curbside-pickup-mysql mysql -uroot -e \
    "UPDATE ${MYSQL_DB}.vehicles SET location='Parking';"

echo
echo "Reset complete. Both dashboards should now be empty."
