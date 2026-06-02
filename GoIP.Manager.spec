# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files # <-- Add this line

# Collect every hidden component of plyer automatically
plyer_submodules = collect_submodules('plyer')
plyer_datas = collect_data_files('plyer')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('installer_files/icons', 'icons')] + plyer_datas, # <-- Combine plyer files here
    hiddenimports=['selenium.webdriver.edge.webdriver'] + plyer_submodules, # <-- Combine submodules here
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='GoIP.Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
