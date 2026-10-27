#!/usr/bin/env bash
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
set -euo pipefail
echo "Released binaries are not used by this tutorial. Building matching local sources."
exec python3 "$(dirname "$0")/demo.py" build "$@"
