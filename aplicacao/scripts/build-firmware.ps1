$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$pythonExe=Join-Path $projectRoot '.venv-build\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe='E:\Infineon\.venv-build\Scripts\python.exe' }
$env:PLATFORMIO_CORE_DIR='E:\Infineon\.pio-core'
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY='No'
& $pythonExe -m platformio run --project-dir (Join-Path $projectRoot 'firmware') -e pico
if ($LASTEXITCODE -ne 0) { throw 'Build retornou erro; veja o log.' }
$destination=Join-Path $projectRoot 'release\firmware'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'firmware\.pio\build\pico\firmware.uf2') -Destination (Join-Path $destination 'InfineonPico.uf2')
