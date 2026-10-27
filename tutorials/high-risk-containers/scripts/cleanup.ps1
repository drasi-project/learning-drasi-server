param([switch]$RemoveVolumes)
$ErrorActionPreference = "Stop"
$arguments = @("cleanup")
if ($RemoveVolumes) { $arguments += "--volumes" }
python (Join-Path $PSScriptRoot "demo.py") @arguments
exit $LASTEXITCODE
