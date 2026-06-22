@echo off
REM ── SSM Student Profiling System — Windows EXE build script ──────────────
REM Run this from the folder that contains app.py and the assets\ folder.

echo Installing/updating build requirements...
pip install --upgrade pyqt6 pandas openpyxl supabase pyinstaller

echo.
echo Building SSM_Student_Profiling.exe ...
pyinstaller --noconfirm --onedir --windowed ^
    --name "SSM_Student_Profiling" ^
    --add-data "assets;assets" ^
    app.py

echo.
echo Done. Your app is in: dist\SSM_Student_Profiling\
echo Copy the ENTIRE "SSM_Student_Profiling" folder to the other PC -
echo do not copy just the .exe by itself.
pause