import subprocess
import shutil
import os
import re

def check_ffmpeg_installed():
    """
    检查 FFmpeg 是否已安装
    """
    return shutil.which("ffprobe") is not None

def validate_video_file(video_path):
    """验证视频文件完整性和可读性"""
    try:
        # 使用ffprobe检查文件基本信息
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration,format_name', 
             '-of', 'default=noprint_wrappers=1', video_path],
            capture_output=True, text=True, check=True
        )
        output_lines = result.stdout.strip().split('\n')
        
        # 检查是否有有效的格式信息
        has_format = any('format_name=' in line for line in output_lines)
        has_duration = any('duration=' in line for line in output_lines)
        
        if not has_format:
            return False, "文件格式无法识别"
        if not has_duration:
            return False, "无法获取文件时长信息"
            
        return True, "文件验证通过"
    except subprocess.CalledProcessError as e:
        return False, f"文件损坏或格式不支持: {e}"
    except Exception as e:
        return False, f"验证过程出错: {e}"

def get_video_duration(video_path):
    """
    获取视频时长（秒），float 类型
    如果 FFmpeg 未安装，返回默认时长
    """
    # 检查 FFmpeg 是否安装
    if not check_ffmpeg_installed():
        print("⚠️ FFmpeg 未安装，无法获取视频时长")
        print("💡 请运行以下命令安装 FFmpeg:")
        print("   brew install ffmpeg")
        print("🔄 使用默认时长 30 秒")
        return 30.0  # 返回默认时长
    
    # 检查文件是否存在
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return None
    
    # 先验证文件完整性
    is_valid, message = validate_video_file(video_path)
    if not is_valid:
        print(f"❌ 文件验证失败 {video_path}: {message}")
        return 30.0  # 返回默认时长
    
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
        duration = float(result.stdout.strip())
        return duration
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 执行失败: {e}")
        return 30.0  # 返回默认时长
    except ValueError as e:
        print(f"❌ 无法解析视频时长: {e}")
        return 30.0  # 返回默认时长
    except Exception as e:
        print(f"❌ 获取视频时长失败: {e}")
        return 30.0  # 返回默认时长


def check_video_has_alpha(video_path, silent=False):
    """
    检查视频是否包含alpha通道
    
    Args:
        video_path: 视频文件路径
        silent: 是否静默模式（不打印信息）
        
    Returns:
        bool: 如果视频包含alpha通道返回True，否则返回False
              如果检查失败（文件不存在或FFmpeg未安装）也返回False
    """
    # 检查 FFmpeg 是否安装
    if not check_ffmpeg_installed():
        if not silent:
            print("⚠️ FFmpeg 未安装，无法检查视频alpha通道")
            print("💡 请运行以下命令安装 FFmpeg:")
            print("   brew install ffmpeg")
        return False
    
    # 检查文件是否存在
    if not os.path.exists(video_path):
        if not silent:
            print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    # 使用ffprobe检查视频的像素格式
    command = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=pix_fmt",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
        pix_fmt = result.stdout.strip()
        
        # 检查像素格式是否支持alpha通道
        # 常见的支持alpha通道的格式包括：rgba, argb, yuva420p, yuva444p等
        alpha_formats = ['rgba', 'argb', 'yuva420p', 'yuva444p', 'ya8', 'ya16', 
                        'ayuv', 'pal8a', 'gbrap', 'gbrap10le', 'gbrap12le', 
                        'gbrp16a', 'rgba64le', 'rgba64be', 'bgra', 'gbra']
        
        has_alpha = any(fmt in pix_fmt for fmt in alpha_formats)
        
        if not silent:
            if has_alpha:
                print(f"✅ 视频包含alpha通道，像素格式: {pix_fmt}")
            else:
                print(f"ℹ️ 视频不包含alpha通道，像素格式: {pix_fmt}")
            
        return has_alpha
        
    except subprocess.CalledProcessError as e:
        if not silent:
            print(f"❌ FFmpeg 执行失败: {e}")
        return False
    except Exception as e:
        if not silent:
            print(f"❌ 检查视频alpha通道失败: {e}")
        return False


