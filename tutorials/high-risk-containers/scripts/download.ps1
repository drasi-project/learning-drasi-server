$ErrorActionPreference = "Stop"
Write-Host "Released artifacts are not compatible with this tutorial. Building local Server/Core instead."
python (Join-Path $PSScriptRoot "demo.py") build @args
exit $LASTEXITCODE
