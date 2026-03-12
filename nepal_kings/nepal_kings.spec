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

# Windows version info (improves SmartScreen reputation)
_WIN_VERSION_INFO = None
if sys.platform == 'win32':
    try:
        # version_info.py is next to this spec file
        sys.path.insert(0, os.path.dirname(os.path.abspath(SPECPATH)) if 'SPECPATH' in dir() else os.path.abspath('.'))
        from version_info import VSVersionInfo
        _WIN_VERSION_INFO = VSVersionInfo
    except Exception:
        pass

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
        # Bundle img/ subdirectories individually to exclude unused ones
        # (figures_old/ and old_cards/ are not used at runtime)
        (os.path.join(_IMG_DIR, '_button'),        os.path.join('img', '_button')),
        (os.path.join(_IMG_DIR, 'app_icon'),       os.path.join('img', 'app_icon')),
        (os.path.join(_IMG_DIR, 'background'),     os.path.join('img', 'background')),
        (os.path.join(_IMG_DIR, 'battle'),         os.path.join('img', 'battle')),
        (os.path.join(_IMG_DIR, 'button'),         os.path.join('img', 'button')),
        (os.path.join(_IMG_DIR, 'cards'),          os.path.join('img', 'cards')),
        (os.path.join(_IMG_DIR, 'dialogue_box'),   os.path.join('img', 'dialogue_box')),
        (os.path.join(_IMG_DIR, 'figures'),        os.path.join('img', 'figures')),
        (os.path.join(_IMG_DIR, 'game_button'),    os.path.join('img', 'game_button')),
        (os.path.join(_IMG_DIR, 'glow'),           os.path.join('img', 'glow')),
        (os.path.join(_IMG_DIR, 'icons'),          os.path.join('img', 'icons')),
        (os.path.join(_IMG_DIR, 'menu_button'),    os.path.join('img', 'menu_button')),
        (os.path.join(_IMG_DIR, 'new_cards'),      os.path.join('img', 'new_cards')),
        (os.path.join(_IMG_DIR, 'resource_icons'), os.path.join('img', 'resource_icons')),
        (os.path.join(_IMG_DIR, 'slot_icons'),     os.path.join('img', 'slot_icons')),
        (os.path.join(_IMG_DIR, 'spells'),         os.path.join('img', 'spells')),
        (os.path.join(_IMG_DIR, 'status_icons'),   os.path.join('img', 'status_icons')),
        (os.path.join(_IMG_DIR, 'sub_screen'),     os.path.join('img', 'sub_screen')),
        (os.path.join(_IMG_DIR, 'suits'),          os.path.join('img', 'suits')),
        (os.path.join(_IMG_DIR, 'utils'),          os.path.join('img', 'utils')),
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

# Windows: use onedir mode to avoid zlib decompression failures with large assets.
# macOS/Linux: use onefile mode (single binary / .app bundle).
_ONEDIR = sys.platform == 'win32' or os.environ.get('PYINSTALLER_ONEDIR') == '1'

if _ONEDIR:
    # ── One-directory mode (Windows) ──────────────────────────────
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='NepalKings',
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
        icon=_ICON,
        version=_WIN_VERSION_INFO,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='NepalKings',
    )
else:
    # ── One-file mode (macOS / Linux) ─────────────────────────────
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
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
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
