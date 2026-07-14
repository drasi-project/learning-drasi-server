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

# Reset Script (Windows)
# Returns the demo to its starting state: every order back to 'preparing' and
# every vehicle back to 'Parking'.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TutorialDir = Split-Path -Parent $ScriptDir

$EnvFile = Join-Path $TutorialDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
        }
    }
}

$MysqlRootPw = if ($env:MYSQL_ROOT_PASSWORD) { $env:MYSQL_ROOT_PASSWORD } else { "root_admin" }
$MysqlDb = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "PhysicalOperations" }

Write-Host "Resetting orders to 'preparing' (PostgreSQL)..."
docker exec curbside-pickup-postgres psql -v ON_ERROR_STOP=1 -U drasi_user -d RetailOperations -c "UPDATE orders SET status='preparing';"

Write-Host "Resetting vehicles to 'Parking' (MySQL)..."
docker exec -e MYSQL_PWD=$MysqlRootPw curbside-pickup-mysql mysql -uroot -e "UPDATE $MysqlDb.vehicles SET location='Parking';"

Write-Host ""
Write-Host "Reset complete. Both dashboards should now be empty."
