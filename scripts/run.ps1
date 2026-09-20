[CmdletBinding()]
param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $bootstrapPython = Join-Path $env:USERPROFILE 'scoop/apps/python/current/python.exe'
    if (-not (Test-Path -LiteralPath $bootstrapPython)) { $bootstrapPython = 'python' }
    & $bootstrapPython -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente Python' }
    & $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements.lock')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências' }
}
$env:IMOVEL_PORT = [string]$Port
& $pythonPath (Join-Path $projectRoot 'run.py')
exit $LASTEXITCODE
