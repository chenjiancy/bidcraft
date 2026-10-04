# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec：将 sidecar/FastAPI 应用打包为独立 exe。
用法：
  uv run pyinstaller sidecar/bidcraft-sidecar.spec
"""

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# RapidOCR：收集包内 ONNX 模型、config.yaml/default_models.yaml 等数据与子模块
_rapid_datas, _rapid_binaries, _rapid_hidden = collect_all('rapidocr')

a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=_rapid_binaries,
    datas=[
        ('app/db/alembic', 'app/db/alembic'),
        ('alembic.ini', '.'),
    ]
    + _rapid_datas,
    hiddenimports=[
        'rapidocr',
        'onnxruntime',
        'cv2',
    ]
    + _rapid_hidden
    + [
        'uvicorn.loops.auto',
        'sqlalchemy.dialects.sqlite',
        'docxtpl',
        'pymupdf',
        'fitz',
        'pypdf',
        'fastapi',
        'starlette',
        'anyio',
        'sniffio',
        'click',
        'colorama',
        'h11',
        'httpcore',
        'httpx',
        'idna',
        'certifi',
        'watchfiles',
        'multidict',
        'pydantic',
        'pydantic_core',
        'annotated_types',
        'typing_extensions',
        'alembic',
        'mako',
        'markupsafe',
        'jinja2',
        'lxml',
        'lxml.etree',
        'lxml.html',
        'openpyxl',
        'yaml',
    ],
    console=False,
    onefile=True,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='bidcraft-sidecar',
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='bidcraft-sidecar',
    debug=False,
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
)
