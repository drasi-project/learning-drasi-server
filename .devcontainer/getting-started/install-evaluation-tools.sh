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

# Installs tools required for AI-powered tutorial evaluation.
#
# This script only does work when DRASI_TUTORIAL_EVALUATION=true, which is
# explicitly set by the GitHub Actions tutorial evaluation workflow. During a
# normal (human) devcontainer build the environment variable is unset and this
# script is a no-op, so it adds no overhead to the regular tutorial experience.
#
# Tools installed:
#   - Node.js 22 (from NodeSource): provides npm, required by the Copilot CLI
#   - @github/copilot: GitHub Copilot CLI used to run the evaluation agent
#
# The getting-started tutorial is driven entirely through the terminal
# (drasi-server, drasi-sse-cli, docker, curl, psql), so no browser automation
# tooling (Playwright/Chromium) is required.
#
# Usage: source this script from post-create.sh:
#   source "$(dirname "$0")/install-evaluation-tools.sh"

if [ "$DRASI_TUTORIAL_EVALUATION" = "true" ]; then
    echo "🤖 Installing tutorial evaluation tools..."

    # The base devcontainer image does not include Node.js/npm, which the
    # Copilot CLI requires. Install Node.js 22 from NodeSource. This is only
    # done during evaluation runs, so the normal human tutorial build stays lean.
    if ! command -v npm >/dev/null 2>&1; then
        echo "Installing Node.js 22 (required by the Copilot CLI)..."
        curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi

    echo "Installing GitHub Copilot CLI..."
    npm install -g @github/copilot

    echo "✅ Evaluation tools installed successfully."
    echo "    node: $(node --version 2>/dev/null || echo 'not found')"
    echo "    copilot: $(command -v copilot || echo 'not found')"
fi
