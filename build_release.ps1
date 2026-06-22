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

Write-Host "Release created in dist\SSM_Student_Profiling"
