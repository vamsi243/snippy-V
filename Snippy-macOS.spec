# -*- mode: python ; coding: utf-8 -*-

import importlib.util

from PyInstaller.utils.hooks import collect_all, collect_submodules

hiddenimports = [
    'mcp_server',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'pynput.keyboard',
    'pynput.mouse',
    'PIL._tkinter_finder',
    'lxml._elementpath',
]

datas = [
    ('assets', 'assets'),
    ('ocr', 'ocr'),
]

binaries = []


def collect_package(package_name):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    except Exception:
        return
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)


def collect_mcp_protocol_modules():
    hiddenimports.extend(
        collect_submodules(
            'mcp',
            filter=lambda name: not name.startswith('mcp.cli'),
        )
    )


rapidocr_spec = importlib.util.find_spec('rapidocr')
if rapidocr_spec and rapidocr_spec.submodule_search_locations:
    rapidocr_dir = list(rapidocr_spec.submodule_search_locations)[0]
    datas.append((rapidocr_dir, 'rapidocr'))

for package in (
    'fastmcp',
    'uvicorn',
    'starlette',
    'sse_starlette',
    'anyio',
    'httpx',
    'httpx_sse',
    'pydantic',
    'pydantic_core',
    'jsonschema',
    'jsonschema_path',
    'rich',
    'click',
    'websockets',
    'watchfiles',
):
    collect_package(package)

collect_mcp_protocol_modules()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='Snippy',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='Snippy',
)

app = BUNDLE(
    coll,
    name='Snippy.app',
    bundle_identifier='com.snippy.app',
)