def check_directory_for_alpha_videos(directory_path, recursive=False, video_extensions=None):
    """
    检查目录中的视频文件是否包含alpha通道，并生成报告
    
    Args:
        directory_path: 目录路径
        recursive: 是否递归检查子目录
        video_extensions: 视频文件扩展名列表，默认为['.mp4', '.mov', '.avi']
    
    Returns:
        dict: 包含检查结果的字典，格式为：
            {
                'total': 检查的视频总数,
                'with_alpha': 包含alpha通道的视频数量,
                'without_alpha': 不包含alpha通道的视频数量,
                'failed': 检查失败的视频数量,
                'alpha_videos': [包含alpha通道的视频路径列表],
                'non_alpha_videos': [不包含alpha通道的视频路径列表],
                'failed_videos': [检查失败的视频路径列表]
            }
    """
    if video_extensions is None:
        video_extensions = ['.mp4', '.mov', '.avi']
    
    # 检查目录是否存在
    if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
        print(f"❌ 目录不存在: {directory_path}")
        return None
    
    # 初始化结果
    results = {
        'total': 0,
        'with_alpha': 0,
        'without_alpha': 0,
        'failed': 0,
        'alpha_videos': [],
        'non_alpha_videos': [],
        'failed_videos': []
    }
    
    # 获取视频文件列表
    video_files = []
    
    if recursive:
        # 递归遍历目录
        for root, _, files in os.walk(directory_path):
            for file in files:
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    video_files.append(os.path.join(root, file))
    else:
        # 只检查当前目录
        for file in os.listdir(directory_path):
            if any(file.lower().endswith(ext) for ext in video_extensions):
                video_files.append(os.path.join(directory_path, file))
    
    # 检查每个视频文件
    total_files = len(video_files)
    print(f"找到 {total_files} 个视频文件，开始检查...")
    
    for i, video_path in enumerate(video_files, 1):
        print(f"[{i}/{total_files}] 检查: {os.path.basename(video_path)}")
        
        # 检查视频是否包含alpha通道（静默模式）
        has_alpha = check_video_has_alpha(video_path, silent=True)
        
        # 获取视频的像素格式
        try:
            command = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
            pix_fmt = result.stdout.strip()
        except:
            pix_fmt = "未知"
        
        # 更新结果
        results['total'] += 1
        
        if has_alpha is None:  # 检查失败
            results['failed'] += 1
            results['failed_videos'].append(video_path)
            print(f"  ❌ 检查失败")
        elif has_alpha:  # 包含alpha通道
            results['with_alpha'] += 1
            results['alpha_videos'].append(video_path)
            print(f"  ✅ 包含alpha通道，像素格式: {pix_fmt}")
        else:  # 不包含alpha通道
            results['without_alpha'] += 1
            results['non_alpha_videos'].append(video_path)
            print(f"  ℹ️ 不包含alpha通道，像素格式: {pix_fmt}")
    
    # 打印汇总报告
    print("\n===== Alpha通道检查报告 =====")
    print(f"总共检查: {results['total']} 个视频文件")
    print(f"包含alpha通道: {results['with_alpha']} 个")
    print(f"不包含alpha通道: {results['without_alpha']} 个")
    print(f"检查失败: {results['failed']} 个")
    
    if results['with_alpha'] > 0:
        print("\n包含alpha通道的视频:")
        for video in results['alpha_videos']:
            print(f"  - {video}")
    
    return results


