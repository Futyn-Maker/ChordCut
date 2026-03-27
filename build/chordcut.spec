# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ChordCut."""

import glob
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(SPECPATH, '..', 'src'))

from chordcut import __version__, __app_name__, __author__, __description__

# Parse "YYYY.MM.DD[.N]" → (int, int, int, int) for VERSIONINFO
_ver_parts = [int(x) for x in __version__.split('.')]
while len(_ver_parts) < 4:
    _ver_parts.append(0)
_ver_tuple = tuple(_ver_parts)

# Generate Windows VERSIONINFO resource so the OS and assistive tools can
# read the product name and version from the executable's properties.
_version_file = os.path.join(SPECPATH, 'version_info.txt')
with open(_version_file, 'w', encoding='utf-8') as _f:
    _f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_ver_tuple},
    prodvers={_ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{__author__}'),
        StringStruct(u'FileDescription', u'{__description__}'),
        StringStruct(u'FileVersion', u'{__version__}'),
        StringStruct(u'InternalName', u'{__app_name__}'),
        StringStruct(u'LegalCopyright', u'Copyright (c) {__author__}. MIT License.'),
        StringStruct(u'OriginalFilename', u'{__app_name__}.exe'),
        StringStruct(u'ProductName', u'{__app_name__}'),
        StringStruct(u'ProductVersion', u'{__version__}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
""")

# Collect compiled translation catalogs (.mo files only).
locale_root = os.path.join(SPECPATH, '..', 'locale')
locale_datas = []
for mo in glob.glob(os.path.join(locale_root, '*', 'LC_MESSAGES', '*.mo')):
    # Preserve the relative path under locale/, e.g. locale/ru/LC_MESSAGES/
    rel = os.path.relpath(os.path.dirname(mo), os.path.join(SPECPATH, '..'))
    locale_datas.append((mo, rel))

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
    ] + locale_datas,
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
    version=_version_file,
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
