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

# Cleanup Script (Windows)
# Removes the PostgreSQL container and deletes the k3d cluster.

param(
    [switch]$RemoveVolumes
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$DatabaseDir = Join-Path $TutorialDir "database"
$ClusterName = if ($env:K3D_CLUSTER_NAME) { $env:K3D_CLUSTER_NAME } else { "otel-observability" }

Write-Host "=== Drasi Server OTel Observability - Cleanup ==="
Write-Host ""

if (Get-Command k3d -ErrorAction SilentlyContinue) {
    $existing = k3d cluster list --no-headers 2>$null | ForEach-Object { ($_ -split '\s+')[0] }
    if ($existing -contains $ClusterName) {
        Write-Host "Deleting k3d cluster '$ClusterName'..."
        k3d cluster delete $ClusterName
    }
} else {
    Write-Host "Warning: k3d not found, skipping cluster cleanup"
}

$kubeconfig = Join-Path $TutorialDir "bin\kubeconfig.yaml"
if (Test-Path $kubeconfig) { Remove-Item -Force $kubeconfig }

Push-Location $DatabaseDir
try {
    if ($RemoveVolumes) {
        Write-Host "Removing container and volumes..."
        docker compose down -v 2>&1 | Write-Host
    } else {
        Write-Host "Removing container (keeping volumes)..."
        docker compose down 2>&1 | Write-Host
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Cleanup complete! ==="
Write-Host ""
Write-Host "Options:"
Write-Host "  scripts/cleanup.ps1                 # Stop containers + cluster, keep data volumes"
Write-Host "  scripts/cleanup.ps1 -RemoveVolumes  # Stop containers + cluster and remove data volumes"
