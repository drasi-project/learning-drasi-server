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

# Start TUI Script
# Installs dependencies on first run, then launches the terminal UI used to
# drive changes against the two databases (orders in PostgreSQL, vehicles in
# SQL Server). Run this in a second terminal while start-demo.sh / start-server.sh
# runs in the first.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TUI_DIR="$TUTORIAL_DIR/tui"

if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed or not in PATH."
    echo "Install Node.js 18+ from https://nodejs.org/ and try again."
    exit 1
fi

cd "$TUI_DIR"

if [ ! -d node_modules ]; then
    echo "Installing TUI dependencies (first run)..."
    npm install
    echo
fi

exec npm start
