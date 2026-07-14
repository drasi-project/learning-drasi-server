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

# Start Web Console Script
# Installs dependencies on first run, then launches the browser-based UI used to
# drive changes against the two databases (orders in PostgreSQL, vehicles in
# MySQL). It is the browser sibling of scripts/start-tui.sh and reuses the same
# tui/src/db.js data-access layer, so it needs the tui dependencies too. Run
# this in a second terminal while start-demo.sh / start-server.sh runs in the
# first, then open http://localhost:3001.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TUI_DIR="$TUTORIAL_DIR/tui"
WEBUI_DIR="$TUTORIAL_DIR/webui"

if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed or not in PATH."
    echo "Install Node.js 18+ from https://nodejs.org/ and try again."
    exit 1
fi

# The web console imports tui/src/db.js, which needs pg and mysql2.
if [ ! -d "$TUI_DIR/node_modules" ]; then
    echo "Installing shared data-access dependencies (tui/)..."
    (cd "$TUI_DIR" && npm install)
    echo
fi

cd "$WEBUI_DIR"

if [ ! -d node_modules ]; then
    echo "Installing web console dependencies (first run)..."
    npm install
    echo
fi

exec npm start
