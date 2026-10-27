$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") start-demo @args
exit $LASTEXITCODE
