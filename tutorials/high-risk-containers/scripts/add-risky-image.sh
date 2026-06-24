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

# Add Risky Image Script
# Marks a new container image tag as high risk by inserting a row into the
# RiskyImage table. By default it flags my-app:0.2 (which my-app-2 is running),
# so that Pod immediately appears in the query results and on the dashboard.
#
# Usage: add-risky-image.sh [image] [reason] [mitigation]

set -e

IMAGE="${1:-ghcr.io/drasi-project/my-app:0.2}"
REASON="${2:-Critical Bug}"
MITIGATION="${3:-Update to latest version}"
ID="${RISKY_IMAGE_ID:-101}"

echo "Flagging image as high risk:"
echo "  Image:      $IMAGE"
echo "  Reason:     $REASON"
echo "  Mitigation: $MITIGATION"
echo

printf "INSERT INTO \"RiskyImage\" (\"Id\", \"Image\", \"Reason\", \"Mitigation\") VALUES (%s, '%s', '%s', '%s') ON CONFLICT (\"Id\") DO UPDATE SET \"Image\"=EXCLUDED.\"Image\", \"Reason\"=EXCLUDED.\"Reason\", \"Mitigation\"=EXCLUDED.\"Mitigation\";" \
    "$ID" "$IMAGE" "$REASON" "$MITIGATION" \
    | docker exec -i high-risk-containers-postgres \
        psql -v ON_ERROR_STOP=1 -U drasi_user -d high_risk_containers

echo
echo "Done. Watch the dashboard at http://localhost:3000 - any running container"
echo "with image '$IMAGE' now appears in the High Risk Containers list."
