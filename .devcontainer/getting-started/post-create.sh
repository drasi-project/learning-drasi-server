#!/bin/bash
# Copyright 2026 The Drasi Authors
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

# Post-create script for Drasi Server Getting Started tutorial

set -e

echo "🔧 Initializing Drasi Server Getting Started tutorial environment..."

# Install system dependencies
echo "🐘 Installing system dependencies (PostgreSQL client)..."
sudo apt-get update && sudo apt-get install -y postgresql-client

# Download pre-built Drasi Server and SSE CLI binaries.
# Invoke via `bash` so we don't depend on the executable bit, which can be
# lost on Windows bind-mounts (e.g. workspace under OneDrive) where chmod
# is not permitted on the mounted filesystem.
echo "⬇️  Downloading Drasi Server and SSE CLI binaries..."
bash tutorials/getting-started/scripts/download.sh

echo ""
echo "✅ Drasi Server Getting Started tutorial environment is ready!"
