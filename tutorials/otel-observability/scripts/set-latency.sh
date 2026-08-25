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

# Set Latency Script
# POSTs a new p99 gauge value to the checkout mock's control API.

set -e

VALUE="${1:-}"
CHECKOUT_URL="${CHECKOUT_URL:-http://127.0.0.1:${CHECKOUT_CONTROL_PORT:-18080}}"

if [ -z "$VALUE" ] || ! printf '%s' "$VALUE" | grep -Eq '^[0-9]+([.][0-9]+)?$'; then
    echo "Usage: $0 <latency_ms>"
    echo
    echo "Examples:"
    echo "  $0 920    # above the 750ms SLO — alert fires after 5s"
    echo "  $0 700    # recover (below threshold)"
    echo "  $0 400    # healthy baseline"
    exit 1
fi

echo "Setting checkout work delay to ${VALUE}ms via $CHECKOUT_URL"
curl -fsS -X POST "$CHECKOUT_URL/delay/$VALUE"
echo
echo
echo "Done. Watch the dashboard at http://localhost:${DASHBOARD_PORT:-3000}"
