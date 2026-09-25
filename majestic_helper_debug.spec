# -*- mode: python ; coding: utf-8 -*-
# Majestic Text Helper — диагностическая сборка (консоль видна).
#
# Если обычный exe не открывается и error.log пуст — запустите
# dist/MajesticTextHelper_debug/MajesticTextHelper_debug.exe:
# откроется чёрное окно консоли, где будет напечатана точная причина.

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=["keyboard"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MajesticTextHelper_debug",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MajesticTextHelper_debug",
)
