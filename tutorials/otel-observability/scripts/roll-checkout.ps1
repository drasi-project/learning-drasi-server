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

# Optional helper. The tutorial drive step shows these same kubectl commands.

param(
    [string]$Version = "v42"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$env:KUBECONFIG = if ($env:KUBECONFIG_PATH) { $env:KUBECONFIG_PATH } else { Join-Path $TutorialDir "bin\kubeconfig.yaml" }

if ($Version -notmatch '^v[0-9]+$') {
    Write-Host "Usage: scripts/roll-checkout.ps1 [-Version v41|v42]"
    exit 1
}

if (-not (Test-Path $env:KUBECONFIG)) {
    Write-Host "Error: kubeconfig not found at $($env:KUBECONFIG)"
    Write-Host "Run scripts/setup-cluster.ps1 first."
    exit 1
}

kubectl set image deployment/checkout "app=otel-observability-checkout:$Version"
if ($LASTEXITCODE -ne 0) { exit 1 }
kubectl rollout status deployment/checkout --timeout=120s
if ($LASTEXITCODE -ne 0) { exit 1 }
kubectl label deployment/checkout "version=$Version" --overwrite
