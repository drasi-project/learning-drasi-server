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

# Reset Script (Windows)
# Returns the demo to its starting state: checkout v41, latency 400, heartbeat
# on, SLO threshold 750.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Resetting checkout to v41..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "roll-checkout.ps1") -Version v41
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Restoring healthy latency and heartbeat..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "set-latency.ps1") -Value 400
& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "start-heartbeat.ps1")

Write-Host ""
Write-Host "Restoring the default SLO threshold..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "set-slo.ps1") -Threshold 750

Write-Host ""
Write-Host "Reset complete. Checkout should be v41 at 400ms with a 750ms SLO."
