#!/bin/bash
# Copyright 2026 The Drasi Authors. Licensed under Apache-2.0.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/demo.py" cleanup "$@"
