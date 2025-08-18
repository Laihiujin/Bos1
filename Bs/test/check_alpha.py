#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
检查视频文件是否包含alpha通道的命令行工具

用法:
    python check_alpha.py 视频文件路径                # 检查单个视频文件
    python check_alpha.py -d 目录路径               # 检查目录中的所有视频文件
    python check_alpha.py -d 目录路径 -r            # 递归检查目录及其子目录中的所有视频文件
    python check_alpha.py -d 目录路径 -e mp4,mov    # 指定要检查的视频文件扩展名
"""

import os
import sys
import argparse
from utils import check_video_has_alpha, check_directory_for_alpha_videos


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="检查视频文件是否包含alpha通道")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("video_path", nargs="?", help="视频文件路径")
    group.add_argument("-d", "--directory", help="要检查的目录路径")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归检查子目录")
    parser.add_argument("-e", "--extensions", default="mp4,mov,avi", help="要检查的视频文件扩展名，用逗号分隔")
    
    args = parser.parse_args()
    
    # 处理文件扩展名
    extensions = [f".{ext.strip()}" for ext in args.extensions.split(",")]
    
    # 检查单个视频文件
    if args.video_path:
        if not os.path.exists(args.video_path):
            print(f"❌ 文件不存在: {args.video_path}")
            return 1
        
        print(f"检查视频文件: {args.video_path}")
        has_alpha = check_video_has_alpha(args.video_path)
        
        # 返回状态码：0表示有alpha通道，1表示没有alpha通道或检查失败
        return 0 if has_alpha else 1
    
    # 检查目录中的视频文件
    elif args.directory:
        if not os.path.exists(args.directory) or not os.path.isdir(args.directory):
            print(f"❌ 目录不存在: {args.directory}")
            return 1
        
        print(f"检查目录: {args.directory} {'(递归)' if args.recursive else ''}")
        print(f"文件类型: {', '.join(extensions)}")
        
        results = check_directory_for_alpha_videos(
            args.directory,
            recursive=args.recursive,
            video_extensions=extensions
        )
        
        # 返回状态码：如果至少有一个视频包含alpha通道，则返回0，否则返回1
        return 0 if results and results['with_alpha'] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())