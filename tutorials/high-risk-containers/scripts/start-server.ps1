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
# Runs the downloaded Drasi Server binary with the High Risk Containers config.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $TutorialDir "..\..")
$ConfigFile = if ($env:CONFIG_FILE) { $env:CONFIG_FILE } else { Join-Path $TutorialDir "server-config.yaml" }

# Run from the tutorial directory so the Kubernetes source resolves the relative
# kubeconfig path (bin\kubeconfig.yaml) against it.
Set-Location $TutorialDir

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

$kubeconfigFile = Join-Path $TutorialDir "bin\kubeconfig.yaml"
if (-not (Test-Path $kubeconfigFile)) {
    Write-Host "Warning: kubeconfig not found at $kubeconfigFile"
    Write-Host "Run scripts/setup-cluster.ps1 first."
    Write-Host ""
}

$pgRunning = docker ps --filter "name=high-risk-containers-postgres" --format "{{.Names}}" 2>$null
if (-not $pgRunning) {
    Write-Host "Warning: the high-risk-containers-postgres container is not running."
    Write-Host "Run scripts/setup-database.ps1 first."
    Write-Host ""
}

# Cache plugins in a user-owned directory outside the workspace. The default
# location is next to the binary (bin\plugins), but on a bind-mounted workspace
# that path may be owned by another user, so writing the plugin lock file fails
# with "Permission denied". A path under the user profile is always writable and
# persists the cache across runs.
$pluginsDir = if ($env:DRASI_PLUGINS_DIR) { $env:DRASI_PLUGINS_DIR } else { Join-Path $HOME ".drasi\plugins" }
New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null

$serverPort = if ($env:SERVER_PORT) { $env:SERVER_PORT } else { "8380" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "3000" }

Write-Host "=== Drasi Server High Risk Containers ==="
Write-Host "  Binary: $bin"
Write-Host "  Config: $ConfigFile"
Write-Host "  Kubeconfig: $kubeconfigFile"
Write-Host "  Plugins: $pluginsDir"
Write-Host "  API:       http://localhost:$serverPort"
Write-Host "  Dashboard: http://localhost:$dashboardPort"
Write-Host "  API docs:  http://localhost:$serverPort/api/v1/docs/"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server."
Write-Host "=============================================="
Write-Host ""

& $bin --config $ConfigFile --plugins-dir $pluginsDir
