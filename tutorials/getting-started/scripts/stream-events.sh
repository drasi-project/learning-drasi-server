#!/usr/bin/env bash
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
set -euo pipefail
echo "Listening to an existing SSE reaction. This does not fetch a snapshot or create a reaction."
exec curl --fail --show-error --no-buffer \
    "${SSE_URL:-http://127.0.0.1:8181/events}"
