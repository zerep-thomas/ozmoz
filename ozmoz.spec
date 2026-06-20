# -*- mode: python ; coding: utf-8 -*-

# ============================================================
# OZMOZ SPEC - PyInstaller
# ============================================================
from PyInstaller.utils.hooks import collect_all

fw_datas, fw_binaries, fw_hiddenimports = collect_all('faster_whisper')
ort_datas, ort_binaries, ort_hiddenimports = collect_all('onnxruntime')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=fw_binaries + ort_binaries, # <--- MODIFIÉ ICI
    datas=[
        ('src/ui/qml', 'src/ui/qml'),
        ('src/static/audio', 'src/static/audio'),
        ('ffmpeg.exe', '.'),
        ('ffprobe.exe', '.'),  
        ('data', 'data'),
    ] + fw_datas + ort_datas,

    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickControls2',
        
        'groq',
        'groq.resources',
        'groq.types',
        
        'pyaudio',
        'pydub',
        'pydub.utils', 
        
        'win32gui',
        'win32con',
        'win32api',
        
        'numpy',
        
        'uuid',
        'wave',
        'tempfile',
        'threading',
    ] + fw_hiddenimports + ort_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter',
        'PIL',
        'pytest',
        'unittest',
        'pydoc',
        'email.mime',
        'http.server',
        'html',
        'xml',
        'xmlrpc',
        'lib2to3',
        'distutils',
        'setuptools',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ozmoz',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    
    console=False,
    
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    
    icon='src\\ui\\qml\\icons\\app_icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        # 'qml*.dll',
        # 'Qt*.dll',
    ],
    name='ozmoz',
)