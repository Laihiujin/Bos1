#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试alpha通道检测功能

这个脚本演示了如何使用utils.py中的函数来检查视频文件是否包含alpha通道。
它将检查alpha_templates目录中的视频文件，并显示哪些文件包含alpha通道。
"""

import os
from utils import check_video_has_alpha, check_directory_for_alpha_videos


def test_single_video():
    """
    测试检查单个视频文件
    """
    print("\n===== 测试检查单个视频文件 =====")
    
    # 检查alpha_templates/bottom_layer中的视频
    bottom_layer_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alpha_templates", "bottom_layer")
    
    if os.path.exists(bottom_layer_dir):
        video_files = [f for f in os.listdir(bottom_layer_dir) if f.endswith(('.mp4', '.mov', '.avi'))]
        
        if video_files:
            video_path = os.path.join(bottom_layer_dir, video_files[0])
            print(f"检查视频: {video_path}")
            has_alpha = check_video_has_alpha(video_path)
            
            if has_alpha:
                print(f"✅ 视频包含alpha通道")
            else:
                print(f"ℹ️ 视频不包含alpha通道")
        else:
            print(f"❌ 未找到视频文件")
    else:
        print(f"❌ 目录不存在: {bottom_layer_dir}")


def test_directory_check():
    """
    测试检查目录中的视频文件
    """
    print("\n===== 测试检查目录中的视频文件 =====")
    
    # 检查alpha_templates目录
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alpha_templates")
    
    if os.path.exists(templates_dir):
        print(f"检查目录: {templates_dir} (递归)")
        results = check_directory_for_alpha_videos(templates_dir, recursive=True)
        
        if results:
            # 结果已经在函数内部打印，这里不需要额外处理
            pass
        else:
            print(f"❌ 检查失败")
    else:
        print(f"❌ 目录不存在: {templates_dir}")


def test_material_videos():
    """
    测试检查material_videos目录中的视频文件
    """
    print("\n===== 测试检查material_videos目录 =====")
    
    # 检查material_videos目录
    material_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "material_videos")
    
    if os.path.exists(material_dir):
        print(f"检查目录: {material_dir}")
        results = check_directory_for_alpha_videos(material_dir)
        
        if results:
            # 结果已经在函数内部打印，这里不需要额外处理
            pass
        else:
            print(f"❌ 检查失败")
    else:
        print(f"❌ 目录不存在: {material_dir}")


def main():
    print("===== Alpha通道检测测试 =====")
    
    # 测试检查单个视频文件
    test_single_video()
    
    # 测试检查目录中的视频文件
    test_directory_check()
    
    # 测试检查material_videos目录
    test_material_videos()
    
    print("\n===== 测试完成 =====")


if __name__ == "__main__":
    main()