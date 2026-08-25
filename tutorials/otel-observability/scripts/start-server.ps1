# Copyright 2026 The Drasi Authors.
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
# Runs the downloaded Drasi Server binary with the OTel Observability config.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $TutorialDir "..\..")
$ConfigFile = if ($env:CONFIG_FILE) { $env:CONFIG_FILE } else { Join-Path $TutorialDir "server-config.yaml" }

Set-Location $TutorialDir

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

$pgRunning = docker ps --filter "name=otel-observability-postgres" --format "{{.Names}}" 2>$null
if (-not $pgRunning) {
    Write-Host "Warning: the otel-observability-postgres container is not running."
    Write-Host "Run scripts/setup-database.ps1 first."
    Write-Host ""
}

$pluginsDir = if ($env:DRASI_PLUGINS_DIR) { $env:DRASI_PLUGINS_DIR } else { Join-Path $TutorialDir "bin\plugins" }
New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null

& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "install-otel-plugin.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$serverPort = if ($env:SERVER_PORT) { $env:SERVER_PORT } else { "8380" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "3000" }
$otlpBind = if ($env:OTEL_GRPC_BIND) { $env:OTEL_GRPC_BIND } else { "0.0.0.0:14317" }

Write-Host "=== Drasi Server OTel Observability ==="
Write-Host "  Binary: $bin"
Write-Host "  Config: $ConfigFile"
Write-Host "  Kubeconfig: $kubeconfigFile"
Write-Host "  Plugins: $pluginsDir"
Write-Host "  API:       http://localhost:$serverPort"
Write-Host "  Dashboard: http://localhost:$dashboardPort"
Write-Host "  OTLP:      $otlpBind"
Write-Host "  API docs:  http://localhost:$serverPort/api/v1/docs/"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server."
Write-Host "=============================================="
Write-Host ""

if ((Test-Path $kubeconfigFile) -and (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    kubectl --kubeconfig $kubeconfigFile get deploy otel-collector 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Restarting the OTel Collector so it reconnects immediately..."
        kubectl --kubeconfig $kubeconfigFile rollout restart deploy/otel-collector | Out-Null
    }
}

& $bin --config $ConfigFile --plugins-dir $pluginsDir
