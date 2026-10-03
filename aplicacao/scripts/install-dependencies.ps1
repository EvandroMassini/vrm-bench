$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv-build\Scripts\python.exe')) {
    py -3 -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.11 ou superior.' }
}
& .\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Download/instalacao falhou. Verifique conectividade TLS ao PyPI.' }
