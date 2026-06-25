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

# Reset Script (Windows)
# Returns the demo to its starting state: removes the image added by
# add-risky-image.ps1 and puts the Pods back on their original tags
# (my-app-1 -> :0.1, my-app-2 -> :0.2).

param(
    [int]$Id = 101
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$KubeconfigFile = if ($env:KUBECONFIG_PATH) { $env:KUBECONFIG_PATH } else { Join-Path $TutorialDir "bin\kubeconfig.yaml" }

Write-Host "Removing the added high risk image (Id=$Id)..."
'DELETE FROM "RiskyImage" WHERE "Id" = :''id''::int;' |
    docker exec -i high-risk-containers-postgres psql -v ON_ERROR_STOP=1 -U drasi_user -d high_risk_containers -v "id=$Id"

if (Test-Path $KubeconfigFile) {
    Write-Host "Restoring Pod image tags (my-app-1 -> :0.1, my-app-2 -> :0.2)..."
    kubectl --kubeconfig $KubeconfigFile set image pod/my-app-1 app=ghcr.io/drasi-project/my-app:0.1
    kubectl --kubeconfig $KubeconfigFile set image pod/my-app-2 app=ghcr.io/drasi-project/my-app:0.2
    kubectl --kubeconfig $KubeconfigFile wait --for=condition=Ready pod/my-app-1 pod/my-app-2 --timeout=120s
} else {
    Write-Host "Note: kubeconfig not found at $KubeconfigFile - skipping Pod restore."
}

Write-Host ""
Write-Host "Reset complete. Only my-app-1 (:0.1) should remain flagged."
