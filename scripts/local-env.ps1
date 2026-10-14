param([switch]$Test)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path $PSScriptRoot -Parent
$settingsPath = Join-Path $repoPath '.local/settings.json'
if (-not (Test-Path -LiteralPath $settingsPath)) { throw 'Run scripts/bootstrap.ps1 or provide your own PostgreSQL environment.' }
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
$databaseName = if ($Test) { $settings.testDatabase } else { $settings.database }
$databaseRole = if ($Test) { $settings.testUsername } else { $settings.username }
$databasePassword = if ($Test) { $settings.testPassword } else { $settings.password }
$env:DATABASE_URL = 'postgresql://' + [Uri]::EscapeDataString($databaseRole) + ':' + [Uri]::EscapeDataString($databasePassword) + '@' + $settings.host + ':' + $settings.port + '/' + $databaseName
$env:SONDA_ENV = if ($Test) { 'test' } else { 'development' }
$env:DB_TLS = 'false'
$env:SESSION_SECRET = $settings.sessionSecret
$env:PROBE_SECRET = $settings.probeSecret
$env:APP_URL = if ($Test) { 'http://127.0.0.1:5097' } else { 'http://127.0.0.1:5095' }
$env:PORT = if ($Test) { '5097' } else { '5095' }
$env:SONDA_DEMO_ENABLED = 'true'
$env:SONDA_LOGIN_ENABLED = 'false'
$env:TRUST_VERCEL_INGRESS = 'false'
$env:PATH = (Join-Path $repoPath '.venv/Scripts') + ';' + (Join-Path (Split-Path $repoPath -Parent) '.tools/node') + ';' + $env:PATH
if ($Test) { $env:SONDA_TEST_DATABASE_URL = $env:DATABASE_URL } else { Remove-Item Env:SONDA_TEST_DATABASE_URL -ErrorAction SilentlyContinue }
