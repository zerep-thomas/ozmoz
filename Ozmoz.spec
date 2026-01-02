# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import importlib.util
from PyInstaller.utils.hooks import collect_data_files, collect_all

block_cipher = None

# --- Paths Configuration ---
project_dir = os.getcwd()
src_path = os.path.join(project_dir, 'src')
icon_path = os.path.join(src_path, 'static', 'img', 'icons', 'icon.ico')

# --- DATA FILES/ASSETS ---
# List of (source, destination) tuples for bundling data files
datas = [
    ('src/templates', 'src/templates'),
    ('src/static', 'src/static'),
    ('bin', 'bin'),
    ('README.md', '.'),
    ('LICENSE', '.'),
]

# Collect data files from dependencies
datas += collect_data_files('jaraco.text')
datas += collect_data_files('setuptools')

# --- Workaround for missing Lorem ipsum.txt in setuptools vendor ---
spec_setuptools = importlib.util.find_spec('setuptools')
if spec_setuptools and spec_setuptools.origin:
    setuptools_root = os.path.dirname(spec_setuptools.origin)
    
    # Path to the potentially missing file
    lorem_source = os.path.join(setuptools_root, '_vendor', 'jaraco', 'text', 'Lorem ipsum.txt')
    
    if os.path.exists(lorem_source):
        print(f"--- FIX APPLIED: Including {lorem_source} ---")
        datas.append((lorem_source, os.path.join('setuptools', '_vendor', 'jaraco', 'text')))
    else:
        print("--- WARNING: Could not find 'Lorem ipsum.txt' in setuptools vendor folder ---")

# --- HIDDEN IMPORTS ---
hidden_imports = [
    'keyring.backends',
    'keyring.backends.Windows',
    'win32timezone',
    'pyaudio',
    'mss',
    'PySide6',
    'jaraco.text',
    'inflect',
    'pkg_resources.extern'
]

# --- Analysis Phase ---
a = Analysis(
    ['app.py'],
    pathex=[project_dir, src_path],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude large or unnecessary standard libraries to reduce size
    excludes=['PyQt5', 'tkinter', 'matplotlib', 'notebook', 'scipy', 'pandas'], 
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# --- PYZ Optimization Phase ---
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher, optimize=1)

# --- Executable Phase ---
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Ozmoz', # Product Name
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True, # Compress the final executable
    console=False, # Create a windowed (GUI) application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    version=None,
)

# --- COLLECT (Bundle/Output Folder) Phase ---
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Ozmoz', # Output folder name
)