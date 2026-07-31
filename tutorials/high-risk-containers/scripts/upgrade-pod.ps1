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

# Upgrade Pod Script (Windows)
# Upgrades a running Pod to a different (non-risky) image tag. By default it
# moves my-app-2 from :0.2 to :0.3, so it drops out of the query results and
# disappears from the dashboard.
#
# Usage: upgrade-pod.ps1 [-Pod <name>] [-Image <img>]

param(
    [string]$Pod = "my-app-2",
    [string]$Image = "ghcr.io/drasi-project/my-app:0.3",
    [string]$Container = "app"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$KubeconfigFile = if ($env:KUBECONFIG_PATH) { $env:KUBECONFIG_PATH } else { Join-Path $TutorialDir "bin\kubeconfig.yaml" }

if (-not (Test-Path $KubeconfigFile)) {
    Write-Host "Error: kubeconfig not found at $KubeconfigFile"
    Write-Host "Run scripts/setup-cluster.ps1 first."
    exit 1
}

Write-Host "Upgrading $Pod container '$Container' to $Image ..."
kubectl --kubeconfig $KubeconfigFile set image "pod/$Pod" "$Container=$Image"
if ($LASTEXITCODE -ne 0) { Write-Host "Error: failed to set image"; exit 1 }

Write-Host "Waiting for $Pod to be ready..."
kubectl --kubeconfig $KubeconfigFile wait --for=condition=Ready "pod/$Pod" --timeout=120s

Write-Host ""
Write-Host "Done. If '$Image' is not in the RiskyImage table, $Pod disappears from the"
Write-Host "High Risk Containers list on the dashboard at http://localhost:3000."
