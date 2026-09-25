# -*- mode: python ; coding: utf-8 -*-
# Majestic Text Helper — PyInstaller (onedir, без консоли, права администратора)
#
# v3.3.0: onedir вместо onefile —
#   • антивирусы намного реже помечают папочную сборку как угрозу;
#   • нет распаковки во временную папку при каждом запуске (старт быстрее);
#   • если антивирус удалил часть файлов — это сразу видно в папке.
# Результат: dist/MajesticTextHelper/MajesticTextHelper.exe (+ _internal).

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
    name="MajesticTextHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    # Запрашивать права администратора при запуске — чтобы глобальные хоткеи
    # и вставка работали, даже если игра запущена от администратора.
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MajesticTextHelper",
)
