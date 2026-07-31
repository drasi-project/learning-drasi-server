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
# Runs the downloaded Drasi Server binary with the Curbside Pickup config, and
# starts the browser-based operations console (webui/) alongside it so one
# command brings up everything. Open the dashboard at http://localhost:3000 and
# the console at http://localhost:3001.

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
$WebuiPort = if ($env:WEBUI_PORT) { $env:WEBUI_PORT } else { "3001" }

# Start the browser-based operations console in the background so a single
# command brings up everything you need. It inherits this session's environment
# (the .env values loaded above), so it points at the same databases.
$WebuiDir = Join-Path $TutorialDir "webui"
$WebuiProc = $null
if (Get-Command node -ErrorAction SilentlyContinue) {
    if (-not (Test-Path (Join-Path $WebuiDir "node_modules"))) {
        Write-Host "Installing web console dependencies (first run)..."
        Push-Location $WebuiDir
        npm install
        Pop-Location
        Write-Host ""
    }
    $WebuiProc = Start-Process -FilePath "node" -ArgumentList "src/server.js" -WorkingDirectory $WebuiDir -PassThru -NoNewWindow

    # Wait until the console is actually serving before printing the banner, so
    # you get clear feedback that it is up (and can open it right away) instead
    # of guessing whether it is still starting.
    Write-Host -NoNewline "Starting the operations console"
    $WebuiReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        if ($WebuiProc.HasExited) { break }
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:$WebuiPort/api/state" -TimeoutSec 2 -UseBasicParsing
            $WebuiReady = $true
            break
        } catch {
            Write-Host -NoNewline "."
            Start-Sleep -Milliseconds 500
        }
    }
    if ($WebuiReady) {
        Write-Host " ready."
    } else {
        Write-Host ""
        Write-Host "Warning: the operations console did not start (check for errors above)."
    }
    Write-Host ""
} else {
    Write-Host "Note: Node.js not found, so the web console was not started."
    Write-Host "Install Node.js 18+ to drive changes from http://localhost:$WebuiPort."
    Write-Host ""
}

Write-Host "=== Drasi Server Curbside Pickup ==="
Write-Host "  Binary:      $Bin"
Write-Host "  Config:      $ConfigFile"
Write-Host "  Plugins:     $PluginsDir"
Write-Host "  API:         http://localhost:$ServerPort"
Write-Host "  Dashboard:   http://localhost:$DashboardPort"
if ($WebuiProc) {
    Write-Host "  Web console: http://localhost:$WebuiPort"
}
Write-Host "  API docs:    http://localhost:$ServerPort/api/v1/docs/"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server (and the web console)."
Write-Host "==================================="
Write-Host ""

try {
    & $Bin --config $ConfigFile --plugins-dir $PluginsDir
} finally {
    # Stop the web console when the server exits (Ctrl+C or otherwise).
    if ($WebuiProc -and -not $WebuiProc.HasExited) {
        Stop-Process -Id $WebuiProc.Id -Force -ErrorAction SilentlyContinue
    }
}