def compress_alpha_template(input_path, output_path=None, target_size_mb=50, silent=False):
    """
    压缩alpha模板视频，专门处理RLE等大文件格式
    优化版本 - 确保保留alpha通道
    
    Args:
        input_path: 输入视频路径
        output_path: 输出路径，如果为None则在原文件名后添加_compressed
        target_size_mb: 目标文件大小（MB），默认50MB
        silent: 是否静默模式
        
    Returns:
        tuple: (success: bool, output_path: str, message: str)
    """
    # 检查FFmpeg是否安装
    if not check_ffmpeg_installed():
        message = "FFmpeg未安装，无法压缩视频"
        if not silent:
            print(f"❌ {message}")
        return False, None, message
    
    # 检查输入文件
    if not os.path.exists(input_path):
        message = f"输入文件不存在: {input_path}"
        if not silent:
            print(f"❌ {message}")
        return False, None, message
    
    # 生成输出路径
    if output_path is None:
        base_name = os.path.splitext(input_path)[0]
        ext = os.path.splitext(input_path)[1]
        output_path = f"{base_name}_compressed{ext}"
    
    # 获取原文件信息
    try:
        # 获取文件大小
        original_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        # 获取视频信息
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,pix_fmt,codec_name",
            "-of", "default=noprint_wrappers=1",
            input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
        video_info = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                video_info[key] = value
        
        width = int(video_info.get('width', 1920))
        height = int(video_info.get('height', 1080))
        duration = float(video_info.get('duration', 10))
        pix_fmt = video_info.get('pix_fmt', 'unknown')
        codec = video_info.get('codec_name', 'unknown')
        
        if not silent:
            print(f"📹 原文件信息: {original_size_mb:.1f}MB, {width}x{height}, {duration:.1f}s")
            print(f"📹 像素格式: {pix_fmt}, 编码器: {codec}")
        
        # 检查是否包含alpha通道
        has_alpha = check_video_has_alpha(input_path, silent=True)
        
        if not has_alpha:
            message = "输入视频不包含alpha通道，无需特殊处理"
            if not silent:
                print(f"⚠️ {message}")
            return False, None, message
        
        # 计算目标码率（考虑alpha通道需要更高码率）
        # 增加码率以确保alpha通道质量
        target_bitrate_kbps = int((target_size_mb * 8 * 1024) / duration * 0.95)  # 95%用于视频
        
        # 构建FFmpeg命令 - 专门优化alpha通道处理
        # 使用prores_ks编码器或qtrle编码器更好地保留alpha通道
        if original_size_mb > 200 and target_size_mb < 100:
            # 大文件压缩到小文件，使用更高效的编码
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-c:v", "libx264",
                "-preset", "medium",  # 平衡压缩率和速度
                "-crf", "23",  # 降低CRF以提高质量
                "-pix_fmt", "yuva420p",  # 保持alpha通道的标准格式
                "-profile:v", "high",
                "-level", "4.1",
                "-movflags", "+faststart",
                "-b:v", f"{target_bitrate_kbps}k",
                "-maxrate", f"{int(target_bitrate_kbps * 1.5)}k",
                "-bufsize", f"{int(target_bitrate_kbps * 2)}k",
                "-threads", "4",  # 限制线程数以提高稳定性
                "-tune", "animation",  # 针对动画内容优化
                "-filter_complex", "format=yuva420p,scale=trunc(iw/2)*2:trunc(ih/2)*2",  # 确保尺寸是偶数
                output_path
            ]
        else:
            # 使用ProRes 4444编码器，更好地保留alpha通道
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-c:v", "prores_ks",
                "-profile:v", "4",  # ProRes 4444，保留alpha通道
                "-alpha_bits", "16",  # 使用16位alpha通道
                "-pix_fmt", "yuva444p10le",  # 10位4:4:4:4格式
                "-vendor", "ap10",
                "-bits_per_mb", f"{int((target_size_mb * 8 * 1024 * 1024) / (width * height * duration) * 0.8)}",
                "-threads", "4",
                output_path
            ]
        
        if not silent:
            print(f"🔄 开始压缩，目标大小: {target_size_mb}MB，目标码率: {target_bitrate_kbps}kbps")
            print(f"📝 执行命令: {' '.join(cmd[:8])}...")
        
        # 执行压缩
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode != 0:
            message = f"压缩失败: {result.stderr}"
            if not silent:
                print(f"❌ {message}")
            return False, None, message
        
        # 检查输出文件
        if os.path.exists(output_path):
            compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            compression_ratio = (1 - compressed_size_mb / original_size_mb) * 100
            
            # 验证压缩后的文件仍包含alpha通道
            compressed_has_alpha = check_video_has_alpha(output_path, silent=True)
            
            if not silent:
                print(f"✅ 压缩完成!")
                print(f"📊 原文件: {original_size_mb:.1f}MB → 压缩后: {compressed_size_mb:.1f}MB")
                print(f"📈 压缩率: {compression_ratio:.1f}%")
                print(f"🎭 Alpha通道: {'保留' if compressed_has_alpha else '丢失'}")
            
            if not compressed_has_alpha:
                message = "警告：压缩后alpha通道丢失"
                if not silent:
                    print(f"⚠️ {message}")
                return True, output_path, message
            
            message = f"压缩成功，文件大小从{original_size_mb:.1f}MB减少到{compressed_size_mb:.1f}MB"
            return True, output_path, message
        else:
            message = "压缩失败：输出文件未生成"
            if not silent:
                print(f"❌ {message}")
            return False, None, message
            
    except subprocess.CalledProcessError as e:
        message = f"FFmpeg执行失败: {e}"
        if not silent:
            print(f"❌ {message}")
        return False, None, message
    except Exception as e:
        message = f"压缩过程出错: {e}"
        if not silent:
            print(f"❌ {message}")
        return False, None, message


