
# -*- mode: python ; coding: utf-8 -*-

import sys
import os
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

# 收集数据文件
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

# 收集gradio相关所有文件（包括.py源文件）
gradio_datas, gradio_binaries, gradio_hiddenimports = collect_all('gradio')
gradio_client_datas, gradio_client_binaries, gradio_client_hiddenimports = collect_all('gradio_client')

# 修复safehttpx版本文件问题
safehttpx_datas = []
try:
    safehttpx_datas = collect_data_files('safehttpx')
except:
    pass

# 收集groovy数据文件（修复version.txt缺失问题）
groovy_datas = []
try:
    groovy_datas = collect_data_files('groovy')
except:
    pass

# 收集其他可能缺失的数据文件
pydantic_datas = []
try:
    pydantic_datas = collect_data_files('pydantic')
except:
    pass

# 项目数据文件
datas = [
    ('alpha_templates', 'alpha_templates'),
    ('config', 'config'),
    ('material_videos', 'material_videos'),
    ('pixels_trans', 'pixels_trans'),
    ('End_cut', 'End_cut'), 
    ('segments', 'segments'),
    ('requirements.txt', '.'),
    ('utils.py', '.'),
    ('ffmpeg_processor.py', '.'),
] + gradio_datas + gradio_client_datas + safehttpx_datas + groovy_datas + pydantic_datas

# 收集二进制文件
binaries = []

# 添加gradio相关二进制文件
binaries.extend(gradio_binaries)
binaries.extend(gradio_client_binaries)

# 尝试添加FFmpeg
import shutil
ffmpeg_path = shutil.which('ffmpeg')
if ffmpeg_path:
    binaries.append((ffmpeg_path, '.'))
elif os.path.exists('ffmpeg.exe'):
    binaries.append(('ffmpeg.exe', '.'))

# 隐藏导入 - 添加更多必要的模块
hiddenimports = [
    # Gradio相关（从collect_all自动收集）
    *gradio_hiddenimports,
    *gradio_client_hiddenimports,
    # 额外的Gradio模块
    'gradio',
    'gradio.components',
    'gradio.interface',
    'gradio.blocks',
    'gradio.routes',
    'gradio.utils',
    'gradio_client',
    'gradio_client.client',
    'gradio_client.serializing',
    'gradio_client.utils',
    
    # 多媒体处理
    'ffmpeg',
    'ffmpeg_python',
    'pydub',
    'PIL',
    'PIL.Image',
    'cv2',
    
    # 数据处理
    'numpy',
    'pandas',
    'json',
    'random',
    'threading',
    'queue',
    'subprocess',
    'pathlib',
    'argparse',
    'shutil',
    'tempfile',
    'time',
    'concurrent.futures',
    
    # Web框架
    'uvicorn',
    'fastapi',
    'websockets',
    'httpx',
    'aiofiles',
    'pydantic',
    
    # 可视化
    'matplotlib',
    'matplotlib.pyplot',
    'altair',
    
    # 系统相关
    'platform',
    'socket',
    'warnings',
    'psutil',
    
    # 加密和安全
    'cryptography',
    'cryptography.fernet',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'scipy',
        'jupyter',
        'notebook',
    ],
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
    name='AlphaVideoProcessor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台模式
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以后续添加图标文件
)
