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

# Setup Database Script (Windows)
# Starts PostgreSQL (orders) and SQL Server (vehicles), both with CDC, and seeds.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Split-Path -Parent $ScriptDir
$DatabaseDir = Join-Path $TutorialDir "database"

# Load .env if present.
$EnvFile = Join-Path $TutorialDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
        }
    }
}

$SaPassword = if ($env:MSSQL_SA_PASSWORD) { $env:MSSQL_SA_PASSWORD } else { "Drasi_Passw0rd!" }
$Sqlcmd = "/opt/mssql-tools18/bin/sqlcmd"

Write-Host "=== Drasi Server Curbside Pickup - Database Setup ==="
Write-Host ""

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker is not running. Please start Docker Desktop and try again."
    exit 1
}

docker compose version *> $null
$ComposeCmd = if ($LASTEXITCODE -eq 0) { "docker compose" } else { "docker-compose" }
Write-Host "Using: $ComposeCmd"
Write-Host ""

Push-Location $DatabaseDir
try {
    Write-Host "Stopping any existing database containers..."
    Invoke-Expression "$ComposeCmd down -v" 2>$null

    Write-Host "Starting PostgreSQL and SQL Server..."
    Invoke-Expression "$ComposeCmd up -d"

    # --- PostgreSQL --------------------------------------------------------
    Write-Host ""
    Write-Host "Waiting for PostgreSQL to be ready..."
    $ok = $false
    for ($i = 1; $i -le 30; $i++) {
        docker exec curbside-pickup-postgres pg_isready -h localhost -U postgres -d RetailOperations *> $null
        if ($LASTEXITCODE -eq 0) { $ok = $true; Write-Host "PostgreSQL is ready!"; break }
        Write-Host "  Waiting... ($i/30)"
        Start-Sleep -Seconds 2
    }
    if (-not $ok) { Write-Host "Error: PostgreSQL failed to start in time."; exit 1 }

    Write-Host "Applying Retail Operations schema and seed data..."
    Get-Content (Join-Path $DatabaseDir "postgres-init.sql") -Raw | docker exec -i curbside-pickup-postgres psql -v ON_ERROR_STOP=1 -U postgres -d RetailOperations

    # --- SQL Server --------------------------------------------------------
    Write-Host ""
    Write-Host "Waiting for SQL Server to be ready..."
    $ok = $false
    for ($i = 1; $i -le 40; $i++) {
        docker exec curbside-pickup-mssql $Sqlcmd -S localhost -U sa -P $SaPassword -C -Q "SELECT 1" *> $null
        if ($LASTEXITCODE -eq 0) { $ok = $true; Write-Host "SQL Server is ready!"; break }
        Write-Host "  Waiting... ($i/40)"
        Start-Sleep -Seconds 3
    }
    if (-not $ok) { Write-Host "Error: SQL Server failed to start in time."; exit 1 }

    Write-Host "Applying Physical Operations schema, seed data, and enabling CDC..."
    Get-Content (Join-Path $DatabaseDir "mssql-init.sql") -Raw | docker exec -i curbside-pickup-mssql $Sqlcmd -S localhost -U sa -P $SaPassword -C -b

    # --- Verify ------------------------------------------------------------
    Write-Host ""
    Write-Host "Seeded orders (PostgreSQL):"
    docker exec curbside-pickup-postgres psql -U drasi_user -d RetailOperations -c "SELECT id, customer_name, plate, status FROM orders ORDER BY id;"

    Write-Host ""
    Write-Host "Seeded vehicles (SQL Server):"
    docker exec curbside-pickup-mssql $Sqlcmd -S localhost -U sa -P $SaPassword -C -Q "SET NOCOUNT ON; SELECT plate, customer_name, location FROM PhysicalOperations.dbo.vehicles ORDER BY plate;"

    Write-Host ""
    Write-Host "=== Database setup complete! ==="
    Write-Host "Next step: run .\scripts\start-server.ps1 to start Drasi Server"
}
finally {
    Pop-Location
}
