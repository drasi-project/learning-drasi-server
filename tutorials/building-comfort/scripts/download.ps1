# Drasi Server Install Script for Windows
# Downloads the Windows x64 drasi-server binary.

$ErrorActionPreference = "Stop"

# TEMPORARY: pinned to the 0.2.0-preview pre-release (plugin-sdk 0.9.0) so the
# reaction/dashboard plugin loads. Revert to ".../releases/latest/download"
# once a stable sdk-0.9.0 drasi-server is released.
$RepoUrl = "https://github.com/drasi-project/drasi-server/releases/download/0.2.0-preview"
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
