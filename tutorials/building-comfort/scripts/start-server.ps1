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

# Start Server Script (Windows)
# Runs the downloaded Drasi Server binary with the Building Comfort configuration.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $TutorialDir "..\..")
$ConfigFile = if ($env:CONFIG_FILE) { $env:CONFIG_FILE } else { Join-Path $TutorialDir "server-config.yaml" }

# Locate the drasi-server binary downloaded by scripts/download.ps1.
$bin = $null
foreach ($candidate in @(
    (Join-Path $TutorialDir "bin\drasi-server.exe"),
    (Join-Path $RepoRoot "bin\drasi-server.exe")
)) {
    if (Test-Path $candidate) { $bin = $candidate; break }
}

if (-not $bin) {
    Write-Host "Error: drasi-server binary not found."
    Write-Host "Run scripts/download.ps1 first."
    exit 1
}

if (-not (Test-Path $ConfigFile)) {
    Write-Host "Error: Configuration file not found: $ConfigFile"
    exit 1
}

$pgRunning = docker ps --filter "name=building-comfort-postgres" --format "{{.Names}}" 2>$null
if (-not $pgRunning) {
    Write-Host "Warning: the building-comfort-postgres container is not running."
    Write-Host "Run scripts/setup-database.ps1 first."
    Write-Host ""
}

$serverPort = if ($env:SERVER_PORT) { $env:SERVER_PORT } else { "8380" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "3000" }

Write-Host "=== Drasi Server Building Comfort ==="
Write-Host "  Binary: $bin"
Write-Host "  Config: $ConfigFile"
Write-Host "  API:       http://localhost:$serverPort"
Write-Host "  Dashboard: http://localhost:$dashboardPort"
Write-Host "  API docs:  http://localhost:$serverPort/api/v1/docs/"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server."
Write-Host "=============================================="
Write-Host ""

& $bin --config $ConfigFile
