#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Alpha模板压缩功能
"""

import os
import sys
from utils import compress_alpha_template, batch_compress_alpha_templates, check_video_has_alpha

def test_alpha_detection():
    """测试alpha通道检测功能"""
    print("=== 测试Alpha通道检测功能 ===")
    
    # 测试用户提到的两个文件
    test_files = [
        "/Users/laihiujin/Documents/Down/Trae/Batch/alpha_templates/middle_layer/121.mov",
        "/Users/laihiujin/Documents/Down/Trae/Batch/alpha_templates/middle_layer/7月11日.mov"
    ]
    
    for file_path in test_files:
        if os.path.exists(file_path):
            print(f"\n📹 检测文件: {os.path.basename(file_path)}")
            
            # 获取文件大小
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            print(f"📊 文件大小: {file_size_mb:.1f}MB")
            
            # 检测alpha通道
            has_alpha = check_video_has_alpha(file_path, silent=False)
            print(f"🎭 包含Alpha通道: {'是' if has_alpha else '否'}")
            
            if file_size_mb > 100:  # 大于100MB的文件
                print(f"⚠️ 文件较大，建议压缩")
        else:
            print(f"❌ 文件不存在: {file_path}")

def test_single_compression():
    """测试单文件压缩"""
    print("\n=== 测试单文件压缩功能 ===")
    
    # 查找alpha_templates目录中的大文件
    alpha_dir = "/Users/laihiujin/Documents/Down/Trae/Batch/alpha_templates"
    
    large_files = []
    for layer in ['top_layer', 'middle_layer', 'bottom_layer']:
        layer_dir = os.path.join(alpha_dir, layer)
        if os.path.exists(layer_dir):
            for filename in os.listdir(layer_dir):
                if filename.lower().endswith(('.mov', '.mp4', '.avi')):
                    file_path = os.path.join(layer_dir, filename)
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    if file_size_mb > 50:  # 大于50MB
                        large_files.append((file_path, file_size_mb))
    
    if large_files:
        # 选择第一个大文件进行测试
        test_file, file_size = large_files[0]
        print(f"\n🎯 测试文件: {os.path.basename(test_file)}")
        print(f"📊 原始大小: {file_size:.1f}MB")
        
        # 生成测试输出路径
        output_path = test_file.replace('.mov', '_test_compressed.mov').replace('.mp4', '_test_compressed.mp4')
        
        print(f"🗜️ 开始压缩测试...")
        success, final_path, message = compress_alpha_template(
            test_file, output_path, target_size_mb=30, silent=False
        )
        
        if success:
            compressed_size = os.path.getsize(final_path) / (1024 * 1024)
            print(f"✅ 压缩成功!")
            print(f"📊 压缩后大小: {compressed_size:.1f}MB")
            print(f"📈 压缩率: {(1 - compressed_size/file_size)*100:.1f}%")
            
            # 清理测试文件
            try:
                os.remove(final_path)
                print(f"🗑️ 已清理测试文件")
            except:
                print(f"⚠️ 清理测试文件失败")
        else:
            print(f"❌ 压缩失败: {message}")
    else:
        print("📭 未找到大于50MB的alpha模板文件")

def test_batch_compression_dry_run():
    """测试批量压缩（模拟运行）"""
    print("\n=== 批量压缩模拟测试 ===")
    
    alpha_dir = "/Users/laihiujin/Documents/Down/Trae/Batch/alpha_templates"
    
    if not os.path.exists(alpha_dir):
        print(f"❌ Alpha模板目录不存在: {alpha_dir}")
        return
    
    print(f"🔍 扫描目录: {alpha_dir}")
    
    total_files = 0
    large_files = 0
    total_size = 0
    
    for layer in ['top_layer', 'middle_layer', 'bottom_layer']:
        layer_dir = os.path.join(alpha_dir, layer)
        if os.path.exists(layer_dir):
            print(f"\n📁 检查 {layer}:")
            
            layer_files = [f for f in os.listdir(layer_dir) if f.lower().endswith(('.mov', '.mp4', '.avi'))]
            
            for filename in layer_files:
                file_path = os.path.join(layer_dir, filename)
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                total_files += 1
                total_size += file_size_mb
                
                if file_size_mb > 50:  # 大于50MB
                    large_files += 1
                    print(f"  🔍 {filename}: {file_size_mb:.1f}MB (需要压缩)")
                else:
                    print(f"  ✅ {filename}: {file_size_mb:.1f}MB (跳过)")
    
    print(f"\n📊 统计结果:")
    print(f"总文件数: {total_files}")
    print(f"需要压缩: {large_files}")
    print(f"总大小: {total_size:.1f}MB")
    
    if large_files > 0:
        estimated_savings = large_files * 200  # 假设每个文件平均节省200MB
        print(f"预计节省空间: ~{estimated_savings:.0f}MB")

def main():
    """主测试函数"""
    print("🧪 Alpha模板压缩功能测试")
    print("=" * 50)
    
    try:
        # 测试alpha通道检测
        test_alpha_detection()
        
        # 测试单文件压缩
        test_single_compression()
        
        # 测试批量压缩（模拟）
        test_batch_compression_dry_run()
        
        print("\n✅ 所有测试完成!")
        
    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()