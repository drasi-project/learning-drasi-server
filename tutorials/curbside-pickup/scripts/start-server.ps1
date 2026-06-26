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
# Runs the downloaded Drasi Server binary with the Curbside Pickup config.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TutorialDir)
$ConfigFile = if ($env:CONFIG_FILE) { $env:CONFIG_FILE } else { Join-Path $TutorialDir "server-config.yaml" }

# Load .env if present.
$EnvFile = Join-Path $TutorialDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
        }
    }
}

Set-Location $TutorialDir

# Locate the drasi-server binary downloaded by download.ps1.
$Bin = $null
foreach ($candidate in @(
    (Join-Path $RepoRoot "bin\drasi-server.exe"),
    (Join-Path $TutorialDir "bin\drasi-server.exe")
)) {
    if (Test-Path $candidate) { $Bin = $candidate; break }
}
if (-not $Bin) {
    Write-Host "Error: drasi-server.exe not found. Run .\scripts\download.ps1 first."
    exit 1
}

if (-not (Test-Path $ConfigFile)) {
    Write-Host "Error: Configuration file not found: $ConfigFile"
    exit 1
}

# Plugins are cached in a user-owned directory.
$PluginsDir = if ($env:DRASI_PLUGINS_DIR) { $env:DRASI_PLUGINS_DIR } else { Join-Path $env:USERPROFILE ".drasi\plugins" }
New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null

$ServerPort = if ($env:SERVER_PORT) { $env:SERVER_PORT } else { "8480" }
$DashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "3000" }

Write-Host "=== Drasi Server Curbside Pickup ==="
Write-Host "  Binary:    $Bin"
Write-Host "  Config:    $ConfigFile"
Write-Host "  Plugins:   $PluginsDir"
Write-Host "  API:       http://localhost:$ServerPort"
Write-Host "  Dashboard: http://localhost:$DashboardPort"
Write-Host "  API docs:  http://localhost:$ServerPort/api/v1/docs/"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server."
Write-Host "==================================="
Write-Host ""

& $Bin --config $ConfigFile --plugins-dir $PluginsDir
