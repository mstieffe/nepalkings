# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Nepal Kings.

Usage:
    cd nepal_kings
    pyinstaller nepal_kings.spec

Produces:
    dist/NepalKings          (macOS .app or Linux binary)
    dist/NepalKings.exe      (Windows)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Paths
_DIR = os.path.abspath('.')
_IMG_DIR = os.path.join(_DIR, 'img')
_CONFIG_DIR = os.path.join(_DIR, 'config')
_GAME_DIR = os.path.join(_DIR, 'game')
_UTILS_DIR = os.path.join(_DIR, 'utils')
_ICON_DIR = os.path.join(_IMG_DIR, 'app_icon')

# Platform-specific icon
if sys.platform == 'darwin':
    _ICON = os.path.join(_ICON_DIR, 'app_icon.icns')
elif sys.platform == 'win32':
    _ICON = os.path.join(_ICON_DIR, 'app_icon.ico')
else:
    _ICON = None

# Collect all Python submodules so dynamic imports work
hidden_imports = (
    collect_submodules('config') +
    collect_submodules('game') +
    collect_submodules('utils')
)

a = Analysis(
    ['main.py'],
    pathex=[_DIR],
    binaries=[],
    datas=[
        # Bundle the entire img/ tree
        (_IMG_DIR, 'img'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'numpy.testing'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NepalKings',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX can corrupt Pygame/SDL DLLs on Windows
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed app, no terminal
    disable_windowed_traceback=False,
    argv_emulation=False,  # MUST be False — True crashes on modern macOS
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)

# macOS .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='NepalKings.app',
        icon=_ICON,
        bundle_identifier='com.nepalkings.game',
        info_plist={
            'CFBundleShortVersionString': '0.1.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
        },
    )
