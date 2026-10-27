$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") cluster @args
exit $LASTEXITCODE
