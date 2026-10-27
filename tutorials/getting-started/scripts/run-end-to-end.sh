#!/usr/bin/env bash
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
set -euo pipefail
# Requires a completed matching local build; never starts another Cargo build.
exec python3 "$(dirname "$0")/verify_demo.py" "$@"
