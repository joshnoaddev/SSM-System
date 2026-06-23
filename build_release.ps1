$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
& ".venv\Scripts\python.exe" -m unittest discover -s tests -v
& ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm SSM_Student_Profiling.spec

$version = & ".venv\Scripts\python.exe" -c "from office_app.services.updater_service import UpdaterService; print(UpdaterService.CURRENT_VERSION)"
$zipPath = "dist\SSM_Student_Profiling_v$version.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath "dist\SSM_Student_Profiling" -DestinationPath $zipPath -Force

Write-Host "Release folder created in dist\SSM_Student_Profiling"
Write-Host "Release zip created at $zipPath"
