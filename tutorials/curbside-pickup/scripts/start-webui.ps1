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

# Start Web Console Script (Windows)
# Installs dependencies on first run, then launches the browser-based UI used to
# drive changes against the two databases. It is the browser sibling of
# scripts/start-tui.ps1 and reuses the same tui/src/db.js data-access layer, so
# it needs the tui dependencies too. Run this in a second terminal while
# start-demo.ps1 / start-server.ps1 runs in the first, then open
# http://localhost:3001.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Split-Path -Parent $ScriptDir
$TuiDir = Join-Path $TutorialDir "tui"
$WebuiDir = Join-Path $TutorialDir "webui"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Node.js is not installed or not in PATH."
    Write-Host "Install Node.js 18+ from https://nodejs.org/ and try again."
    exit 1
}

# The web console imports tui/src/db.js, which needs pg and mysql2.
if (-not (Test-Path (Join-Path $TuiDir "node_modules"))) {
    Write-Host "Installing shared data-access dependencies (tui/)..."
    Push-Location $TuiDir
    npm install
    Pop-Location
    Write-Host ""
}

Set-Location $WebuiDir

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing web console dependencies (first run)..."
    npm install
    Write-Host ""
}

npm start
