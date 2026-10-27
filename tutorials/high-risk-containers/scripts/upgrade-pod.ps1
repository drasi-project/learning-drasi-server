param(
    [string]$Pod = "my-app-2",
    [string]$Image = "ghcr.io/drasi-project/my-app:0.3",
    [string]$Container = "app"
)
$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") upgrade $Pod $Image --container $Container
exit $LASTEXITCODE
