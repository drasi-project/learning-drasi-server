# Local matching-build compatibility entry point.
$ErrorActionPreference = "Stop"
& python (Join-Path $PSScriptRoot "demo.py") compat $PSCommandPath @args
exit $LASTEXITCODE
