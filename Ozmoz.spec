# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Paths
project_dir = os.getcwd()
src_path = os.path.join(project_dir, 'src')
icon_path = os.path.join(src_path, 'static', 'img', 'icons', 'icon.ico')

# Hidden imports
hidden_imports = [
    'keyring.backends',
    'keyring.backends.Windows',
    'win32timezone',
    'pyaudio',
    'mss',
    'PySide6',
]

# Data files
datas = [
    ('src/templates', 'src/templates'),
    ('src/static', 'src/static'),
    ('README.md', '.'),
    ('LICENSE', '.'),
]

# Analysis
a = Analysis(
    ['app.py'],
    pathex=[project_dir, src_path],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'tkinter', 'matplotlib', 'notebook', 'scipy', 'pandas'], 
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Optimization
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher, optimize=1)

# Executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Ozmoz',
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
    icon=icon_path,
    version=None,
)

# Output folder
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Ozmoz',
)
