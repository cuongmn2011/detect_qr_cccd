# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import importlib.util

# Helper to get module path
def get_module_path(module_name):
    spec = importlib.util.find_spec(module_name)
    if spec and spec.origin:
        return os.path.dirname(spec.origin)
    return None

block_cipher = None

# Get paths for packages
celery_path = get_module_path('celery')
kombu_path = get_module_path('kombu')
billiard_path = get_module_path('billiard')
vine_path = get_module_path('vine')

# Build datas list
datas = [
    ('d:/Acacy/detect_qr_cccd/web', 'web/'),
    ('d:/Acacy/detect_qr_cccd/asset', 'asset/'),
]

# Add packages if found
if celery_path:
    datas.append((celery_path, 'celery'))
if kombu_path:
    datas.append((kombu_path, 'kombu'))
if billiard_path:
    datas.append((billiard_path, 'billiard'))
if vine_path:
    datas.append((vine_path, 'vine'))

a = Analysis(
    ['d:/Acacy/detect_qr_cccd/run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'cv2',
        'numpy',
        'redis',
        'fastapi',
        'uvicorn',
        'uvicorn.lifespan',
        'uvicorn.protocols',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websocket',
        'PIL',
        'pillow_heif',
        'zxingcpp',
        'pydantic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='detect_qr_cccd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
