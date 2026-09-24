# Copyright 2026 The Drasi Authors.
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

# Install source/otel. Prefer the bash builder (Git Bash / WSL). Docker is used
# to produce the Linux cdylib from drasi-core PR 750.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BashScript = Join-Path $ScriptDir "install-otel-plugin.sh"

if (Get-Command bash -ErrorAction SilentlyContinue) {
    & bash $BashScript
    exit $LASTEXITCODE
}

$TutorialDir = Resolve-Path (Join-Path $ScriptDir "..")
$PluginsDir = if ($env:DRASI_PLUGINS_DIR) { $env:DRASI_PLUGINS_DIR } else { Join-Path $TutorialDir "bin\plugins" }
New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null

$existing = @(
    (Join-Path $PluginsDir "libdrasi_source_otel.so"),
    (Join-Path $PluginsDir "libdrasi_source_otel.dylib"),
    (Join-Path $PluginsDir "drasi_source_otel.dll")
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($existing) {
    Write-Host "source/otel already present: $existing"
    exit 0
}

Write-Host "Error: bash is required to build source/otel from drasi-core PR 750."
Write-Host "Install Git Bash or WSL and re-run, or copy libdrasi_source_otel.* into:"
Write-Host "  $PluginsDir"
exit 1
