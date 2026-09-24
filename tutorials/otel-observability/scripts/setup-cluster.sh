#!/bin/bash
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

# Setup Cluster Script
# Builds the mock store images, creates a k3d cluster, imports the images,
# and deploys the Collector plus frontend/checkout/payments.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICES_DIR="$TUTORIAL_DIR/services"
CLUSTER_NAME="${K3D_CLUSTER_NAME:-otel-observability}"
API_PORT="${K3D_API_PORT:-6551}"
CHECKOUT_CONTROL_PORT="${CHECKOUT_CONTROL_PORT:-18080}"
KUBECONFIG_FILE="$TUTORIAL_DIR/bin/kubeconfig.yaml"

echo "=== Drasi Server OTel Observability - Cluster Setup ==="
echo

if ! command -v k3d &> /dev/null; then
    echo "Error: k3d is not installed or not in PATH"
    echo "Install it from https://k3d.io/#installation"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed or not in PATH"
    echo "Install it from https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "Error: Docker daemon is not running"
    echo "Please start Docker and try again"
    exit 1
fi

mkdir -p "$TUTORIAL_DIR/bin"

echo "Building mock store images..."
docker build -t otel-observability-frontend:v1 -f "$SERVICES_DIR/frontend/Dockerfile" "$SERVICES_DIR"
docker build --build-arg SERVICE_VERSION=v41 --build-arg WORK_MS=400 -t otel-observability-checkout:v41 -f "$SERVICES_DIR/checkout/Dockerfile" "$SERVICES_DIR"
docker build --build-arg SERVICE_VERSION=v42 --build-arg WORK_MS=920 -t otel-observability-checkout:v42 -f "$SERVICES_DIR/checkout/Dockerfile" "$SERVICES_DIR"
docker build -t otel-observability-payments:v1 -f "$SERVICES_DIR/payments/Dockerfile" "$SERVICES_DIR"

if k3d cluster list 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
    echo "k3d cluster '$CLUSTER_NAME' already exists - reusing it."
else
    echo "Creating k3d cluster '$CLUSTER_NAME' (API on 127.0.0.1:$API_PORT, checkout control on :$CHECKOUT_CONTROL_PORT)..."
    k3d cluster create "$CLUSTER_NAME" \
        --api-port "$API_PORT" \
        --port "${CHECKOUT_CONTROL_PORT}:30080@server:0" \
        --k3s-arg "--tls-san=127.0.0.1@server:0" \
        --wait
fi

echo "Importing mock images into the cluster..."
k3d image import \
    otel-observability-frontend:v1 \
    otel-observability-checkout:v41 \
    otel-observability-checkout:v42 \
    otel-observability-payments:v1 \
    -c "$CLUSTER_NAME"

echo "Writing kubeconfig to $KUBECONFIG_FILE ..."
# Docker Desktop's k3d load-balancer cert is not in the bundled CA. Keep the
# client cert/key intact and skip TLS verify so both kubectl and the Kubernetes
# source can reach https://127.0.0.1:$API_PORT. awk only — the tutorial
# container does not ship python3.
k3d kubeconfig get "$CLUSTER_NAME" | awk '
  /certificate-authority-data:/ {
    match($0, /^[ \t]*/)
    print substr($0, 1, RLENGTH) "insecure-skip-tls-verify: true"
    next
  }
  {
    gsub("https://0.0.0.0:", "https://127.0.0.1:")
    gsub("https://host.docker.internal:", "https://127.0.0.1:")
    print
  }
' > "$KUBECONFIG_FILE"

# k3d injects host.k3d.internal into the node /etc/hosts on Docker Desktop.
# Nested Docker-in-Docker often skips that alias; pods then fail DNS and
# must use the node default gateway (the environment running Drasi).
NODE="k3d-${CLUSTER_NAME}-server-0"
if docker exec "$NODE" grep -q 'host.k3d.internal' /etc/hosts 2>/dev/null; then
    DRASI_HOST="host.k3d.internal"
else
    DRASI_HOST="$(docker exec "$NODE" sh -c "ip route 2>/dev/null | awk '/default/ {print \$3; exit}'")"
fi
if ! printf '%s' "$DRASI_HOST" | grep -Eq '^(host\.k3d\.internal|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$'; then
    echo "Error: could not resolve a host address for the OTel Collector export"
    exit 1
fi
echo "Collector will export OTLP to ${DRASI_HOST}:14317"

echo "Deploying the OTel Collector..."
sed "s/host.k3d.internal/${DRASI_HOST}/g" "$TUTORIAL_DIR/k8s/collector.yaml" \
    | kubectl --kubeconfig "$KUBECONFIG_FILE" apply -f -
kubectl --kubeconfig "$KUBECONFIG_FILE" rollout status deployment/otel-collector --timeout=180s

echo "Deploying mock store services..."
kubectl --kubeconfig "$KUBECONFIG_FILE" apply -f "$TUTORIAL_DIR/k8s/store.yaml"
# Same tags after image import do not change the pod spec, so restart to pick up new layers.
kubectl --kubeconfig "$KUBECONFIG_FILE" rollout restart deployment/frontend deployment/checkout deployment/payments
kubectl --kubeconfig "$KUBECONFIG_FILE" rollout status deployment/frontend --timeout=180s
kubectl --kubeconfig "$KUBECONFIG_FILE" rollout status deployment/checkout --timeout=180s
kubectl --kubeconfig "$KUBECONFIG_FILE" rollout status deployment/payments --timeout=180s

echo
echo "Running Deployments:"
kubectl --kubeconfig "$KUBECONFIG_FILE" get deploy,pods,svc -l 'app in (frontend,checkout,payments,otel-collector)'

echo
echo "=== Cluster setup complete! ==="
echo "  Cluster:         $CLUSTER_NAME"
echo "  Kubeconfig:      $KUBECONFIG_FILE"
echo "  Checkout control: http://127.0.0.1:${CHECKOUT_CONTROL_PORT}"
echo
echo "Next step: run ./scripts/setup-database.sh then ./scripts/start-server.sh"
