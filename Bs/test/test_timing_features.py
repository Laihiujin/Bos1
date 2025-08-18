#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试时间点控制功能
验证随机、高级随机、精确定点播放等功能
"""

import os
import sys
from main import process_batch_with_features

def test_timing_features():
    """测试时间点控制功能"""
    print("🧪 测试时间点控制功能...")
    
    # 模拟UI参数
    materials = ["test_material.mp4"]  # 假设存在测试素材
    top_template = "无"
    middle_template = "无" 
    bottom_template = "test_template.mp4"  # 假设存在测试模板
    
    # 测试1: 基础随机模式
    print("\n=== 测试1: 基础随机模式 ===")
    result1 = process_batch_with_features(
        materials=materials,
        top_template=top_template,
        middle_template=middle_template, 
        bottom_template=bottom_template,
        random_timing_enabled=True,  # 启用随机
        random_timing_window=30,
        advanced_timing_enabled=False,  # 不启用高级
        random_timing_mode="window",
        random_timing_start=0,
        random_timing_end=40,
        random_timing_exact=15,
        exact_timing_enabled=False,  # 不启用精确定点
        top_alpha_clip_enabled=False,
        top_alpha_clip_start=0,
        top_alpha_clip_duration=5,
        middle_alpha_clip_enabled=False,
        middle_alpha_clip_start=0,
        middle_alpha_clip_duration=5,
        bottom_alpha_clip_enabled=False,
        bottom_alpha_clip_start=0,
        bottom_alpha_clip_duration=5,
        preset="fast",
        crf=23,
        audio_bitrate="128k",
        max_workers=1
    )
    
    # 测试2: 高级随机范围模式
    print("\n=== 测试2: 高级随机范围模式 ===")
    result2 = process_batch_with_features(
        materials=materials,
        top_template=top_template,
        middle_template=middle_template,
        bottom_template=bottom_template,
        random_timing_enabled=True,  # 启用随机
        random_timing_window=30,
        advanced_timing_enabled=True,  # 启用高级
        random_timing_mode="range",  # 范围模式
        random_timing_start=10,
        random_timing_end=50,
        random_timing_exact=15,
        exact_timing_enabled=False,  # 不启用精确定点
        top_alpha_clip_enabled=False,
        top_alpha_clip_start=0,
        top_alpha_clip_duration=5,
        middle_alpha_clip_enabled=False,
        middle_alpha_clip_start=0,
        middle_alpha_clip_duration=5,
        bottom_alpha_clip_enabled=False,
        bottom_alpha_clip_start=0,
        bottom_alpha_clip_duration=5,
        preset="fast",
        crf=23,
        audio_bitrate="128k",
        max_workers=1
    )
    
    # 测试3: 精确定点模式
    print("\n=== 测试3: 精确定点模式 ===")
    result3 = process_batch_with_features(
        materials=materials,
        top_template=top_template,
        middle_template=middle_template,
        bottom_template=bottom_template,
        random_timing_enabled=False,  # 不启用随机
        random_timing_window=30,
        advanced_timing_enabled=False,  # 不启用高级
        random_timing_mode="window",
        random_timing_start=10,
        random_timing_end=50,
        random_timing_exact=25,  # 精确在25秒出现
        exact_timing_enabled=True,  # 启用精确定点
        top_alpha_clip_enabled=False,
        top_alpha_clip_start=0,
        top_alpha_clip_duration=5,
        middle_alpha_clip_enabled=False,
        middle_alpha_clip_start=0,
        middle_alpha_clip_duration=5,
        bottom_alpha_clip_enabled=False,
        bottom_alpha_clip_start=0,
        bottom_alpha_clip_duration=5,
        preset="fast",
        crf=23,
        audio_bitrate="128k",
        max_workers=1
    )
    
    # 测试4: 标准覆盖模式（所有随机开关都关闭）
    print("\n=== 测试4: 标准覆盖模式 ===")
    result4 = process_batch_with_features(
        materials=materials,
        top_template=top_template,
        middle_template=middle_template,
        bottom_template=bottom_template,
        random_timing_enabled=False,  # 不启用随机
        random_timing_window=30,
        advanced_timing_enabled=False,  # 不启用高级
        random_timing_mode="window",
        random_timing_start=10,
        random_timing_end=50,
        random_timing_exact=25,
        exact_timing_enabled=False,  # 不启用精确定点
        top_alpha_clip_enabled=False,
        top_alpha_clip_start=0,
        top_alpha_clip_duration=5,
        middle_alpha_clip_enabled=False,
        middle_alpha_clip_start=0,
        middle_alpha_clip_duration=5,
        bottom_alpha_clip_enabled=False,
        bottom_alpha_clip_start=0,
        bottom_alpha_clip_duration=5,
        preset="fast",
        crf=23,
        audio_bitrate="128k",
        max_workers=1
    )
    
    print("\n🎉 时间点控制功能测试完成！")
    print("请检查上述DEBUG FLAGS输出，确认参数传递正确。")
    print("如果看到相应的🕒随机日志或🔧🔄标准模式日志，说明功能正常。")

if __name__ == "__main__":
    test_timing_features()