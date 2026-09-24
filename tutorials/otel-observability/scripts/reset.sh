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

# Reset Script
# Returns the demo to its starting state: checkout v41, latency 400, heartbeat
# on, SLO threshold 750.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Resetting checkout to v41..."
bash "$SCRIPT_DIR/roll-checkout.sh" v41

echo
echo "Restoring healthy latency and heartbeat..."
bash "$SCRIPT_DIR/set-latency.sh" 400
bash "$SCRIPT_DIR/start-heartbeat.sh"

echo
echo "Restoring the default SLO threshold..."
bash "$SCRIPT_DIR/set-slo.sh" 750

echo
echo "Reset complete. Checkout should be v41 at 400ms with a 750ms SLO."
