$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv-build\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe='E:\Infineon\.venv-build\Scripts\python.exe' }
& $pythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testes falharam.' }
& $pythonExe -m PyInstaller --noconfirm --distpath release/desktop --workpath work/pyinstaller InfineonBench.spec
if ($LASTEXITCODE -ne 0) { throw 'Build falhou.' }
$exe = Join-Path $projectRoot 'release\desktop\InfineonBench\InfineonBench.exe'
$report = Join-Path $projectRoot 'work\packaged-test.json'
$env:QT_QPA_PLATFORM = 'windows'
$p = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $report + '"')) -WindowStyle Hidden -PassThru
if (-not $p.WaitForExit(20000)) { Stop-Process -Id $p.Id; throw 'Timeout do autoteste.' }
$p.Refresh()
if ($p.ExitCode -ne 0) { throw 'Autoteste do EXE falhou. Consulte %TEMP%\InfineonBench-error.log.' }
Get-FileHash -LiteralPath $exe -Algorithm SHA256
