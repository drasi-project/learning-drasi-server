$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") start @args
exit $LASTEXITCODE
