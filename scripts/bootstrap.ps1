$ErrorActionPreference = 'Stop'
$repoPath = Split-Path $PSScriptRoot -Parent
$localPath = Join-Path $repoPath '.local'
New-Item -ItemType Directory -Path $localPath -Force | Out-Null
$settingsPath = Join-Path $localPath 'settings.json'
$portfolioPath = Split-Path $repoPath -Parent
$adminSettingsPath = Join-Path $portfolioPath '1/.local/settings.json'
if (-not (Test-Path -LiteralPath $adminSettingsPath)) {
    throw 'Provide an existing PostgreSQL admin connection and create sonda/sonda_test, or use the portfolio local runtime.'
}
$adminSettings = Get-Content -LiteralPath $adminSettingsPath -Raw | ConvertFrom-Json
$adminConnection = [System.Data.Common.DbConnectionStringBuilder]::new()
$adminConnection.set_ConnectionString($adminSettings.connectionString)
$pgAdminHost = [string]$adminConnection.get_Item('Host')
$pgAdminPort = [string]$adminConnection.get_Item('Port')
$pgAdminRole = [string]$adminConnection.get_Item('Username')
$pgAdminDatabase = [string]$adminConnection.get_Item('Database')
if ($pgAdminHost -ne '127.0.0.1' -or $pgAdminPort -ne '55417') {
    throw 'Portfolio bootstrap only targets the private PostgreSQL cluster at 127.0.0.1:55417.'
}
$lastroSettings = Get-Content -LiteralPath (Join-Path $portfolioPath '2/.local/settings.json') -Raw | ConvertFrom-Json
$psqlPath = Join-Path $lastroSettings.postgresBin 'psql.exe'
function New-LocalSecret {
    $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
$settings = if (Test-Path -LiteralPath $settingsPath) {
    Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
} else {
    [pscustomobject]@{ host='127.0.0.1'; port=55417; database='sonda'; username='sonda'; password=(New-LocalSecret); testDatabase='sonda_test'; testUsername='sonda_test'; testPassword=(New-LocalSecret); sessionSecret=(New-LocalSecret); probeSecret=(New-LocalSecret); postgresBin=$lastroSettings.postgresBin }
}
$previousPgPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = [string]$adminConnection.get_Item('Password')
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        $roleProbe = & $psqlPath -h $pgAdminHost -p $pgAdminPort -U $pgAdminRole -d $pgAdminDatabase -Atc "SELECT count(*) FROM pg_roles WHERE rolname IN ('sonda','sonda_test')" 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Private PostgreSQL is not accepting admin connections.' }
        if ([int]$roleProbe -ne 0) { throw 'Sonda roles already exist without local settings; refusing to replace their credentials.' }
    }
    $sqlBatch = @'
\set ON_ERROR_STOP on
SELECT 'CREATE ROLE sonda LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD ''__APP_PASSWORD__''' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sonda')
\gexec
SELECT 'CREATE ROLE sonda_test LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD ''__TEST_PASSWORD__''' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sonda_test')
\gexec
SELECT 'CREATE DATABASE sonda OWNER sonda' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='sonda')
\gexec
SELECT 'CREATE DATABASE sonda_test OWNER sonda_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='sonda_test')
\gexec
REVOKE CONNECT ON DATABASE sonda FROM PUBLIC;
REVOKE CONNECT ON DATABASE sonda_test FROM PUBLIC;
GRANT CONNECT ON DATABASE sonda TO sonda;
GRANT CONNECT ON DATABASE sonda_test TO sonda_test;
'@
    $sqlBatch = $sqlBatch.Replace('__APP_PASSWORD__', $settings.password).Replace('__TEST_PASSWORD__', $settings.testPassword)
    $sqlBatch | & $psqlPath -h $pgAdminHost -p $pgAdminPort -U $pgAdminRole -d $pgAdminDatabase > (Join-Path $localPath 'bootstrap.log') 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Database provisioning failed; diagnostics remain in the private .local/bootstrap.log.' }
    $settings | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding utf8NoBOM
    Write-Output 'Sonda databases and isolated non-superuser roles are configured. Secrets remain in .local/settings.json.'
} finally { $env:PGPASSWORD = $previousPgPassword }
