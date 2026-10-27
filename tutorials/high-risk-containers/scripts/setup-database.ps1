$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") database @args
exit $LASTEXITCODE
