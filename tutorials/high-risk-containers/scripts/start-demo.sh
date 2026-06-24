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

# Start Demo Script
# One command to run the whole High Risk Containers demo: create the Kubernetes
# cluster (with the demo Pods), start (and seed) the database, then run Drasi
# Server with the full configuration in the foreground. Open
# http://localhost:3000 once it is running, and use the add-risky-image /
# upgrade-pod scripts from a second terminal to drive changes. Press Ctrl+C to
# stop the server, then run ./scripts/cleanup.sh.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/setup-cluster.sh"

echo
bash "$SCRIPT_DIR/setup-database.sh"

echo
exec bash "$SCRIPT_DIR/start-server.sh"
