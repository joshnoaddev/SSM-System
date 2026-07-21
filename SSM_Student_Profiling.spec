# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('database', 'database'),
        ('DEPLOYMENT.md', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6.QtWebEngine', 
        'PyQt6.QtWebEngineCore', 
        'PyQt6.QtWebEngineWidgets', 
        'PyQt6.QtNetwork', 
        'PyQt6.QtQml', 
        'PyQt6.QtQuick', 
        'PyQt6.QtSql', 
        'PyQt6.QtTest', 
        'PyQt6.QtXml', 
        'PyQt6.QtBluetooth', 
        'PyQt6.QtPositioning', 
        'PyQt6.QtSensors', 
        'PyQt6.QtMultimedia', 
        'PyQt6.QtMultimediaWidgets', 
        'PyQt6.QtWebChannel', 
        'PyQt6.QtWebSockets'
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SSM_Student_Profiling',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
