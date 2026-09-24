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

# Set Latency Script (Windows)
# POSTs a new p99 gauge value to the checkout mock's control API.

param(
    [Parameter(Mandatory = $true)]
    [string]$Value
)

if ($Value -notmatch '^[0-9]+([.][0-9]+)?$') {
    Write-Host "Usage: scripts/set-latency.ps1 -Value <latency_ms>"
    Write-Host "  scripts/set-latency.ps1 -Value 920"
    exit 1
}

$port = if ($env:CHECKOUT_CONTROL_PORT) { $env:CHECKOUT_CONTROL_PORT } else { "18080" }
$checkoutUrl = if ($env:CHECKOUT_URL) { $env:CHECKOUT_URL } else { "http://127.0.0.1:$port" }

Write-Host "Setting checkout work delay to ${Value}ms via $checkoutUrl"
Invoke-RestMethod -Method Post -Uri "$checkoutUrl/delay/$Value" | ConvertTo-Json
Write-Host ""
Write-Host "Done. Watch the dashboard at http://localhost:3000"
