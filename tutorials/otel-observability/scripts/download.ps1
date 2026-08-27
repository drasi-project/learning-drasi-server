# Drasi Server Install Script for Windows
# Downloads the Windows x64 drasi-server binary.

$ErrorActionPreference = "Stop"

# Pin Drasi Server. 0.2.2 ships plugin-sdk 0.11, which loads source/otel 0.1.0.
$ServerVersion = if ($env:DRASI_SERVER_VERSION) { $env:DRASI_SERVER_VERSION } else { "0.2.2" }
$RepoUrl = "https://github.com/drasi-project/drasi-server/releases/download/$ServerVersion"
$InstallDir = "bin"

$Arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture

if ($Arch -ne "X64") {
    Write-Host "Warning: Detected $Arch architecture. Only x64 binaries are available."
    Write-Host "The download will proceed with the x64 binary."
}

Write-Host "Detected: Windows ($Arch)"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$ServerBinary = "drasi-server-x86_64-windows-msvc.exe"
$ServerPath = Join-Path $InstallDir "drasi-server.exe"
Write-Host "Downloading: $ServerBinary"
try {
    Invoke-WebRequest -Uri "$RepoUrl/$ServerBinary" -OutFile $ServerPath -UseBasicParsing
} catch {
    Write-Host "Error: Failed to download $ServerBinary"
    Write-Host $_.Exception.Message
    exit 1
}

Unblock-File -Path $ServerPath

$pluginsDir = Join-Path $InstallDir "plugins"
if (Test-Path $pluginsDir) {
    Write-Host "Clearing $pluginsDir (re-fetched on next server start)..."
    Get-ChildItem -Path $pluginsDir -Filter "libdrasi_*" -ErrorAction SilentlyContinue | Remove-Item -Force
    $lock = Join-Path $pluginsDir "plugins.lock"
    if (Test-Path $lock) { Remove-Item -Force $lock }
}

Write-Host ""
Write-Host "Verifying installation..."
try {
    & $ServerPath --version
    Write-Host ""
    Write-Host "✅ Drasi Server installed to $ServerPath"
} catch {
    Write-Host "Error: Failed to verify installation"
    Write-Host $_.Exception.Message
    exit 1
}
