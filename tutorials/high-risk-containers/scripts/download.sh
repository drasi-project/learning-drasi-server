#!/usr/bin/env bash
set -euo pipefail
echo "Released artifacts are not compatible with this tutorial. Building local Server/Core instead."
exec python3 "$(dirname "$0")/demo.py" build "$@"
