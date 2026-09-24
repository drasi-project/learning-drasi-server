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

# Setup Cluster Script (Windows)
# Builds the mock store images, creates a k3d cluster, imports the images,
# and deploys the Collector plus frontend/checkout/payments.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$ServicesDir = Join-Path $TutorialDir "services"
$ClusterName = if ($env:K3D_CLUSTER_NAME) { $env:K3D_CLUSTER_NAME } else { "otel-observability" }
$ApiPort = if ($env:K3D_API_PORT) { $env:K3D_API_PORT } else { "6551" }
$CheckoutControlPort = if ($env:CHECKOUT_CONTROL_PORT) { $env:CHECKOUT_CONTROL_PORT } else { "18080" }
$BinDir = Join-Path $TutorialDir "bin"
$KubeconfigFile = Join-Path $BinDir "kubeconfig.yaml"

Write-Host "=== Drasi Server OTel Observability - Cluster Setup ==="
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

Write-Host "Building mock store images..."
docker build -t otel-observability-frontend:v1 -f (Join-Path $ServicesDir "frontend\Dockerfile") $ServicesDir
if ($LASTEXITCODE -ne 0) { exit 1 }
docker build --build-arg SERVICE_VERSION=v41 --build-arg WORK_MS=400 -t otel-observability-checkout:v41 -f (Join-Path $ServicesDir "checkout\Dockerfile") $ServicesDir
if ($LASTEXITCODE -ne 0) { exit 1 }
docker build --build-arg SERVICE_VERSION=v42 --build-arg WORK_MS=920 -t otel-observability-checkout:v42 -f (Join-Path $ServicesDir "checkout\Dockerfile") $ServicesDir
if ($LASTEXITCODE -ne 0) { exit 1 }
docker build -t otel-observability-payments:v1 -f (Join-Path $ServicesDir "payments\Dockerfile") $ServicesDir
if ($LASTEXITCODE -ne 0) { exit 1 }

$existing = k3d cluster list --no-headers 2>$null | ForEach-Object { ($_ -split '\s+')[0] }
if ($existing -contains $ClusterName) {
    Write-Host "k3d cluster '$ClusterName' already exists - reusing it."
} else {
    Write-Host "Creating k3d cluster '$ClusterName' (API on 127.0.0.1:$ApiPort, checkout control on :$CheckoutControlPort)..."
    k3d cluster create $ClusterName --api-port $ApiPort --port "${CheckoutControlPort}:30080@server:0" --k3s-arg "--tls-san=127.0.0.1@server:0" --wait
    if ($LASTEXITCODE -ne 0) { Write-Host "Error: failed to create k3d cluster"; exit 1 }
}

Write-Host "Importing mock images into the cluster..."
k3d image import `
    otel-observability-frontend:v1 `
    otel-observability-checkout:v41 `
    otel-observability-checkout:v42 `
    otel-observability-payments:v1 `
    -c $ClusterName
if ($LASTEXITCODE -ne 0) { Write-Host "Error: failed to import images"; exit 1 }

Write-Host "Writing kubeconfig to $KubeconfigFile ..."
$kubeconfig = k3d kubeconfig get $ClusterName
$kubeconfig = $kubeconfig `
    -replace 'https://0\.0\.0\.0:', 'https://127.0.0.1:' `
    -replace 'https://host\.docker\.internal:', 'https://127.0.0.1:'
$kubeconfig = [regex]::Replace(
    $kubeconfig,
    '(?m)^(\s*)certificate-authority-data:.*$',
    '${1}insecure-skip-tls-verify: true'
)
Set-Content -Path $KubeconfigFile -Value $kubeconfig -Encoding ascii

$node = "k3d-$ClusterName-server-0"
$hasAlias = docker exec $node grep -q "host.k3d.internal" /etc/hosts 2>$null
if ($LASTEXITCODE -eq 0) {
    $drasiHost = "host.k3d.internal"
} else {
    $drasiHost = docker exec $node sh -c "ip route 2>/dev/null | awk '/default/ {print `$3; exit}'"
}
if (-not $drasiHost) {
    Write-Host "Error: could not resolve a host address for the OTel Collector export"
    exit 1
}
Write-Host "Collector will export OTLP to ${drasiHost}:14317"

Write-Host "Deploying the OTel Collector..."
$collector = Get-Content -Raw (Join-Path $TutorialDir "k8s\collector.yaml")
$collector = $collector -replace 'host.k3d.internal', $drasiHost
$collector | kubectl --kubeconfig $KubeconfigFile apply -f -
if ($LASTEXITCODE -ne 0) { exit 1 }
kubectl --kubeconfig $KubeconfigFile rollout status deployment/otel-collector --timeout=180s

Write-Host "Deploying mock store services..."
kubectl --kubeconfig $KubeconfigFile apply -f (Join-Path $TutorialDir "k8s\store.yaml")
if ($LASTEXITCODE -ne 0) { exit 1 }
kubectl --kubeconfig $KubeconfigFile rollout restart deployment/frontend,deployment/checkout,deployment/payments
kubectl --kubeconfig $KubeconfigFile rollout status deployment/frontend --timeout=180s
kubectl --kubeconfig $KubeconfigFile rollout status deployment/checkout --timeout=180s
kubectl --kubeconfig $KubeconfigFile rollout status deployment/payments --timeout=180s

Write-Host ""
Write-Host "Running Deployments:"
kubectl --kubeconfig $KubeconfigFile get deploy,pods,svc -l "app in (frontend,checkout,payments,otel-collector)"

Write-Host ""
Write-Host "=== Cluster setup complete! ==="
Write-Host "  Cluster:          $ClusterName"
Write-Host "  Kubeconfig:       $KubeconfigFile"
Write-Host "  Checkout control: http://127.0.0.1:$CheckoutControlPort"
Write-Host ""
Write-Host "Next step: run scripts/setup-database.ps1 then scripts/start-server.ps1"
