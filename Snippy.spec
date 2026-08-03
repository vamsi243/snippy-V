# -*- mode: python ; coding: utf-8 -*-

import os

site_packages = os.path.join(os.getcwd(), '.venv', 'Lib', 'site-packages')
rapidocr_dir = os.path.join(site_packages, 'rapidocr')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('ocr', 'ocr'),
        (rapidocr_dir, 'rapidocr'),
    ],
    hiddenimports=[
        'rapidocr',
        'onnxruntime',
        'pynput.keyboard',
        'pynput.mouse',
        'PIL._tkinter_finder',
        'lxml._elementpath',
        'reportlab',
        'pandas',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Snippy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\logo.png'],
)
