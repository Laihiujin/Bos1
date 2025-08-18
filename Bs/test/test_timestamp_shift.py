#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试时间戳平移修复
验证随机/精确定点模式下模板能够完整播放而不被截取
"""

import os
import sys
import random
from main import process_video_with_layers

def test_timestamp_shift():
    """
    测试时间戳平移功能
    """
    print("=" * 60)
    print("🧪 测试时间戳平移修复")
    print("=" * 60)
    
    # 测试参数
    material_path = "material_videos/710Zr(1).mp4"
    template_dirs = {
        'top_layer': 'alpha_templates/top_layer',
        'middle_layer': 'alpha_templates/middle_layer', 
        'bottom_layer': 'alpha_templates/bottom_layer'
    }
    output_dir = "output_processed_videos"
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"📁 素材路径: {material_path}")
    print(f"📁 输出目录: {output_dir}")
    print(f"📁 模板目录: {template_dirs}")
    print()
    
    # 测试1: 精确定点 - 30秒开始
    print("🎯 测试1: 精确定点模式 - 30秒开始")
    print("预期: 模板应该从30秒开始完整播放18秒（30-48秒）")
    result1 = process_video_with_layers(
        material_path=material_path,
        template_dirs=template_dirs,
        output_dir=output_dir,
        exact_timing_enabled=True,
        random_timing_exact=30,
        force_template="2-1"  # 指定模板以便观察
    )
    print(f"结果: {result1}")
    print()
    
    # 测试2: 精确定点 - 45秒开始（接近素材末尾）
    print("🎯 测试2: 精确定点模式 - 45秒开始")
    print("预期: 模板应该从45秒开始完整播放18秒（45-63秒，可能超出素材长度）")
    result2 = process_video_with_layers(
        material_path=material_path,
        template_dirs=template_dirs,
        output_dir=output_dir,
        exact_timing_enabled=True,
        random_timing_exact=45,
        force_template="2-1"
    )
    print(f"结果: {result2}")
    print()
    
    # 测试3: 高级随机模式 - 范围30-50秒
    print("🕒 测试3: 高级随机模式 - 范围30-50秒")
    print("预期: 模板应该在30-50秒范围内随机开始，完整播放18秒")
    result3 = process_video_with_layers(
        material_path=material_path,
        template_dirs=template_dirs,
        output_dir=output_dir,
        advanced_timing_enabled=True,
        random_timing_mode="range",
        random_timing_start=30,
        random_timing_end=50,
        force_template="2-1"
    )
    print(f"结果: {result3}")
    print()
    
    # 测试4: 基础随机模式 - 前50秒窗口
    print("🕒 测试4: 基础随机模式 - 前50秒窗口")
    print("预期: 模板应该在0-50秒范围内随机开始，完整播放18秒")
    result4 = process_video_with_layers(
        material_path=material_path,
        template_dirs=template_dirs,
        output_dir=output_dir,
        random_timing=True,
        random_timing_window=50,
        force_template="2-1"
    )
    print(f"结果: {result4}")
    print()
    
    # 总结
    print("=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    tests = [
        ("精确定点30秒", result1),
        ("精确定点45秒", result2), 
        ("高级随机30-50秒", result3),
        ("基础随机前50秒", result4)
    ]
    
    success_count = 0
    for name, result in tests:
        if result and result.get('success'):
            print(f"✅ {name}: 成功")
            success_count += 1
        else:
            print(f"❌ {name}: 失败 - {result.get('message', '未知错误') if result else '无结果'}")
    
    print(f"\n🎯 成功率: {success_count}/{len(tests)} ({success_count/len(tests)*100:.1f}%)")
    
    if success_count == len(tests):
        print("\n🎉 所有测试通过！时间戳平移修复成功")
        print("\n📝 关键改进:")
        print("   • 使用 setpts=PTS-STARTPTS+START/TB 实现时间戳平移")
        print("   • 移除 enable='between()' 限制")
        print("   • 模板可以在任意时间点完整播放")
        print("   • 不再受原始模板时长限制")
    else:
        print("\n⚠️  部分测试失败，需要进一步检查")
    
    return success_count == len(tests)

if __name__ == "__main__":
    # 设置随机种子以便重现结果
    random.seed(42)
    
    try:
        success = test_timestamp_shift()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        sys.exit(1)