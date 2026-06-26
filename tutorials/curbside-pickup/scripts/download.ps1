# Copyright 2025 The Drasi Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    Write-Host "Drasi Server installed to $ServerPath"
} catch {
    Write-Host "Error: Failed to verify installation"
    Write-Host $_.Exception.Message
    exit 1
}
