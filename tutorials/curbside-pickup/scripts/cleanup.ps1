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

# Cleanup Script (Windows)
# Stops Drasi Server and removes the PostgreSQL and SQL Server containers.

$ErrorActionPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Split-Path -Parent $ScriptDir
$DatabaseDir = Join-Path $TutorialDir "database"
$RemoveVolumes = $args[0]

Write-Host "=== Drasi Server Curbside Pickup - Cleanup ==="
Write-Host ""

Write-Host "Stopping Drasi Server processes..."
Get-Process drasi-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

docker compose version *> $null
$ComposeCmd = if ($LASTEXITCODE -eq 0) { "docker compose" } else { "docker-compose" }

Push-Location $DatabaseDir
try {
    if ($RemoveVolumes -eq "--volumes" -or $RemoveVolumes -eq "-v") {
        Write-Host "Removing containers and volumes..."
        Invoke-Expression "$ComposeCmd down -v"
    } else {
        Write-Host "Removing containers (keeping volumes)..."
        Invoke-Expression "$ComposeCmd down"
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Cleanup complete! ==="
Write-Host "Options:"
Write-Host "  .\scripts\cleanup.ps1           # Stop containers, keep data volumes"
Write-Host "  .\scripts\cleanup.ps1 --volumes # Stop containers and remove data volumes"
