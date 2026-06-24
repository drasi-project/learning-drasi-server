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

# Upgrade Pod Script
# Upgrades a running Pod to a different (non-risky) image tag. By default it
# moves my-app-2 from :0.2 to :0.3, so it drops out of the query results and
# disappears from the dashboard.
#
# Usage: upgrade-pod.sh [pod-name] [image]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KUBECONFIG_FILE="${KUBECONFIG_PATH:-$TUTORIAL_DIR/bin/kubeconfig.yaml}"

POD="${1:-my-app-2}"
IMAGE="${2:-ghcr.io/drasi-project/my-app:0.3}"
CONTAINER="${POD_CONTAINER_NAME:-app}"

if [ ! -f "$KUBECONFIG_FILE" ]; then
    echo "Error: kubeconfig not found at $KUBECONFIG_FILE"
    echo "Run ./scripts/setup-cluster.sh first."
    exit 1
fi

echo "Upgrading $POD container '$CONTAINER' to $IMAGE ..."
kubectl --kubeconfig "$KUBECONFIG_FILE" set image "pod/$POD" "$CONTAINER=$IMAGE"

echo "Waiting for $POD to be ready..."
kubectl --kubeconfig "$KUBECONFIG_FILE" wait --for=condition=Ready "pod/$POD" --timeout=120s

echo
echo "Done. If '$IMAGE' is not in the RiskyImage table, $POD disappears from the"
echo "High Risk Containers list on the dashboard at http://localhost:3000."
