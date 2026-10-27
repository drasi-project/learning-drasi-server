param([int]$Id = 101)
$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") reset --id $Id
exit $LASTEXITCODE
