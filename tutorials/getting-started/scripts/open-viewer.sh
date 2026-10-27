#!/usr/bin/env bash
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
set -euo pipefail
echo "Open http://127.0.0.1:${VIEWER_PORT:-5173}; Ctrl+C stops this viewer."
exec python3 -m http.server "${VIEWER_PORT:-5173}" --bind 127.0.0.1 \
    --directory "$(dirname "$0")/../viewer"
