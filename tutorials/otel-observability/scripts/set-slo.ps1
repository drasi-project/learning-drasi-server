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

# Set SLO Script (Windows)
# Updates checkout's latency_p99_ms threshold in PostgreSQL.

param(
    [Parameter(Mandatory = $true)]
    [string]$Threshold
)

if ($Threshold -notmatch '^[0-9]+([.][0-9]+)?$') {
    Write-Host "Usage: scripts/set-slo.ps1 -Threshold <threshold_ms>"
    exit 1
}

$container = if ($env:POSTGRES_CONTAINER) { $env:POSTGRES_CONTAINER } else { "otel-observability-postgres" }

Write-Host "Setting checkout latency_p99_ms threshold to $Threshold"
docker exec $container psql -U drasi_user -d otel_observability -c `
    "UPDATE service_slo_policy SET threshold_ms = $Threshold WHERE service_name = 'checkout' AND metric_name = 'latency_p99_ms' RETURNING service_name, metric_name, threshold_ms;"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Done. Watch the dashboard at http://localhost:3000"
