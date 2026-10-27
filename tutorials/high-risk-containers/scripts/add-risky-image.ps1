param(
    [string]$Image = "ghcr.io/drasi-project/my-app:0.2",
    [string]$Reason = "Critical Bug",
    [string]$Mitigation = "Update to latest version",
    [int]$Id = 101
)
$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "demo.py") add-risk $Image $Reason $Mitigation --id $Id
exit $LASTEXITCODE
