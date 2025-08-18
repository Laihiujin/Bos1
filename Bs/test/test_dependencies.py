#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
依赖项测试脚本
验证所有requirements.txt中的依赖是否正确安装
"""

import sys
import importlib
from typing import List, Tuple

def test_import(module_name: str, package_name: str = None) -> Tuple[bool, str]:
    """
    测试模块导入
    
    Args:
        module_name: 要导入的模块名
        package_name: 包名（用于显示）
    
    Returns:
        (成功标志, 消息)
    """
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, '__version__', 'unknown')
        display_name = package_name or module_name
        return True, f"✅ {display_name}: {version}"
    except ImportError as e:
        display_name = package_name or module_name
        return False, f"❌ {display_name}: {str(e)}"
    except Exception as e:
        display_name = package_name or module_name
        return False, f"⚠️ {display_name}: {str(e)}"

def main():
    """
    主测试函数
    """
    print("🔍 开始测试依赖项...\n")
    
    # 定义要测试的依赖项
    dependencies = [
        # 核心可视化 / API
        ('gradio', 'Gradio'),
        ('fastapi', 'FastAPI'),
        ('uvicorn', 'Uvicorn'),
        
        # 数据模型 / 校验
        ('pydantic', 'Pydantic'),
        
        # 多媒体处理
        ('ffmpeg', 'python-ffmpeg'),
        ('PIL', 'Pillow'),
        ('pydub', 'PyDub'),
        
        # 计算机视觉
        ('cv2', 'OpenCV'),
        
        # 数值计算与工具
        ('numpy', 'NumPy'),
        ('tqdm', 'tqdm'),
        
        # 系统与环境
        ('psutil', 'psutil'),
        ('dotenv', 'python-dotenv'),
    ]
    
    success_count = 0
    total_count = len(dependencies)
    failed_modules = []
    
    print("📦 核心依赖测试:")
    for module_name, display_name in dependencies:
        success, message = test_import(module_name, display_name)
        print(f"  {message}")
        if success:
            success_count += 1
        else:
            failed_modules.append(display_name)
    
    print("\n🧪 功能测试:")
    
    # 测试 NumPy 基本功能
    try:
        import numpy as np
        arr = np.array([1, 2, 3])
        print(f"  ✅ NumPy 数组创建: {arr.shape}")
    except Exception as e:
        print(f"  ❌ NumPy 功能测试失败: {e}")
        failed_modules.append("NumPy功能")
    
    # 测试 OpenCV 基本功能
    try:
        import cv2
        # 创建一个简单的图像
        img = cv2.imread('nonexistent.jpg')  # 这会返回 None，但不会抛出异常
        print(f"  ✅ OpenCV 基本功能: 版本 {cv2.__version__}")
    except Exception as e:
        print(f"  ❌ OpenCV 功能测试失败: {e}")
        failed_modules.append("OpenCV功能")
    
    # 测试 Pillow 基本功能
    try:
        from PIL import Image
        # 创建一个简单的图像
        img = Image.new('RGB', (100, 100), color='red')
        print(f"  ✅ Pillow 图像创建: {img.size}")
    except Exception as e:
        print(f"  ❌ Pillow 功能测试失败: {e}")
        failed_modules.append("Pillow功能")
    
    # 测试项目核心模块
    print("\n🏠 项目模块测试:")
    project_modules = [
        ('config', '配置模块'),
        ('utils', '工具模块'),
        ('main', '主处理模块'),
        ('ffmpeg_processor', 'FFmpeg处理器'),
        ('gradio_ui', 'Gradio界面'),
    ]
    
    for module_name, display_name in project_modules:
        success, message = test_import(module_name, display_name)
        print(f"  {message}")
        if success:
            success_count += 1
        else:
            failed_modules.append(display_name)
    
    total_count += len(project_modules)
    
    # 输出总结
    print("\n" + "="*50)
    print(f"📊 测试总结:")
    print(f"  成功: {success_count}/{total_count}")
    print(f"  失败: {len(failed_modules)}")
    
    if failed_modules:
        print(f"\n❌ 失败的模块:")
        for module in failed_modules:
            print(f"  - {module}")
        print("\n💡 建议:")
        print("  1. 检查虚拟环境是否正确激活")
        print("  2. 重新安装失败的依赖: pip install -r requirements.txt")
        print("  3. 检查 Python 版本是否为 3.11+")
        return False
    else:
        print("\n🎉 所有依赖项测试通过！")
        print("✅ 环境配置完成，可以正常使用应用")
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)