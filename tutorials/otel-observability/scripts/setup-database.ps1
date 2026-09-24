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

# Setup Database Script (Windows)
# Starts PostgreSQL with logical replication enabled and seeds service_slo_policy.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DatabaseDir = Join-Path $ScriptDir "..\database"

Write-Host "=== Drasi Server OTel Observability - Database Setup ==="
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker is not installed or not in PATH"
    Write-Host "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
}

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker daemon is not running"
    Write-Host "Please start Docker and try again"
    exit 1
}

Push-Location $DatabaseDir
try {
    Write-Host "Stopping any existing PostgreSQL container..."
    docker compose down -v 2>&1 | Out-Null

    Write-Host "Starting PostgreSQL with WAL replication..."
    docker compose up -d 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: failed to start PostgreSQL container"
        exit 1
    }

    Write-Host "Waiting for PostgreSQL to be ready..."
    $maxRetries = 30
    $ready = $false
    for ($i = 1; $i -le $maxRetries; $i++) {
        docker exec otel-observability-postgres pg_isready -h localhost -U postgres -d otel_observability 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL is ready!"
            $ready = $true
            break
        }
        Write-Host "  Waiting... ($i/$maxRetries)"
        Start-Sleep -Seconds 2
    }

    if (-not $ready) {
        Write-Host "Error: PostgreSQL failed to start within the timeout"
        Write-Host "Check logs with: docker logs otel-observability-postgres"
        exit 1
    }

    Write-Host "Applying schema and seed data..."
    Get-Content (Join-Path $DatabaseDir "init.sql") -Raw | docker exec -i otel-observability-postgres `
        psql -v ON_ERROR_STOP=1 -U postgres -d otel_observability
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: failed to apply init.sql"
        exit 1
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Seeded SLO policy:"
docker exec otel-observability-postgres psql -U drasi_user -d otel_observability -c `
    "SELECT service_name, metric_name, threshold_ms FROM service_slo_policy;"

Write-Host ""
Write-Host "=== Database setup complete! ==="
Write-Host ""
Write-Host "Next step: run scripts/start-server.ps1 to start Drasi Server"
