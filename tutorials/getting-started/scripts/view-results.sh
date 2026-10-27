#!/usr/bin/env bash
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
set -euo pipefail
if [[ "${1:-}" == status ]]; then
    exec python3 "$(dirname "$0")/demo.py" check
fi
exec python3 "$(dirname "$0")/demo.py" results "$@"
