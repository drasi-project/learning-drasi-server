# Copyright 2026 The Drasi Authors. Licensed under Apache-2.0.
$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") reset @args
exit $LASTEXITCODE
