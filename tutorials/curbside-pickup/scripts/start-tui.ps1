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

# Start TUI Script (Windows)
# Installs dependencies on first run, then launches the terminal UI used to
# drive changes against the two databases. Run this in a second terminal while
# start-demo.ps1 / start-server.ps1 runs in the first.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Split-Path -Parent $ScriptDir
$TuiDir = Join-Path $TutorialDir "tui"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Node.js is not installed or not in PATH."
    Write-Host "Install Node.js 18+ from https://nodejs.org/ and try again."
    exit 1
}

Set-Location $TuiDir

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing TUI dependencies (first run)..."
    npm install
    Write-Host ""
}

npm start
