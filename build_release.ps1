$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python build environment."
    }
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Could not update pip."
}
& ".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the build requirements."
}
& ".venv\Scripts\python.exe" -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed; the release was not built."
}

if (Get-Process -Name "SSM_Student_Profiling" -ErrorAction SilentlyContinue) {
    throw "Close every running SSM Student Profiling window before building."
}

& ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm SSM_Student_Profiling.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed; no release archive was created."
}

$version = & ".venv\Scripts\python.exe" -c "from office_app.services.updater_service import UpdaterService; print(UpdaterService.CURRENT_VERSION)"
$exePath = "dist\SSM_Student_Profiling.exe"
$zipPath = "dist\SSM_Student_Profiling_v$version.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $exePath -DestinationPath $zipPath -Force

Write-Host "Release executable created at $exePath"
Write-Host "Release zip created at $zipPath"
