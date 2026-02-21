# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import importlib.util
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

project_dir = os.getcwd()
src_path = os.path.join(project_dir, 'src')
icon_path = os.path.join(src_path, 'static', 'img', 'icons', 'icon.ico')

datas = [
    ('src/templates', 'src/templates'),
    ('src/static', 'src/static'),
    ('src/modules/models.json', 'src/modules'),
    ('bin', 'bin'),
    ('README.md', '.'),
    ('LICENSE', '.'),
]

datas += collect_data_files('jaraco.text')
datas += collect_data_files('setuptools')

spec_setuptools = importlib.util.find_spec('setuptools')
if spec_setuptools and spec_setuptools.origin:
    setuptools_root = os.path.dirname(spec_setuptools.origin)
    lorem_source = os.path.join(setuptools_root, '_vendor', 'jaraco', 'text', 'Lorem ipsum.txt')
    if os.path.exists(lorem_source):
        datas.append((lorem_source, os.path.join('setuptools', '_vendor', 'jaraco', 'text')))

hidden_imports = [
    'keyring.backends',
    'keyring.backends.Windows',
    'win32timezone',
    'pyaudio',
    'mss',
    'jaraco.text',
    'inflect',
    'pkg_resources.extern',
    'pynput.keyboard._win32',
    'pynput.mouse._win32',
]

excludes = [
    'PySide6', 'PyQt5', 'PyQt6', 'shiboken6',
    'tkinter', 'matplotlib', 'notebook', 'IPython',
    'scipy', 'pandas', 'numpy.testing',
    'torch', 'tensorflow', 'tensorboard', 'keras',
    'pytest', 'unittest'
]

a = Analysis(
    ['app.py'],
    pathex=[project_dir, src_path],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes, 
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher, optimize=2)

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