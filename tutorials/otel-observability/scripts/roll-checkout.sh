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

# Optional helper. The tutorial drive step shows these same kubectl commands.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export KUBECONFIG="${KUBECONFIG_PATH:-$TUTORIAL_DIR/bin/kubeconfig.yaml}"
VERSION="${1:-v42}"

if ! printf '%s' "$VERSION" | grep -Eq '^v[0-9]+$'; then
    echo "Usage: $0 [v41|v42]"
    exit 1
fi

if [ ! -f "$KUBECONFIG" ]; then
    echo "Error: kubeconfig not found at $KUBECONFIG"
    echo "Run ./scripts/setup-cluster.sh first."
    exit 1
fi

kubectl set image deployment/checkout "app=otel-observability-checkout:${VERSION}"
kubectl label deployment/checkout "version=${VERSION}" --overwrite
kubectl rollout status deployment/checkout --timeout=120s
