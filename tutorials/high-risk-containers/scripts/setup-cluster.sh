#!/bin/bash
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

# Setup Cluster Script
# Creates a local k3d Kubernetes cluster, writes a kubeconfig that Drasi Server
# can use from the host, and deploys the two demo Pods (my-app-1, my-app-2).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLUSTER_NAME="${K3D_CLUSTER_NAME:-high-risk-containers}"
API_PORT="${K3D_API_PORT:-6550}"
KUBECONFIG_FILE="$TUTORIAL_DIR/bin/kubeconfig.yaml"

echo "=== Drasi Server High Risk Containers - Cluster Setup ==="
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

# Create the cluster only if it does not already exist (idempotent re-runs).
if k3d cluster list 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
    echo "k3d cluster '$CLUSTER_NAME' already exists - reusing it."
else
    echo "Creating k3d cluster '$CLUSTER_NAME' (API on 127.0.0.1:$API_PORT)..."
    k3d cluster create "$CLUSTER_NAME" --api-port "$API_PORT" --wait
fi

# Write a kubeconfig Drasi Server can read from the host. k3d points the server
# URL at 0.0.0.0 (or host.docker.internal); normalize it to 127.0.0.1 so the
# Kubernetes source can reach the API from outside the cluster.
echo "Writing kubeconfig to $KUBECONFIG_FILE ..."
k3d kubeconfig get "$CLUSTER_NAME" > "$KUBECONFIG_FILE"
sed -i.bak \
    -e 's#https://0\.0\.0\.0:#https://127.0.0.1:#g' \
    -e 's#https://host\.docker\.internal:#https://127.0.0.1:#g' \
    "$KUBECONFIG_FILE"
rm -f "$KUBECONFIG_FILE.bak"

echo "Deploying demo Pods (my-app-1, my-app-2)..."
kubectl --kubeconfig "$KUBECONFIG_FILE" apply -f "$TUTORIAL_DIR/k8s/my-app.yaml"

echo "Waiting for Pods to be ready..."
kubectl --kubeconfig "$KUBECONFIG_FILE" wait --for=condition=Ready \
    pod/my-app-1 pod/my-app-2 --timeout=120s

echo
echo "Running Pods:"
kubectl --kubeconfig "$KUBECONFIG_FILE" get pods -o wide

echo
echo "=== Cluster setup complete! ==="
echo "  Cluster:    $CLUSTER_NAME"
echo "  Kubeconfig: $KUBECONFIG_FILE"
echo
echo "Next step: run ./scripts/start-server.sh to start Drasi Server"
