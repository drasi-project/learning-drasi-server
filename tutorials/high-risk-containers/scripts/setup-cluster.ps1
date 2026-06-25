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

# Setup Cluster Script (Windows)
# Creates a local k3d Kubernetes cluster, writes a kubeconfig that Drasi Server
# can use from the host, and deploys the two demo Pods (my-app-1, my-app-2).

# Note: we check $LASTEXITCODE explicitly rather than setting
# $ErrorActionPreference = "Stop", because the docker/k3d CLIs write progress to
# stderr, which PowerShell would otherwise treat as a terminating error.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$ClusterName = if ($env:K3D_CLUSTER_NAME) { $env:K3D_CLUSTER_NAME } else { "high-risk-containers" }
$ApiPort = if ($env:K3D_API_PORT) { $env:K3D_API_PORT } else { "6550" }
$BinDir = Join-Path $TutorialDir "bin"
$KubeconfigFile = Join-Path $BinDir "kubeconfig.yaml"

Write-Host "=== Drasi Server High Risk Containers - Cluster Setup ==="
Write-Host ""

if (-not (Get-Command k3d -ErrorAction SilentlyContinue)) {
    Write-Host "Error: k3d is not installed or not in PATH"
    Write-Host "Install it from https://k3d.io/#installation"
    exit 1
}

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "Error: kubectl is not installed or not in PATH"
    Write-Host "Install it from https://kubernetes.io/docs/tasks/tools/"
    exit 1
}

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker daemon is not running"
    Write-Host "Please start Docker and try again"
    exit 1
}

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# Create the cluster only if it does not already exist (idempotent re-runs).
$existing = k3d cluster list --no-headers 2>$null | ForEach-Object { ($_ -split '\s+')[0] }
if ($existing -contains $ClusterName) {
    Write-Host "k3d cluster '$ClusterName' already exists - reusing it."
} else {
    Write-Host "Creating k3d cluster '$ClusterName' (API on 127.0.0.1:$ApiPort)..."
    k3d cluster create $ClusterName --api-port $ApiPort --wait
    if ($LASTEXITCODE -ne 0) { Write-Host "Error: failed to create k3d cluster"; exit 1 }
}

# Write a kubeconfig Drasi Server can read from the host. k3d points the server
# URL at 0.0.0.0 (or host.docker.internal); normalize it to 127.0.0.1 so the
# Kubernetes source can reach the API from outside the cluster.
Write-Host "Writing kubeconfig to $KubeconfigFile ..."
$kubeconfig = k3d kubeconfig get $ClusterName
$kubeconfig = $kubeconfig `
    -replace 'https://0\.0\.0\.0:', 'https://127.0.0.1:' `
    -replace 'https://host\.docker\.internal:', 'https://127.0.0.1:'
Set-Content -Path $KubeconfigFile -Value $kubeconfig -Encoding ascii

Write-Host "Deploying demo Pods (my-app-1, my-app-2)..."
kubectl --kubeconfig $KubeconfigFile apply -f (Join-Path $TutorialDir "k8s\my-app.yaml")
if ($LASTEXITCODE -ne 0) { Write-Host "Error: failed to apply k8s/my-app.yaml"; exit 1 }

Write-Host "Waiting for Pods to be ready..."
kubectl --kubeconfig $KubeconfigFile wait --for=condition=Ready pod/my-app-1 pod/my-app-2 --timeout=120s

Write-Host ""
Write-Host "Running Pods:"
kubectl --kubeconfig $KubeconfigFile get pods -o wide

Write-Host ""
Write-Host "=== Cluster setup complete! ==="
Write-Host "  Cluster:    $ClusterName"
Write-Host "  Kubeconfig: $KubeconfigFile"
Write-Host ""
Write-Host "Next step: run scripts/start-server.ps1 to start Drasi Server"