def batch_compress_alpha_templates(templates_dir, target_size_mb=50, backup=True):
    """
    批量压缩alpha模板目录中的大文件
    
    Args:
        templates_dir: alpha模板根目录
        target_size_mb: 目标文件大小（MB）
        backup: 是否备份原文件
        
    Returns:
        dict: 压缩结果统计
    """
    results = {
        'total': 0,
        'compressed': 0,
        'skipped': 0,
        'failed': 0,
        'details': []
    }
    
    if not os.path.exists(templates_dir):
        print(f"❌ 模板目录不存在: {templates_dir}")
        return results
    
    print(f"🔍 扫描alpha模板目录: {templates_dir}")
    
    # 遍历所有层级目录
    for layer in ['top_layer', 'middle_layer', 'bottom_layer']:
        layer_dir = os.path.join(templates_dir, layer)
        if not os.path.exists(layer_dir):
            continue
            
        print(f"\n📁 处理 {layer} 目录...")
        
        for filename in os.listdir(layer_dir):
            if not filename.lower().endswith(('.mov', '.mp4', '.avi')):
                continue
                
            file_path = os.path.join(layer_dir, filename)
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            results['total'] += 1
            
            # 跳过小文件
            if file_size_mb <= target_size_mb:
                print(f"⏭️ 跳过小文件: {filename} ({file_size_mb:.1f}MB)")
                results['skipped'] += 1
                results['details'].append({
                    'file': filename,
                    'layer': layer,
                    'action': 'skipped',
                    'reason': f'文件大小({file_size_mb:.1f}MB)小于目标大小({target_size_mb}MB)'
                })
                continue
            
            print(f"🔄 处理大文件: {filename} ({file_size_mb:.1f}MB)")
            
            # 备份原文件
            if backup:
                backup_path = f"{file_path}.backup"
                if not os.path.exists(backup_path):
                    try:
                        import shutil
                        shutil.copy2(file_path, backup_path)
                        print(f"💾 已备份到: {os.path.basename(backup_path)}")
                    except Exception as e:
                        print(f"⚠️ 备份失败: {e}")
            
            # 压缩文件
            temp_output = f"{file_path}.compressed.tmp"
            success, output_path, message = compress_alpha_template(
                file_path, temp_output, target_size_mb, silent=False
            )
            
            if success:
                # 替换原文件
                try:
                    os.replace(temp_output, file_path)
                    print(f"✅ 已替换原文件: {filename}")
                    results['compressed'] += 1
                    results['details'].append({
                        'file': filename,
                        'layer': layer,
                        'action': 'compressed',
                        'message': message
                    })
                except Exception as e:
                    print(f"❌ 替换文件失败: {e}")
                    results['failed'] += 1
                    results['details'].append({
                        'file': filename,
                        'layer': layer,
                        'action': 'failed',
                        'reason': f'替换文件失败: {e}'
                    })
            else:
                results['failed'] += 1
                results['details'].append({
                    'file': filename,
                    'layer': layer,
                    'action': 'failed',
                    'reason': message
                })
                
                # 清理临时文件
                if os.path.exists(temp_output):
                    os.remove(temp_output)
    
    # 打印汇总报告
    print(f"\n===== Alpha模板压缩报告 =====")
    print(f"总文件数: {results['total']}")
    print(f"已压缩: {results['compressed']}")
    print(f"已跳过: {results['skipped']}")
    print(f"失败: {results['failed']}")
    
    return results