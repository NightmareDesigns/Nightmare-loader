# nightmare-loader.spec
# PyInstaller spec file for building a standalone Windows executable.
#
# Usage (run from the repo root on Windows or in a Windows PyInstaller env):
#
#   pip install pyinstaller
#   pyinstaller nightmare-loader.spec
#
# The resulting standalone exe is placed in  dist\nightmare-loader.exe
# (single-file bundle).  Run it as:
#
#   dist\nightmare-loader.exe ui           # open web UI
#   dist\nightmare-loader.exe --help       # CLI help

import sys
from pathlib import Path

block_cipher = None

# Collect the non-Python data files shipped with the package
added_files = [
    (str(Path("nightmare_loader/ui")),    "nightmare_loader/ui"),
    (str(Path("nightmare_loader/theme")), "nightmare_loader/theme"),
    (str(Path("nightmare_loader/assets")),"nightmare_loader/assets"),
]

a = Analysis(
    ["nightmare_loader/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        "nightmare_loader.cli",
        "nightmare_loader.server",
        "nightmare_loader.drive",
        "nightmare_loader.grub",
        "nightmare_loader.iso",
        "nightmare_loader.launcher",
        "nightmare_loader.distros",
        "click",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="nightmare-loader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # keep console for CLI output; GUI via browser
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Request elevation via UAC manifest so the exe always runs as admin
    uac_admin=True,
)
