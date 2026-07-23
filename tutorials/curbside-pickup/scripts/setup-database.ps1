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
# Starts PostgreSQL (orders) and MySQL (vehicles), both with CDC, and seeds.

$ErrorActionPreference = "Stop"

# Run a native readiness probe quietly and report success via its exit code.
# The databases are still starting when these probes first run, so a probe is
# EXPECTED to fail (and print to stderr) for the first few attempts. Under
# $ErrorActionPreference = "Stop", Windows PowerShell 5.1 turns any native
# command's stderr output into a terminating error - which even `*> $null` does
# not suppress - so a normal "not ready yet" message would abort the whole
# script (e.g. MySQL's "ERROR 2003 ... Can't connect"). Lower the preference for
# the duration of the probe and rely on the exit code instead. Works the same on
# PowerShell 5.1 and 7+.
function Test-Ready {
    param([Parameter(Mandatory = $true)][scriptblock]$Probe)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try { & $Probe 2>$null | Out-Null } finally { $ErrorActionPreference = $prev }
    return ($LASTEXITCODE -eq 0)
}

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

$MysqlRootPw = if ($env:MYSQL_ROOT_PASSWORD) { $env:MYSQL_ROOT_PASSWORD } else { "root_admin" }
$MysqlDb = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "PhysicalOperations" }

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

    Write-Host "Starting PostgreSQL and MySQL..."
    Invoke-Expression "$ComposeCmd up -d"

    # --- PostgreSQL --------------------------------------------------------
    Write-Host ""
    Write-Host "Waiting for PostgreSQL to be ready..."
    $ok = $false
    for ($i = 1; $i -le 30; $i++) {
        if (Test-Ready { docker exec curbside-pickup-postgres pg_isready -h localhost -U postgres -d RetailOperations }) {
            $ok = $true; Write-Host "PostgreSQL is ready!"; break
        }
        Write-Host "  Waiting... ($i/30)"
        Start-Sleep -Seconds 2
    }
    if (-not $ok) { Write-Host "Error: PostgreSQL failed to start in time."; exit 1 }

    Write-Host "Applying Retail Operations schema and seed data..."
    Get-Content (Join-Path $DatabaseDir "postgres-init.sql") -Raw | docker exec -i curbside-pickup-postgres psql -v ON_ERROR_STOP=1 -U postgres -d RetailOperations

    # --- MySQL -------------------------------------------------------------
    Write-Host ""
    Write-Host "Waiting for MySQL to be ready..."
    $ok = $false
    for ($i = 1; $i -le 40; $i++) {
        # Authenticate over TCP against the target database. MySQL's first-init
        # temporary server runs with --skip-networking (socket only), so a TCP
        # connection only succeeds once the real server is up with the configured
        # root password and MYSQL_DATABASE created - avoiding a cold-init race that
        # a plain `mysqladmin ping` (which passes even on auth failure) would miss.
        if (Test-Ready { docker exec -e MYSQL_PWD=$MysqlRootPw curbside-pickup-mysql mysql -h 127.0.0.1 -uroot -e "USE $MysqlDb" }) {
            $ok = $true; Write-Host "MySQL is ready!"; break
        }
        Write-Host "  Waiting... ($i/40)"
        Start-Sleep -Seconds 3
    }
    if (-not $ok) { Write-Host "Error: MySQL failed to start in time."; exit 1 }

    Write-Host "Applying Physical Operations schema, seed data, and replication grants..."
    Get-Content (Join-Path $DatabaseDir "mysql-init.sql") -Raw | docker exec -i -e MYSQL_PWD=$MysqlRootPw curbside-pickup-mysql mysql -uroot

    # --- Verify ------------------------------------------------------------
    Write-Host ""
    Write-Host "Seeded orders (PostgreSQL):"
    docker exec curbside-pickup-postgres psql -U drasi_user -d RetailOperations -c "SELECT id, customer_name, plate, status FROM orders ORDER BY id;"

    Write-Host ""
    Write-Host "Seeded vehicles (MySQL):"
    docker exec -e MYSQL_PWD=$MysqlRootPw curbside-pickup-mysql mysql -uroot -e "SELECT plate, customer_name, location FROM $MysqlDb.vehicles ORDER BY plate;"

    Write-Host ""
    Write-Host "=== Database setup complete! ==="
    Write-Host "Next step: run .\scripts\start-server.ps1 to start Drasi Server"
}
finally {
    Pop-Location
}
