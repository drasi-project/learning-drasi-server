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

# Reset Script
# Returns the demo to its starting state: removes the image added by
# add-risky-image.sh and puts the Pods back on their original tags
# (my-app-1 -> :0.1, my-app-2 -> :0.2).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KUBECONFIG_FILE="${KUBECONFIG_PATH:-$TUTORIAL_DIR/bin/kubeconfig.yaml}"
ID="${RISKY_IMAGE_ID:-101}"

echo "Removing the added high risk image (Id=$ID)..."
printf "DELETE FROM \"RiskyImage\" WHERE \"Id\" = %s;" "$ID" \
    | docker exec -i high-risk-containers-postgres \
        psql -v ON_ERROR_STOP=1 -U drasi_user -d high_risk_containers

if [ -f "$KUBECONFIG_FILE" ]; then
    echo "Restoring Pod image tags (my-app-1 -> :0.1, my-app-2 -> :0.2)..."
    kubectl --kubeconfig "$KUBECONFIG_FILE" set image pod/my-app-1 app=ghcr.io/drasi-project/my-app:0.1 || true
    kubectl --kubeconfig "$KUBECONFIG_FILE" set image pod/my-app-2 app=ghcr.io/drasi-project/my-app:0.2 || true
    kubectl --kubeconfig "$KUBECONFIG_FILE" wait --for=condition=Ready pod/my-app-1 pod/my-app-2 --timeout=120s || true
else
    echo "Note: kubeconfig not found at $KUBECONFIG_FILE - skipping Pod restore."
fi

echo
echo "Reset complete. Only my-app-1 (:0.1) should remain flagged."
