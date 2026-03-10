# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ChordCut."""

import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(SPECPATH, '..', 'src'))

# Find the libmpv DLL
libmpv_path = None
libmpv_dir = os.path.join(SPECPATH, '..', 'resources', 'libmpv')

for name in ['mpv-2.dll', 'libmpv-2.dll', 'mpv-1.dll']:
    path = os.path.join(libmpv_dir, name)
    if os.path.exists(path):
        libmpv_path = (path, '.')
        print(f"Found libmpv: {path}")
        break

if not libmpv_path:
    print("WARNING: libmpv DLL not found in resources/libmpv/")
    print("Download from: https://sourceforge.net/projects/mpv-player-windows/files/libmpv/")
    # Continue anyway - user might add it later
    binaries = []
else:
    binaries = [libmpv_path]

a = Analysis(
    [os.path.join(SPECPATH, '..', 'src', 'chordcut', '__main__.py')],
    pathex=[os.path.join(SPECPATH, '..', 'src')],
    binaries=binaries,
    datas=[
        (os.path.join(SPECPATH, '..', 'resources', 'chordcut.ico'), '.'),
    ],
    hiddenimports=[
        'wx',
        'wx._core',
        'wx._adv',
        'wx._html',
        'mpv',
        'jellyfin_apiclient_python',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'cv2',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ChordCut',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, '..', 'resources', 'chordcut.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ChordCut',
)
