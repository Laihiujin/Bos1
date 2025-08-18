#!/usr/bin/env python3
# 测试视频处理功能

import os
import sys
from main import process_video_with_layers
from config import Config

def test_single_processing():
    """测试单个视频处理"""
    print("🧪 测试单个视频处理功能...")
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    MATERIAL_DIR = os.path.join(BASE_DIR, Config.MATERIAL_DIR)
    OUTPUT_DIR = os.path.join(BASE_DIR, Config.OUTPUT_DIR)
    ALPHA_TEMPLATES_DIR = os.path.join(BASE_DIR, Config.ALPHA_TEMPLATES_DIR)
    
    # 检查素材文件
    materials = [f for f in os.listdir(MATERIAL_DIR) if f.endswith(('.mp4', '.mov', '.avi', '.mkv'))]
    if not materials:
        print("❌ 未找到素材文件")
        return False
    
    # 检查模板文件
    template_dirs = {
        "top_layer": os.path.join(ALPHA_TEMPLATES_DIR, "top_layer"),
        "middle_layer": os.path.join(ALPHA_TEMPLATES_DIR, "middle_layer"),
        "bottom_layer": os.path.join(ALPHA_TEMPLATES_DIR, "bottom_layer")
    }
    
    available_templates = 0
    for layer_name, template_dir in template_dirs.items():
        if os.path.exists(template_dir):
            templates = [f for f in os.listdir(template_dir) if f.endswith(('.mp4', '.mov', '.avi'))]
            available_templates += len(templates)
            print(f"📁 {layer_name}: {len(templates)} 个模板")
    
    if available_templates == 0:
        print("❌ 未找到模板文件")
        return False
    
    # 选择第一个素材进行测试
    test_material = materials[0]
    material_path = os.path.join(MATERIAL_DIR, test_material)
    
    print(f"🎬 测试素材: {test_material}")
    print(f"📊 可用模板总数: {available_templates}")
    
    # 定义进度回调
    def progress_callback(message):
        print(f"📈 进度: {message}")
    
    try:
        # 执行处理
        processor = process_video_with_layers(
            material_path=material_path,
            template_dirs=template_dirs,
            output_dir=OUTPUT_DIR,
            progress_callback=progress_callback,
            random_timing=False,
            random_timing_window=40,
            top_alpha_clip_enabled=False,
            top_alpha_clip_start=0,
            top_alpha_clip_duration=5,
            middle_alpha_clip_enabled=False,
            middle_alpha_clip_start=0,
            middle_alpha_clip_duration=5,
            bottom_alpha_clip_enabled=False,
            bottom_alpha_clip_start=0,
            bottom_alpha_clip_duration=5
        )
        
        if processor:
            print("✅ 测试成功完成")
            
            # 检查输出文件
            output_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('layered_') and f.endswith('.mp4')]
            print(f"📁 输出文件数: {len(output_files)}")
            
            if output_files:
                latest_file = max(output_files, key=lambda f: os.path.getctime(os.path.join(OUTPUT_DIR, f)))
                file_path = os.path.join(OUTPUT_DIR, latest_file)
                file_size = os.path.getsize(file_path)
                print(f"📄 最新输出: {latest_file} ({file_size} bytes)")
                
                if file_size > 1024:  # 大于1KB
                    print("✅ 输出文件大小正常")
                    return True
                else:
                    print("⚠️ 输出文件异常小")
                    return False
            else:
                print("❌ 未生成输出文件")
                return False
        else:
            print("❌ 处理失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 开始视频处理功能测试")
    success = test_single_processing()
    
    if success:
        print("\n🎉 所有测试通过！视频处理功能正常")
        sys.exit(0)
    else:
        print("\n💥 测试失败！请检查配置和文件")
        sys.exit(1)