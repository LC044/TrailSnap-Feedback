[CmdletBinding()]
param(
    [string]$EnvFile = 'tests/.env.test',
    [ValidateSet('unit')][string]$Layer = 'unit',
    [ValidateSet('all', 'smoke')][string]$Level = 'all',
    [ValidateSet('requirement-platform', 'server', 'web', 'all')][string]$Component = 'all'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repoRoot $EnvFile }
if (-not (Test-Path -LiteralPath $configPath)) {
    if ($EnvFile -ne 'tests/.env.test') { throw "Test environment file does not exist: $configPath" }
    Copy-Item -LiteralPath (Join-Path $repoRoot 'tests/.env.test.example') -Destination $configPath
}
foreach ($line in Get-Content -LiteralPath $configPath) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), 'Process')
    }
}
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
try {
    if ($Component -in @('requirement-platform', 'server', 'all')) {
        Push-Location (Join-Path $repoRoot 'server')
        try {
            Invoke-Checked 'uv' @('sync', '--frozen')
            Invoke-Checked 'uv' @('run', 'python', '-m', 'pytest', 'tests')
        } finally { Pop-Location }
    }
    if ($Component -in @('web', 'all')) {
        Push-Location (Join-Path $repoRoot 'web')
        try {
            Invoke-Checked 'npm' @('test')
            Invoke-Checked 'npm' @('run', 'build')
        } finally { Pop-Location }
    }
} catch { Write-Error $_; exit 1 }
