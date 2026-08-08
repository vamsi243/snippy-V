# -*- mode: python ; coding: utf-8 -*-

import os
import importlib.util

datas = [
    ('assets', 'assets'),
    ('ocr', 'ocr'),
]

# Dynamically locate rapidocr package directory if installed
rapidocr_spec = importlib.util.find_spec('rapidocr')
if rapidocr_spec and rapidocr_spec.submodule_search_locations:
    rapidocr_dir = list(rapidocr_spec.submodule_search_locations)[0]
    datas.append((rapidocr_dir, 'rapidocr'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    icon=['assets/logo.png'],
    version='file_version_info.txt',
)
