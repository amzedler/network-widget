# -*- mode: python ; coding: utf-8 -*-

VERSION = "1.1"
APP_NAME = f"Network Widget {VERSION}"

a = Analysis(
    ['network_widget.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['rumps'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f'{APP_NAME}.app',
    bundle_identifier='com.local.network-widget',
    info_plist={
        'LSUIElement': True,
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleVersion': VERSION,
    },
)
