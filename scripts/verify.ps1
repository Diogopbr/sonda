$ErrorActionPreference = 'Stop'
$repoPath = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements-dev.txt first.' }
if (-not $env:SONDA_TEST_DATABASE_URL) { throw 'Set SONDA_TEST_DATABASE_URL to the isolated local sonda_test database.' }
function Invoke-Check {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Verification failed: $Program $($Arguments -join ' ')" }
}
Push-Location $repoPath
try {
    Invoke-Check $pythonPath @('-m', 'ruff', 'check', 'sonda', 'scripts', 'tests')
    Invoke-Check $pythonPath @('-m', 'ruff', 'format', '--check', 'sonda', 'scripts', 'tests')
    Invoke-Check $pythonPath @('-m', 'mypy')
    Invoke-Check $pythonPath @('-m', 'pytest', '-q', '--tb=short')
    Push-Location (Join-Path $repoPath 'frontend')
    try {
        Invoke-Check 'npm' @('run', 'format:check')
        Invoke-Check 'npm' @('test')
        Invoke-Check 'npm' @('run', 'build')
        Invoke-Check 'npm' @('run', 'test:e2e')
    } finally { Pop-Location }
    Invoke-Check 'git' @('diff', '--check')
} finally { Pop-Location }
