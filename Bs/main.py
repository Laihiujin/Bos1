import os
import random
import subprocess
import shutil
import re
import sys
import gradio as gr
import platform
import tempfile
import time
import threading
import socket
import warnings
import json
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional
import cv2
from PIL import Image
import numpy as np
from utils import get_video_duration, check_video_has_alpha, compress_alpha_template, batch_compress_alpha_templates
from config.config import Config
from ffmpeg_processor import FFmpegProcessor

# 设置Gradio环境变量
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
warnings.filterwarnings("ignore", category=UserWarning)

# 项目目录配置 - 支持EXE打包后的相对路径
def get_base_dir():
    """获取程序运行基础目录，支持EXE打包后的路径"""
    if getattr(sys, 'frozen', False):
        # 如果是PyInstaller打包的EXE
        return Path(sys.executable).parent
    else:
        # 普通Python脚本运行
        return Path(__file__).parent

BASE_DIR = get_base_dir()
MATERIAL_DIR = BASE_DIR / Config.MATERIAL_DIR
OUTPUT_DIR = BASE_DIR / Config.OUTPUT_DIR
ALPHA_TEMPLATES_DIR = BASE_DIR / Config.ALPHA_TEMPLATES_DIR

# 素材加工专用文件夹
RESOLUTION_CONVERTED_DIR = BASE_DIR / Config.RESOLUTION_CONVERTED_DIR
TRIMMED_DIR = BASE_DIR / Config.TRIMMED_DIR
SEGMENTS_DIR = BASE_DIR / Config.SEGMENTS_DIR

# 确保目录存在
for d in [MATERIAL_DIR, OUTPUT_DIR, ALPHA_TEMPLATES_DIR, RESOLUTION_CONVERTED_DIR, TRIMMED_DIR, SEGMENTS_DIR]:
    os.makedirs(d, exist_ok=True)
for layer in ['top_layer', 'middle_layer', 'bottom_layer']:
    os.makedirs(os.path.join(ALPHA_TEMPLATES_DIR, layer), exist_ok=True)

# 全局FFmpeg处理器实例
global_ffmpeg_processor = FFmpegProcessor(max_retries=3, timeout=300)
processing_cancelled = False

# 全局进度状态
processing_status = {
    'current': 0,
    'total': 0,
    'current_file': '',
    'is_processing': False,
    'results': [],
    'errors': [],
    'start_time': None,
    'end_time': None
}

# 参数预设功能
PRESETS_FILE = os.path.join(BASE_DIR, "config", "presets.json")

# ========== UI辅助函数 ========== #

def list_materials():
    """获取所有素材视频文件名列表"""
    try:
        return [f for f in os.listdir(MATERIAL_DIR) if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))]
    except Exception as e:
        print(f"获取素材列表失败: {e}")
        return []

def list_materials_from_dir(directory):
    """从指定目录获取素材文件列表"""
    try:
        if not os.path.exists(directory):
            return []
        return [f for f in os.listdir(directory) if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))]
    except Exception as e:
        print(f"获取目录 {directory} 素材列表失败: {e}")
        return []

def list_all_processing_materials():
    """获取所有处理文件夹的素材列表"""
    all_materials = []
    
    # 原始素材
    original_materials = [(f"[原始] {f}", f, str(MATERIAL_DIR)) for f in list_materials_from_dir(MATERIAL_DIR)]
    all_materials.extend(original_materials)
    
    # 分辨率转换后的素材
    resolution_materials = [(f"[分辨率转换] {f}", f, str(RESOLUTION_CONVERTED_DIR)) for f in list_materials_from_dir(RESOLUTION_CONVERTED_DIR)]
    all_materials.extend(resolution_materials)
    
    # 裁剪后的素材
    trimmed_materials = [(f"[结尾裁剪] {f}", f, str(TRIMMED_DIR)) for f in list_materials_from_dir(TRIMMED_DIR)]
    all_materials.extend(trimmed_materials)
    
    # 切分后的素材
    segment_materials = [(f"[视频切分] {f}", f, str(SEGMENTS_DIR)) for f in list_materials_from_dir(SEGMENTS_DIR)]
    all_materials.extend(segment_materials)
    
    return all_materials

def get_material_choices_for_processing():
    """获取素材加工面板的素材选择列表"""
    all_materials = list_all_processing_materials()
    return [display_name for display_name, _, _ in all_materials]

def resolve_material_path(selected_materials):
    """解析选中的素材，返回实际文件路径列表"""
    all_materials = list_all_processing_materials()
    material_map = {display_name: (filename, folder_path) for display_name, filename, folder_path in all_materials}
    
    resolved_paths = []
    for selected in selected_materials:
        if selected in material_map:
            filename, folder_path = material_map[selected]
            full_path = os.path.join(folder_path, filename)
            resolved_paths.append(full_path)
    
    return resolved_paths

def list_templates(layer):
    """获取指定层级的模板文件名列表"""
    try:
        layer_dir = os.path.join(ALPHA_TEMPLATES_DIR, layer)
        if not os.path.exists(layer_dir):
            return []
        return [f for f in os.listdir(layer_dir) if f.lower().endswith((".mp4", ".mov", ".avi"))]
    except Exception as e:
        print(f"获取模板列表失败: {e}")
        return []

def open_folder_cross_platform(folder_path):
    """跨平台打开文件夹"""
    try:
        if not os.path.exists(folder_path):
            return f"❌ 文件夹不存在: {folder_path}"
        
        system = platform.system()
        if system == "Darwin":  # macOS
            subprocess.run(["open", folder_path])
        elif system == "Windows":
            subprocess.run(["explorer", folder_path])
        elif system == "Linux":
            subprocess.run(["xdg-open", folder_path])
        else:
            return f"❌ 不支持的操作系统: {system}"
        
        return f"✅ 已打开文件夹: {os.path.basename(folder_path)}"
    except Exception as e:
        return f"❌ 打开文件夹失败: {str(e)}"

def emergency_stop():
    """紧急停止所有FFmpeg进程"""
    global processing_cancelled
    processing_cancelled = True
    
    try:
        # 取消当前处理器的进程
        cancelled = global_ffmpeg_processor.cancel_current_process()
        
        # 清理所有卡住的FFmpeg进程
        killed_count = global_ffmpeg_processor.kill_stuck_ffmpeg_processes()
        
        message = "🛑 紧急停止执行完成\n"
        if cancelled:
            message += "✅ 已取消当前FFmpeg进程\n"
        if killed_count > 0:
            message += f"🧹 清理了 {killed_count} 个卡住的FFmpeg进程\n"
        else:
            message += "ℹ️ 未发现卡住的FFmpeg进程\n"
            
        return message
        
    except Exception as e:
        return f"❌ 紧急停止时出错: {str(e)}"

def reset_processing_state():
    """重置处理状态"""
    global processing_cancelled
    processing_cancelled = False
    return "✅ 处理状态已重置"

def save_preset(name, preset_data):
    """保存参数预设"""
    try:
        if os.path.exists(PRESETS_FILE):
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                presets = json.load(f)
        else:
            presets = {}
        
        presets[name] = preset_data
        
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
        
        return f"✅ 预设 '{name}' 保存成功"
    except Exception as e:
        return f"❌ 保存预设失败: {str(e)}"

def load_preset(name):
    """加载参数预设"""
    try:
        if not os.path.exists(PRESETS_FILE):
            return None
        
        with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        
        return presets.get(name)
    except Exception as e:
        print(f"加载预设失败: {str(e)}")
        return None

def list_presets():
    """列出所有预设"""
    try:
        if not os.path.exists(PRESETS_FILE):
            return []
        
        with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        
        return list(presets.keys())
    except Exception as e:
        print(f"列出预设失败: {str(e)}")
        return []

def delete_preset(name):
    """删除预设"""
    try:
        if not os.path.exists(PRESETS_FILE):
            return "❌ 预设文件不存在"
        
        with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        
        if name in presets:
            del presets[name]
            with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(presets, f, ensure_ascii=False, indent=2)
            return f"✅ 预设 '{name}' 删除成功"
        else:
            return f"❌ 预设 '{name}' 不存在"
    except Exception as e:
        return f"❌ 删除预设失败: {str(e)}"



def generate_video_thumbnail(video_path, timestamp=1.0):
    """生成视频缩略图"""
    try:
        if not os.path.exists(video_path):
            print(f"视频文件不存在: {video_path}")
            return None
            
        # 使用FFmpeg生成缩略图，避免OpenCV可能的兼容性问题
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # 使用FFmpeg提取帧
            cmd = [
                'ffmpeg',
                '-y',  # 覆盖输出文件
                '-ss', str(timestamp),  # 设置时间戳
                '-i', video_path,  # 输入文件
                '-vframes', '1',  # 只提取一帧
                '-q:v', '2',  # 质量设置
                temp_path  # 输出文件
            ]
            
            # 执行命令
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)
            
            if result.returncode != 0:
                print(f"FFmpeg提取帧失败: {result.stderr}")
                # 回退到OpenCV方法
                raise Exception("FFmpeg提取帧失败，尝试使用OpenCV")
            
            # 读取生成的图像
            img = Image.open(temp_path)
            
            # 调整大小
            width, height = img.size
            if width > 320:
                scale = 320 / width
                new_width = 320
                new_height = int(height * scale)
                img = img.resize((new_width, new_height))
            
            # 删除临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
                
            return img
            
        except Exception as ffmpeg_error:
            print(f"FFmpeg方法失败，尝试OpenCV: {str(ffmpeg_error)}")
            # 如果FFmpeg方法失败，回退到OpenCV方法
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # 设置时间戳
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int(timestamp * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                # 转换BGR到RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # 调整大小
                height, width = frame_rgb.shape[:2]
                if width > 320:
                    scale = 320 / width
                    new_width = 320
                    new_height = int(height * scale)
                    frame_rgb = cv2.resize(frame_rgb, (new_width, new_height))
                
                return Image.fromarray(frame_rgb)
            return None
            
    except Exception as e:
        print(f"生成缩略图失败: {str(e)}")
        return None

def upload_template(file, layer):
    """上传模板文件"""
    if file is None:
        return "❌ 请选择文件"
    filename = os.path.basename(file.name)
    layer_dir = os.path.join(ALPHA_TEMPLATES_DIR, layer)
    os.makedirs(layer_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".mp4", ".mov", ".avi"]:
        return f"❌ 不支持的文件格式: {ext}"
    target = os.path.join(layer_dir, filename)
    # 修复：处理Gradio File对象
    if hasattr(file, 'read'):
        # 文件对象
        with open(target, "wb") as f:
            f.write(file.read())
    else:
        # NamedString对象，直接复制文件
        import shutil
        shutil.copy2(file.name, target)
    return f"✅ 已上传 {filename} 到 {layer}"

# 视频预览和下载功能
def list_output_videos():
    """列出输出目录中的所有视频文件"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return []
        
        video_files = []
        for file in os.listdir(OUTPUT_DIR):
            if file.lower().endswith(('.mp4', '.mov', '.avi')):
                video_files.append(file)
        
        return sorted(video_files, key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
    except Exception as e:
        print(f"列出输出视频失败: {str(e)}")
        return []

def get_video_preview_and_info(video_name):
    """获取视频预览和信息"""
    if not video_name:
        return None, ""
    
    video_path = os.path.join(OUTPUT_DIR, video_name)
    if not os.path.exists(video_path):
        return None, "❌ 视频文件不存在"
    
    try:
        # 获取视频信息
        file_size = os.path.getsize(video_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # 获取视频时长
        duration = get_video_duration(video_path)
        duration_str = f"{duration:.1f}秒" if duration else "未知"
        
        # 获取修改时间
        mtime = os.path.getmtime(video_path)
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        
        info_text = f"文件大小: {file_size_mb:.1f} MB\n时长: {duration_str}\n创建时间: {mtime_str}"
        
        return video_path, info_text
    except Exception as e:
        return None, f"❌ 获取视频信息失败: {str(e)}"

def delete_output_video(video_name):
    """删除输出视频文件"""
    if not video_name:
        return "❌ 请选择要删除的视频", gr.update()
    
    video_path = os.path.join(OUTPUT_DIR, video_name)
    if not os.path.exists(video_path):
        return "❌ 视频文件不存在", gr.update()
    
    try:
        os.remove(video_path)
        # 刷新视频列表
        new_choices = list_output_videos()
        return f"✅ 已删除视频: {video_name}", gr.update(choices=new_choices, value=None)
    except Exception as e:
        return f"❌ 删除失败: {str(e)}", gr.update()

def randomize_timing_params():
    """随机化时间参数"""
    return (
        random.choice([True, False]),  # random_timing_enabled
        random.uniform(10, 60),        # random_timing_window
        random.choice(["before_window", "between_range", "exact_time"]),  # random_timing_mode
        random.uniform(0, 30),         # random_timing_start
        random.uniform(30, 60),        # random_timing_end
        random.uniform(5, 45)          # random_timing_exact
    )

# ========== 素材加工相关函数 ========== #

def get_video_info(video_path):
    """获取视频信息"""
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        
        cap.release()
        
        return {
            'width': width,
            'height': height,
            'fps': fps,
            'duration': duration,
            'frame_count': frame_count
        }
    except Exception as e:
        print(f"获取视频信息失败: {e}")
        return None

def crop_and_scale_video(materials, output_path, crop_x, crop_y, crop_width, crop_height, scale_width, scale_height, preset="veryfast", crf=23):
    """裁剪和缩放视频"""
    if not materials:
        return "❌ 请选择要处理的素材"
    
    results = []
    
    try:
        for material in materials:
            input_path = os.path.join(MATERIAL_DIR, material)
            if not os.path.exists(input_path):
                results.append(f"❌ 文件不存在: {material}")
                continue
            
            # 生成输出文件名
            name, ext = os.path.splitext(material)
            output_filename = f"{name}_processed{ext}"
            output_full_path = os.path.join(OUTPUT_DIR, output_filename)
            
            # 构建FFmpeg命令
            cmd = ['ffmpeg', '-i', input_path, '-y']
            
            # 添加视频滤镜
            filters = []
            
            # 裁剪滤镜
            if crop_x > 0 or crop_y > 0 or crop_width < 1920 or crop_height < 1080:
                filters.append(f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y}")
            
            # 缩放滤镜
            if scale_width != 1920 or scale_height != 1080:
                filters.append(f"scale={scale_width}:{scale_height}")
            
            if filters:
                cmd.extend(['-vf', ','.join(filters)])
            
            # 编码参数
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', str(crf),
                '-c:a', 'aac',
                '-b:a', '192k',
                output_full_path
            ])
            
            # 执行命令
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=300)
            
            if result.returncode == 0:
                results.append(f"✅ 处理完成: {output_filename}")
            else:
                results.append(f"❌ 处理失败 {material}: {result.stderr}")
            
    except Exception as e:
        results.append(f"❌ 处理异常: {str(e)}")
    
    return "\n".join(results)

def batch_resolution_convert(materials, resolution="1080p", mode="stretch", preset="veryfast", crf=23):
    """批量分辨率转换"""
    if not materials:
        return "❌ 请选择要处理的素材"
    
    results = []
    
    # 根据分辨率设置目标尺寸
    if resolution == "720p":
        target_width, target_height = 1280, 720
        suffix = "_720p"
    elif resolution == "1080p":
        target_width, target_height = 1920, 1080
        suffix = "_1080p"
    elif resolution == "vertical_720p":
        target_width, target_height = 720, 1280
        suffix = "_vertical_720p"
    elif resolution == "vertical_1080p":
        target_width, target_height = 1080, 1920
        suffix = "_vertical_1080p"
    else:
        return "❌ 不支持的分辨率格式"
    
    # 解析素材路径
    if materials and isinstance(materials[0], str) and materials[0].startswith('['):
        # 如果是带标签的素材名称，需要解析为实际路径
        material_paths = resolve_material_path(materials)
        material_names = [os.path.basename(path) for path in material_paths]
    else:
        # 如果是普通文件名，从原始素材文件夹获取
        material_paths = [os.path.join(MATERIAL_DIR, material) for material in materials]
        material_names = materials
    
    for i, (material_path, material_name) in enumerate(zip(material_paths, material_names)):
        try:
            if not os.path.exists(material_path):
                results.append(f"❌ {material_name}: 文件不存在")
                continue
            
            # 获取视频信息
            info = get_video_info(material_path)
            if not info:
                results.append(f"❌ {material_name}: 无法获取视频信息")
                continue
            
            # 生成输出文件名
            name, ext = os.path.splitext(material_name)
            output_filename = f"{name}{suffix}{ext}"
            output_path = os.path.join(RESOLUTION_CONVERTED_DIR, output_filename)
            
            # 构建FFmpeg命令
            cmd = ['ffmpeg', '-i', material_path, '-y']
            
            if mode == "stretch":
                # 拉伸模式：直接缩放
                cmd.extend(['-vf', f'scale={target_width}:{target_height}'])
            elif mode == "fit":
                # 适配模式：保持宽高比，添加黑边
                cmd.extend(['-vf', f'scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2'])
            elif mode == "crop":
                # 裁剪模式：保持宽高比，裁剪多余部分
                cmd.extend(['-vf', f'scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}'])
            elif mode == "vertical_embed":
                # 竖版嵌入模式：横屏视频嵌入到竖版画布中
                width = info.get('width', 0)
                height = info.get('height', 0)
                if width > height:
                    # 横屏视频：嵌入到竖版画布中
                    if resolution in ["vertical_720p", "vertical_1080p"]:
                        canvas_width = target_width
                        canvas_height = target_height
                        scale_height = int(canvas_width * height / width)
                        y_offset = (canvas_height - scale_height) // 2
                        cmd.extend(['-vf', f'scale={canvas_width}:{scale_height},pad={canvas_width}:{canvas_height}:0:{y_offset}:black'])
                    else:
                        cmd.extend(['-vf', f'scale={target_width}:{target_height}'])
                else:
                    # 竖屏或方形视频：直接适配
                    cmd.extend(['-vf', f'scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black'])
            
            # 编码参数
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', str(crf),
                '-c:a', 'aac',
                '-b:a', '192k',
                output_path
            ])
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=300)
            
            if result.returncode == 0:
                results.append(f"✅ {material_name} -> {output_filename}")
            else:
                results.append(f"❌ {material_name}: {result.stderr[:100]}")
                
        except Exception as e:
            results.append(f"❌ {material_name}: {str(e)}")
    
    return "\n".join(results)

# 保持向后兼容的函数
def batch_resize_to_1080p(materials, mode="stretch", preset="veryfast", crf=23):
    """批量转换到1080p（向后兼容）"""
    return batch_resolution_convert(materials, "1080p", mode, preset, crf)

def trim_video_ending(materials, trim_seconds, preset="veryfast", crf=23):
    """批量删除视频结尾N秒"""
    if not materials:
        return "❌ 请选择要处理的素材"
    
    results = []
    
    for material in materials:
        try:
            # 解析素材路径
            material_path, material_name = resolve_material_path([material])[0]
            
            if not os.path.exists(material_path):
                results.append(f"❌ {material_name}: 文件不存在")
                continue
            
            # 获取视频时长
            info = get_video_info(material_path)
            if not info:
                results.append(f"❌ {material_name}: 无法获取视频信息")
                continue
            
            duration = info['duration']
            
            # 检查裁剪时长是否合理
            if trim_seconds <= 0:
                results.append(f"❌ {material_name}: 裁剪时长必须大于0秒")
                continue
                
            new_duration = duration - trim_seconds
            if new_duration <= 0:
                results.append(f"❌ {material_name}: 裁剪后时长为负，跳过")
                continue
            
            # 生成输出文件名
            name, ext = os.path.splitext(material_name)
            output_filename = f"{name}_trimmed{ext}"
            output_path = os.path.join(TRIMMED_DIR, output_filename)
            
            # 构建FFmpeg命令
            cmd = [
                'ffmpeg', '-i', material_path, '-y',
                '-t', str(new_duration),
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', str(crf),
                '-c:a', 'aac',
                '-b:a', '192k',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                results.append(f"✅ {material_name} -> {output_filename} (删除{trim_seconds}秒)")
            else:
                results.append(f"❌ {material_name}: {result.stderr[:100]}")
                
        except Exception as e:
            results.append(f"❌ {material_name}: {str(e)}")
    
    return "\n".join(results)

def split_video_segments(materials, segment_min=30, segment_max=90, preset="veryfast", crf=23):
    """批量切分视频为多段"""
    if not materials:
        return "❌ 请选择要处理的素材"
    
    results = []
    
    for material in materials:
        try:
            # 解析素材路径
            material_path, material_name = resolve_material_path([material])[0]
            
            if not os.path.exists(material_path):
                results.append(f"❌ {material_name}: 文件不存在")
                continue
            
            # 获取视频时长
            info = get_video_info(material_path)
            if not info:
                results.append(f"❌ {material_name}: 无法获取视频信息")
                continue
            
            duration = info['duration']
            
            # 计算切分点
            segments = []
            current_time = 0
            segment_count = 1
            
            while current_time < duration:
                # 随机选择段长度
                segment_length = random.uniform(segment_min, segment_max)
                end_time = min(current_time + segment_length, duration)
                
                if end_time - current_time >= 10:  # 最小段长度10秒
                    segments.append((current_time, end_time, segment_count))
                    segment_count += 1
                
                current_time = end_time
            
            if not segments:
                results.append(f"⚠️ {material_name}: 视频太短，无法切分")
                continue
            
            # 生成切分文件
            name, ext = os.path.splitext(material_name)
            segment_results = []
            
            for start_time, end_time, seg_num in segments:
                output_filename = f"{name}_seg{seg_num:02d}{ext}"
                output_path = os.path.join(SEGMENTS_DIR, output_filename)
                
                # 构建FFmpeg命令
                cmd = [
                    'ffmpeg', '-i', material_path, '-y',
                    '-ss', str(start_time),
                    '-t', str(end_time - start_time),
                    '-c:v', 'libx264',
                    '-preset', preset,
                    '-crf', str(crf),
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    output_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=300)
                
                if result.returncode == 0:
                    segment_results.append(f"  ✅ 段{seg_num}: {start_time:.1f}s-{end_time:.1f}s -> {output_filename}")
                else:
                    segment_results.append(f"  ❌ 段{seg_num}: 处理失败")
            
            results.append(f"📹 {material_name}:")
            results.extend(segment_results)
                
        except Exception as e:
            results.append(f"❌ {material_name}: {str(e)}")
    
    return "\n".join(results)

# ========== 核心处理函数 ========== #

def validate_video_file(video_path):
    """验证视频文件完整性和可读性"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration,format_name',
             '-of', 'default=noprint_wrappers=1', video_path],
            capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True
        )
        lines = result.stdout.splitlines()
        has_format = any('format_name=' in l for l in lines)
        has_duration = any('duration=' in l for l in lines)
        if not has_format:
            return False, "文件格式无法识别"
        if not has_duration:
            return False, "无法获取文件时长信息"
        return True, "文件验证通过"
    except Exception as e:
        return False, f"验证过程出错: {e}"

def sanitize_filename(filepath):
    name = os.path.basename(filepath)
    base, ext = os.path.splitext(name)
    clean = re.sub(r'[^\w\-\.]+', '_', base)
    clean = re.sub(r'_+', '_', clean).strip('_') + ext
    return os.path.join(os.path.dirname(filepath), clean)

def ensure_clean_filename(filepath):
    if re.search(r'[\s\(\)\[\]&|;<>?*`$!"\'\']', filepath):
        clean = sanitize_filename(filepath)
        if not os.path.exists(clean) and os.path.exists(filepath):
            print(f"🔧 重命名文件: {os.path.basename(filepath)} -> {os.path.basename(clean)}")
            shutil.move(filepath, clean)
            return clean
    return filepath


def calculate_timing_point(exact_timing_enabled, random_timing_exact, random_timing_mode, 
                          random_timing_window, random_timing_start, random_timing_end, 
                          material_duration, template_duration):
    """计算时间点"""
    if exact_timing_enabled:
        # 定点播放模式：使用精确时间
        start_t = min(random_timing_exact, material_duration - template_duration)
    elif random_timing_mode == "before_window":
        # 原有模式：在前N秒内随机出现
        max_start = min(random_timing_window, material_duration - template_duration)
        start_t = random.uniform(0, max_start) if max_start > 0 else 0
    elif random_timing_mode == "between_range":
        # 新模式：在n秒之后m秒之前随机出现
        range_start = min(random_timing_start, material_duration - template_duration)
        range_end = min(random_timing_end, material_duration - template_duration)
        if range_end > range_start:
            start_t = random.uniform(range_start, range_end)
        else:
            start_t = range_start
    elif random_timing_mode == "exact_time":
        # 新模式：在指定n秒精确出现
        start_t = min(random_timing_exact, material_duration - template_duration)
    else:
        # 默认回退到原有模式
        max_start = min(random_timing_window, material_duration - template_duration)
        start_t = random.uniform(0, max_start) if max_start > 0 else 0
    
    return start_t

def get_timing_description(exact_timing_enabled, random_timing_mode, random_timing_window, 
                          random_timing_start, random_timing_end, random_timing_exact, 
                          start_t, template_duration, layer):
    """获取时间点描述"""
    if exact_timing_enabled:
        return f"{layer} 定点播放（{random_timing_exact}秒）：{start_t:.1f}-{start_t+template_duration:.1f}s"
    elif random_timing_mode == "before_window":
        return f"{layer} 随机时间点（前{random_timing_window}秒内）：{start_t:.1f}-{start_t+template_duration:.1f}s"
    elif random_timing_mode == "between_range":
        return f"{layer} 随机时间点（{random_timing_start}-{random_timing_end}秒间）：{start_t:.1f}-{start_t+template_duration:.1f}s"
    elif random_timing_mode == "exact_time":
        return f"{layer} 精确时间点（{random_timing_exact}秒）：{start_t:.1f}-{start_t+template_duration:.1f}s"
    else:
        return f"{layer} 随机时间点：{start_t:.1f}-{start_t+template_duration:.1f}s"

def update_progress(current, total, current_file, result=None, error=None):
    """更新处理进度"""
    global processing_status
    processing_status['current'] = current
    processing_status['total'] = total
    processing_status['current_file'] = current_file
    if result:
        processing_status['results'].append(result)
    if error:
        processing_status['errors'].append(error)

def get_simple_progress_status():
    """获取简化的进度状态"""
    global processing_status
    if not processing_status['is_processing']:
        if processing_status['current'] > 0:
            return f"✅ 处理完成 ({processing_status['current']}/{processing_status['total']})"
        return "⏸️ 等待开始"
    return f"🔄 处理中 ({processing_status['current']}/{processing_status['total']})"

def format_time(seconds):
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:.0f}分{secs:.0f}秒"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:.0f}小时{minutes:.0f}分"

def process_batch_with_features(materials, top_template, middle_template, bottom_template,
                        random_timing_enabled, random_timing_window, advanced_timing_enabled,
                        random_timing_mode, random_timing_start, random_timing_end, random_timing_exact,
                        exact_timing_enabled, top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                        middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                        bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                        preset, crf, audio_bitrate, max_workers):
    """批量处理视频"""
    global processing_status, processing_cancelled
    
    # 调试打印 - 检查所有时间点控制参数
    # 确定当前启用的模式
    if exact_timing_enabled:
        current_mode = f"定点模式(在{random_timing_exact}秒定点出现)"
    elif random_timing_enabled and advanced_timing_enabled:
        if random_timing_mode == "range":
            current_mode = f"高级随机模式(在{random_timing_start}-{random_timing_end}秒之间随机出现)"
        else:
            current_mode = f"高级随机模式(前{random_timing_window}秒内随机出现)"
    elif random_timing_enabled:
        current_mode = f"基础随机模式(前{random_timing_window}秒内随机出现)"
    else:
        current_mode = "标准模式(所有辅助功能未启用)"
    
    # 检查截取设置
    clip_info = []
    if top_alpha_clip_enabled:
        clip_info.append(f"顶层截取{top_alpha_clip_duration}秒")
    if middle_alpha_clip_enabled:
        clip_info.append(f"中层截取{middle_alpha_clip_duration}秒")
    if bottom_alpha_clip_enabled:
        clip_info.append(f"底层截取{bottom_alpha_clip_duration}秒")
    
    clip_status = ", ".join(clip_info) if clip_info else "无截取设置"
    
    print(f"\n[DEBUG FLAGS] 当前模式: {current_mode}")
    print(f"[DEBUG FLAGS] 截取设置: {clip_status}")
    print(f"[DEBUG FLAGS] 原始参数: random_timing={random_timing_enabled}, advanced={advanced_timing_enabled}, exact={exact_timing_enabled}")
    print(f"[DEBUG FLAGS] 时间参数: window={random_timing_window}, start={random_timing_start}, end={random_timing_end}, exact={random_timing_exact}\n")
    
    # 重置状态
    processing_cancelled = False
    processing_status = {
        'current': 0,
        'total': len(materials),
        'current_file': '',
        'is_processing': True,
        'results': [],
        'errors': [],
        'start_time': time.time(),
        'end_time': None
    }
    
    if not materials:
        processing_status['is_processing'] = False
        return "❌ 请选择至少一个素材视频"
    
    # 构建模板目录
    template_dirs = {}
    if top_template and top_template != "无":
        template_dirs["top_layer"] = os.path.join(ALPHA_TEMPLATES_DIR, "top_layer")
    if middle_template and middle_template != "无":
        template_dirs["middle_layer"] = os.path.join(ALPHA_TEMPLATES_DIR, "middle_layer")
    if bottom_template and bottom_template != "无":
        template_dirs["bottom_layer"] = os.path.join(ALPHA_TEMPLATES_DIR, "bottom_layer")
    
    if not template_dirs:
        processing_status['is_processing'] = False
        return "❌ 请至少选择一个模板"
    
    results = []
    
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_material = {}
            for i, material in enumerate(materials):
                if processing_cancelled:
                    break
                    
                future = executor.submit(
                    process_single_video_wrapper,
                    material, template_dirs, preset, crf, audio_bitrate,
                    random_timing_enabled, random_timing_window, random_timing_mode,
                    random_timing_start, random_timing_end, random_timing_exact,
                    exact_timing_enabled, advanced_timing_enabled,
                    top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                    middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                    bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                    i + 1
                )
                future_to_material[future] = material
            
            # 收集结果
            for future in as_completed(future_to_material):
                if processing_cancelled:
                    break
                    
                material = future_to_material[future]
                try:
                    result = future.result()
                    results.append(result)
                    update_progress(len(results), len(materials), material, result)
                except Exception as e:
                    error_msg = f"❌ {material}: {str(e)}"
                    results.append(error_msg)
                    update_progress(len(results), len(materials), material, error=error_msg)
    
    except Exception as e:
        error_msg = f"❌ 批量处理出错: {str(e)}"
        results.append(error_msg)
    
    finally:
        processing_status['is_processing'] = False
        processing_status['end_time'] = time.time()
    
    # 生成最终报告
    success_count = len([r for r in results if not r.startswith("❌")])
    error_count = len([r for r in results if r.startswith("❌")])
    
    final_report = f"\n🎉 批量处理完成！\n"
    final_report += f"✅ 成功: {success_count}个\n"
    final_report += f"❌ 失败: {error_count}个\n"
    
    if processing_status.get('start_time') and processing_status.get('end_time'):
        total_time = processing_status['end_time'] - processing_status['start_time']
        final_report += f"⏱️ 总耗时: {format_time(total_time)}\n"
    
    final_report += f"📁 输出目录: {OUTPUT_DIR}\n\n"
    final_report += "详细结果:\n" + "\n".join(results)
    
    return final_report

def process_single_video_wrapper(material, template_dirs, preset, crf, audio_bitrate,
                                random_timing_enabled, random_timing_window, random_timing_mode,
                                random_timing_start, random_timing_end, random_timing_exact,
                                exact_timing_enabled, advanced_timing_enabled,
                                top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                                middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                                bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                                task_number):
    """单个视频处理包装器"""
    global processing_cancelled
    
    # 检查是否已被取消
    if processing_cancelled:
        return f"🛑 {material} 处理已取消"
    
    try:
        material_path = os.path.join(MATERIAL_DIR, material)
        
        # 验证素材文件是否存在
        if not os.path.exists(material_path):
            return f"❌ {material} 文件不存在"
        
        # 验证模板文件是否存在
        valid_templates = {}
        for layer, template_dir in template_dirs.items():
            if os.path.exists(template_dir):
                template_files = [f for f in os.listdir(template_dir) if f.endswith(('.mp4', '.mov', '.avi'))]
                if template_files:
                    valid_templates[layer] = template_dir
        
        if not valid_templates:
            return f"❌ {material} 未找到有效的模板文件"
        
        # 定义进度回调函数
        def progress_callback(message):
            if processing_cancelled:
                return
            print(f"[{material}] {message}")
        
        # 调用处理函数
        process_video_with_layers(
            material_path,
            valid_templates,
            OUTPUT_DIR,
            progress_callback=progress_callback,
            random_timing=random_timing_enabled,
            random_timing_window=random_timing_window,
            random_timing_mode=random_timing_mode,
            random_timing_start=random_timing_start,
            random_timing_end=random_timing_end,
            random_timing_exact=random_timing_exact,
            exact_timing_enabled=exact_timing_enabled,
            advanced_timing_enabled=advanced_timing_enabled,
            top_alpha_clip_enabled=top_alpha_clip_enabled,
            top_alpha_clip_start=top_alpha_clip_start,
            top_alpha_clip_duration=top_alpha_clip_duration,
            middle_alpha_clip_enabled=middle_alpha_clip_enabled,
            middle_alpha_clip_start=middle_alpha_clip_start,
            middle_alpha_clip_duration=middle_alpha_clip_duration,
            bottom_alpha_clip_enabled=bottom_alpha_clip_enabled,
            bottom_alpha_clip_start=bottom_alpha_clip_start,
            bottom_alpha_clip_duration=bottom_alpha_clip_duration,
            preset=preset,
            crf=crf,
            audio_bitrate=audio_bitrate
        )
        
        return f"✅ {material} 处理完成"
        
    except Exception as e:
        return f"❌ {material} 处理失败: {str(e)}"


def process_video_with_layers(material_path, template_dirs, output_dir,
                              force_template=None, progress_callback=None,
                              random_timing=False, random_timing_window=40,
                              random_timing_mode="before_window", random_timing_start=0, random_timing_end=40, random_timing_exact=0,
                              exact_timing_enabled=False, advanced_timing_enabled=False,
                              top_alpha_clip_enabled=False, top_alpha_clip_start=0, top_alpha_clip_duration=5,
                              middle_alpha_clip_enabled=False, middle_alpha_clip_start=0, middle_alpha_clip_duration=5,
                              bottom_alpha_clip_enabled=False, bottom_alpha_clip_start=0, bottom_alpha_clip_duration=5,
                              preset="veryfast", crf=25, audio_bitrate=192):
    material_duration = get_video_duration(material_path)
    if not material_duration:
        print(f"无法获取素材时长：{material_path}")
        return
    
    # 收集并验证模板
    valid = {}
    for layer, d in template_dirs.items():
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith(('.mp4','.mov','.avi')):
                    path = ensure_clean_filename(os.path.join(d, f))
                    ok, msg = validate_video_file(path)
                    if ok:
                        valid.setdefault(layer, []).append(path)
    if not valid:
        print("❌ 未找到可用模板")
        return
    
    # 随机/指定模板
    chosen = {}
    for layer, paths in valid.items():
        if force_template:
            pts = [p for p in paths if force_template in os.path.basename(p)]
            chosen[layer] = pts[0] if pts else random.choice(paths)
        else:
            chosen[layer] = random.choice(paths)
        print(f"{layer} 使用模板: {os.path.basename(chosen[layer])}")
    
    # 构建命令
    cmd = ["ffmpeg", "-threads", "0", "-i", material_path]
    idx = 1
    filter_parts = []
    overlay_parts = []
    order = ['bottom_layer','middle_layer','top_layer']
    
    # --------------- 判断该走哪条分支 --------------
    # 精确定点模式优先级最高，其次是随机模式，最后是标准覆盖模式
    use_exact_timing = exact_timing_enabled
    use_random_timing = (random_timing or advanced_timing_enabled) and not exact_timing_enabled
    use_standard_mode = not use_exact_timing and not use_random_timing
    
    add_shortest_flag = False
    
    # 存储每个模板层的时间参数，用于音频同步
    layer_timing_params = {}
    # 建立输入索引到图层的映射，解决音频索引错位问题
    input_map = {}  # 例如 {1: 'top_layer', 2: 'middle_layer', ...}
    
    for layer in order:
        if layer in chosen:
            template_path = chosen[layer]
            cmd += ["-i", template_path]
            # 记录当前输入索引对应的图层
            input_map[idx] = layer
            
            # --------------- 计算模板持续 -----------------
            template_dur = get_video_duration(template_path)
            if not template_dur:
                template_dur = material_duration
            fps = 24
            
            # --------------- 应用Alpha截取设置 -----------------
            clip_enabled = False
            clip_start = 0
            clip_duration = template_dur
            
            if layer == 'top_layer' and top_alpha_clip_enabled:
                clip_enabled = True
                clip_start = top_alpha_clip_start
                clip_duration = top_alpha_clip_duration
            elif layer == 'middle_layer' and middle_alpha_clip_enabled:
                clip_enabled = True
                clip_start = middle_alpha_clip_start
                clip_duration = middle_alpha_clip_duration
            elif layer == 'bottom_layer' and bottom_alpha_clip_enabled:
                clip_enabled = True
                clip_start = bottom_alpha_clip_start
                clip_duration = bottom_alpha_clip_duration
            
            # 如果启用了截取，更新模板持续时间
            if clip_enabled:
                template_dur = clip_duration
                print(f"🎬 {layer} 启用截取: 从{clip_start}秒开始，截取{clip_duration}秒")
            
            first_layer = (idx == 1)
            last_layer = (layer == order[-1] and layer in chosen)
            
            if use_exact_timing:
                # ===== 精确定点模式 =====
                start = min(random_timing_exact, material_duration - template_dur)
                start = max(0, start)  # 确保不小于0
                end = start + template_dur
                
                # 存储时间参数供音频使用
                layer_timing_params[layer] = {
                    'timing_offset': start,
                    'trim_start': clip_start if clip_enabled else 0,
                    'trim_duration': clip_duration if clip_enabled else template_dur
                }
                
                # 生成滤镜：trim + 时间戳平移（应用Alpha截取）
                trim_start = clip_start if clip_enabled else 0
                trim_duration = clip_duration if clip_enabled else template_dur
                filter_parts.append(
                    f"[{idx}:v]trim=start={trim_start}:duration={trim_duration},"
                    f"setpts=PTS-STARTPTS+{start:.3f}/TB[clip{idx}]"
                )
                
                src = "0:v" if first_layer else f"tmp{idx-1}"
                dst = "vout" if last_layer else f"tmp{idx}"
                
                overlay_parts.append(
                    f"[{src}][clip{idx}]overlay=0:0:eof_action=pass[{dst}]"
                )
                print(f"🎯 {layer} {start:.2f}–{end:.2f}s 精确定点播放（时间戳平移）")
                
            elif use_random_timing:
                # ===== 随机时间点模式 =====
                if advanced_timing_enabled:
                    # 高级随机模式
                    if random_timing_mode == "range":
                        # N–M 范围随机
                        lo = min(random_timing_start, random_timing_end)
                        hi = max(random_timing_start, random_timing_end)
                        # 移除模板时长限制，允许完整播放
                        hi = min(hi, material_duration)
                        lo = max(0, lo)
                        if hi > lo:
                            start = random.uniform(lo, hi)
                        else:
                            start = lo
                    else:
                        # 前 N 秒随机（窗口模式）
                        # 移除模板时长限制，允许完整播放
                        max_start = min(random_timing_window, material_duration)
                        max_start = max(0, max_start)
                        start = random.uniform(0, max_start)
                else:
                    # 基础随机窗口模式
                    # 移除模板时长限制，允许完整播放
                    max_start = min(random_timing_window, material_duration)
                    max_start = max(0, max_start)
                    start = random.uniform(0, max_start)
                
                end = start + template_dur
                
                # 存储时间参数供音频使用
                layer_timing_params[layer] = {
                    'timing_offset': start,
                    'trim_start': clip_start if clip_enabled else 0,
                    'trim_duration': clip_duration if clip_enabled else template_dur
                }
                
                # 生成滤镜：trim + 时间戳平移（应用Alpha截取）
                trim_start = clip_start if clip_enabled else 0
                trim_duration = clip_duration if clip_enabled else template_dur
                filter_parts.append(
                    f"[{idx}:v]trim=start={trim_start}:duration={trim_duration},"
                    f"setpts=PTS-STARTPTS+{start:.3f}/TB[clip{idx}]"
                )
                
                src = "0:v" if first_layer else f"tmp{idx-1}"
                dst = "vout" if last_layer else f"tmp{idx}"
                
                overlay_parts.append(
                    f"[{src}][clip{idx}]overlay=0:0:eof_action=pass[{dst}]"
                )
                print(f"🕒 {layer} {start:.2f}–{end:.2f}s 随机播放（时间戳平移）")
            else:
                # ===== 标准覆盖分支 =====
                prev = "0:v" if first_layer else f"tmp{idx-1}"
                dst = "vout" if last_layer else f"tmp{idx}"
                
                # 应用Alpha截取设置到标准模式
                trim_start = clip_start if clip_enabled else 0
                trim_duration = clip_duration if clip_enabled else template_dur
                
                # 存储时间参数供音频使用（标准模式无时间偏移）
                layer_timing_params[layer] = {
                    'timing_offset': 0,
                    'trim_start': trim_start,
                    'trim_duration': trim_duration
                }
                
                if template_dur >= material_duration:
                    # 模板更长：裁成素材时长或截取时长
                    final_duration = min(trim_duration, material_duration)
                    filter_parts.append(
                        f"[{idx}:v]trim=start={trim_start}:duration={final_duration},"
                        f"setpts=PTS-STARTPTS[clip{idx}]"
                    )
                    overlay_parts.append(
                        f"[{prev}][clip{idx}]overlay=0:0:eof_action=pass[{dst}]"
                    )
                    print(f"🔧 {layer} 标准模式（长模板）：从{trim_start}s开始trim到{final_duration:.2f}s")
                else:
                    # 模板更短：按截取时长播放，不循环
                    if clip_enabled:
                        filter_parts.append(
                            f"[{idx}:v]trim=start={trim_start}:duration={trim_duration},"
                            f"setpts=PTS-STARTPTS[clip{idx}]"
                        )
                        overlay_parts.append(
                            f"[{prev}][clip{idx}]overlay=0:0:"
                            f"enable='between(t,0,{trim_duration:.2f})':"
                            "eof_action=pass"
                            f"[{dst}]"
                        )
                        print(f"📹 {layer} 标准模式（短模板+截取）：从{trim_start}s开始播放{trim_duration:.2f}s")
                    else:
                        filter_parts.append(
                            f"[{idx}:v]setpts=PTS-STARTPTS[clip{idx}]"
                        )
                        overlay_parts.append(
                            f"[{prev}][clip{idx}]overlay=0:0:"
                            f"enable='between(t,0,{template_dur:.2f})':"
                            "eof_action=pass"
                            f"[{dst}]"
                        )
                        print(f"📹 {layer} 标准模式（短模板）：按原时长{template_dur:.2f}s播放，不循环")
            
            idx += 1
    
    # 第三步：组合完整的filter_complex
    if filter_parts and overlay_parts:
        # 组合视频滤镜部分
        filter_complex = ";".join(filter_parts) + ";" + ";".join(overlay_parts)
        
        # 构建音频混合滤镜 - 修复音频丢失和同步问题
        audio_filter_parts = []
        audio_inputs = []
        
        # 首先添加素材视频的音频（索引0）
        audio_inputs.append("[0:a]")
        
        # 使用input_map精准对应每个模板输入索引到它的层
        for i, layer_name in input_map.items():
            # 拿到这层的视频时间参数
            params = layer_timing_params.get(layer_name, None)
            if not params:
                # 没参数就把音轨简单归零时戳，至少不抢跑
                audio_filter_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
                audio_inputs.append(f"[a{i}]")
                print(f"🎵 {layer_name} 音频：使用默认处理（无参数）")
                continue
            
            timing_offset = params['timing_offset']      # 秒
            trim_start    = params['trim_start']         # 秒
            trim_duration = params['trim_duration']      # 秒
            
            # 先裁切再归零时戳
            line = (f"[{i}:a]atrim=start={trim_start}:duration={trim_duration},"
                   f"asetpts=PTS-STARTPTS")
            
            # 若需要把这段放到素材的 timing_offset 秒再出现，就补静音
            if timing_offset > 0:
                delay_ms = int(round(timing_offset * 1000))
                line += f",adelay={delay_ms}:all=1"  # 补前置静音
                print(f"🎵 {layer_name} 音频：裁切{trim_start}-{trim_start+trim_duration}s，延迟{timing_offset:.2f}s")
            else:
                print(f"🎵 {layer_name} 音频：裁切{trim_start}-{trim_start+trim_duration}s，无延迟")
            
            line += f"[a{i}]"
            audio_filter_parts.append(line)
            audio_inputs.append(f"[a{i}]")
        
        # 添加音频混合命令
        if audio_filter_parts:
            # 先添加视频滤镜
            if filter_complex:
                filter_complex += ";"
            filter_complex += ";".join(audio_filter_parts)
            
            # 构建音频混合命令，素材和模板音频平衡混合
            if len(audio_inputs) > 1:
                weights = " ".join(["1"] * len(audio_inputs))
                filter_complex += ";" + "".join(audio_inputs) + f"amix=inputs={len(audio_inputs)}:duration=first:weights={weights}[aout]"
            else:
                filter_complex += ";[0:a]acopy[aout]"
            
            # 使用混合后的音频
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
        else:
            # 只有素材视频，直接使用其音频，确保音频不丢失
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "0:a"]
    elif overlay_parts:
        filter_complex = ";".join(overlay_parts)
        cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "0:a"]
    else:
        filter_complex = "[0:v]copy[vout]"
        cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "0:a"]
    
    # 调试输出
    print("\n调试信息:")
    print(f"filter_parts: {filter_parts}")
    print(f"overlay_parts: {overlay_parts}")
    print(f"filter_complex: {filter_complex}")
    
    # 编码参数 - 修复音频编码和同步问题
    # 处理音频比特率格式
    if 'audio_bitrate' in locals():
        audio_bitrate_str = f"{audio_bitrate}k" if isinstance(audio_bitrate, int) else str(audio_bitrate)
        if not audio_bitrate_str.endswith('k'):
            audio_bitrate_str += 'k'
    else:
        audio_bitrate_str = "192k"
    
    # 处理预设和CRF参数
    preset_val = preset if 'preset' in locals() else "veryfast"
    crf_val = str(crf) if 'crf' in locals() else "25"
    
    cmd += [
        "-c:a", "aac",
        "-b:a", audio_bitrate_str,
        "-ar", "44100",  # 确保音频采样率一致
        "-ac", "2",      # 确保立体声
        "-c:v", "libx264",
        "-preset", preset_val,
        "-crf", crf_val,
        "-movflags", "+faststart",
        "-r", "24",
        "-threads", "4",
        "-avoid_negative_ts", "make_zero",  # 避免负时间戳
        "-fflags", "+genpts"  # 生成时间戳
    ]
    
    # 在标准模式下添加 -shortest 参数
    if add_shortest_flag:
        cmd.append("-shortest")
    
    # 添加时长限制，防止输出超过原始素材时长
    cmd += ["-t", str(material_duration), "-y"]
    # 输出
    out = os.path.join(output_dir, f"layered_{os.path.splitext(os.path.basename(material_path))[0]}_"+
                        "_".join(os.path.splitext(os.path.basename(p))[0] for p in chosen.values())+".mp4")
    cmd.append(out)
    print("执行命令:"," ".join(cmd))
    # 进度回调函数 - 修复无限循环问题
    def show(progress, message=""):
        global processing_cancelled
        
        # 检查是否被取消
        if processing_cancelled:
            return False  # 返回False表示应该停止处理
            
        # 将progress转换为0-100的百分比
        if isinstance(progress, (int, float)):
            # 限制进度最大值为100，避免无限循环
            progress = min(progress, 100.0)
            bar_length = 30
            filled_length = int(progress / 100 * bar_length)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            # 优化进度显示，避免误判卡死
            if progress >= 99.9:
                status_msg = f"{message} (正在完成最终处理)" if message else "(正在完成最终处理)"
            else:
                status_msg = message
                
            print(f"\r进度 |{bar}| {progress:.1f}% {status_msg}", end='', flush=True)
            if progress >= 100:
                print()  # 完成时换行
                return True  # 明确返回True表示完成
        else:
            print(f"\r{message}", end='', flush=True)
        
        return True  # 继续处理
    
    print(f"🎬 处理 {os.path.basename(material_path)}")
    
    # 使用全局处理器实例，设置合理的超时时间
    timeout_duration = min(int(material_duration * 10), 600)  # 最多10分钟
    proc = FFmpegProcessor(max_retries=2, timeout=timeout_duration)
    
    try:
        ok, msg = proc.process_with_retry(cmd, show)
        
        # 检查是否因为取消而停止
        if processing_cancelled:
            return {'success': False, 'output': None, 'message': '处理已取消'}
            
        if ok:
            print("✅ 完成", out)
            return {'success': True, 'output': out, 'message': f'成功生成: {os.path.basename(out)}'}
        else:
            print("❌ 失败", msg)
            return {'success': False, 'output': None, 'message': msg}
            
    except Exception as e:
        error_msg = f"处理异常: {str(e)}"
        print(f"❌ 异常: {error_msg}")
        return {'success': False, 'output': None, 'message': error_msg}
    
    finally:
        # 确保清理资源
        try:
            proc.cancel_current_process()
        except:
            pass

# CLI
# ========== 进度更新和状态管理 ========== #

def update_progress(current, total, current_file, result=None, error=None):
    """更新处理进度"""
    global processing_status
    processing_status.update({
        'current': current,
        'total': total,
        'current_file': current_file
    })
    
    if result:
        processing_status['results'].append(result)
    if error:
        processing_status['errors'].append(error)

def get_progress_status():
    """获取当前处理状态"""
    global processing_status
    if not processing_status['is_processing']:
        return "🔄 等待开始..."
    
    current = processing_status['current']
    total = processing_status['total']
    current_file = processing_status['current_file']
    
    if current == 0:
        return "🚀 准备开始处理..."
    
    progress_percent = (current / total) * 100 if total > 0 else 0
    return f"📹 处理中 ({current}/{total}) - {progress_percent:.1f}% - {current_file}"

# ========== 批量处理功能 ========== #

# ========== 素材管理功能函数 ========== #

def format_time(seconds):
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}分{secs:.1f}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}小时{minutes}分{secs:.1f}秒"

# ========== Gradio界面创建 ========== #

def create_gradio_interface():
    """创建完整的Gradio Web界面"""
    # 移动端适配CSS
    mobile_css = """
    /* 移动端适配样式 */
    @media (max-width: 768px) {
        .gradio-container {
            padding: 8px !important;
            margin: 0 !important;
        }
        
        .block {
            margin: 4px 0 !important;
        }
        
        .form {
            gap: 8px !important;
        }
        
        .input-container {
            margin: 4px 0 !important;
        }
        
        button {
            padding: 8px 12px !important;
            font-size: 14px !important;
        }
        
        .tab-nav {
            flex-wrap: wrap !important;
        }
        
        .tab-nav button {
            min-width: auto !important;
            flex: 1 !important;
        }
        
        .accordion {
            margin: 8px 0 !important;
        }
        
        .row {
            flex-direction: column !important;
        }
        
        .column {
            width: 100% !important;
        }
        
        .textbox, .dropdown, .slider {
            width: 100% !important;
        }
        
        .progress {
            margin: 8px 0 !important;
        }
    }
    
    /* 通用优化 */
    .gradio-container {
        max-width: 100% !important;
    }
    
    .block {
        border-radius: 8px !important;
    }
    
    .tab-nav {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
        border-radius: 8px 8px 0 0 !important;
    }
    
    .tab-nav button {
        color: white !important;
        font-weight: 500 !important;
    }
    
    .tab-nav button.selected {
         background: rgba(255,255,255,0.2) !important;
     }
     
     /* 移动端提示样式 */
     .mobile-tip {
         background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
         color: white !important;
         padding: 12px !important;
         border-radius: 8px !important;
         margin: 8px 0 !important;
         font-size: 14px !important;
         line-height: 1.5 !important;
     }
     
     @media (max-width: 768px) {
         .mobile-tip {
             font-size: 12px !important;
             padding: 8px !important;
         }
     }
     
     /* 文件上传优化样式 */
     .mobile-file-upload {
         min-height: 120px !important;
     }
     
     .mobile-file-upload .file-upload {
         border: 2px dashed #4CAF50 !important;
         border-radius: 12px !important;
         padding: 20px !important;
         text-align: center !important;
         background: #f8f9fa !important;
         transition: all 0.3s ease !important;
         cursor: pointer !important;
     }
     
     .mobile-file-upload .file-upload:hover {
         border-color: #45a049 !important;
         background: #e8f5e8 !important;
         transform: translateY(-2px) !important;
         box-shadow: 0 4px 12px rgba(76, 175, 80, 0.2) !important;
     }
     
     /* 移动端文件上传特别优化 */
     @media (max-width: 768px) {
         .mobile-file-upload {
             min-height: 100px !important;
         }
         
         .mobile-file-upload .file-upload {
             padding: 15px !important;
             font-size: 14px !important;
             border-width: 3px !important;
         }
         
         .mobile-file-upload .file-upload-text {
             font-size: 16px !important;
             font-weight: 500 !important;
         }
     }
     
     /* 通用文件上传区域样式 */
     .file-upload-area {
         border: 2px dashed #007bff !important;
         border-radius: 8px !important;
         padding: 20px !important;
         text-align: center !important;
         background-color: #f8f9fa !important;
         cursor: pointer !important;
         transition: all 0.3s ease !important;
         min-height: 80px !important;
         display: flex !important;
         align-items: center !important;
         justify-content: center !important;
     }
     
     .file-upload-area:hover {
         border-color: #0056b3 !important;
         background-color: #e3f2fd !important;
         transform: translateY(-1px) !important;
         box-shadow: 0 2px 8px rgba(0, 123, 255, 0.2) !important;
     }
     """
    
    with gr.Blocks(
        title="批量Alpha视频合成工具", 
        theme=gr.themes.Soft(),
        css=mobile_css
    ) as demo:
        gr.Markdown("# 🎬 批量Alpha视频合成工具")
        gr.Markdown("高效的批量视频处理工具，支持多层Alpha模板合成")
        
        # 移动端提示
        with gr.Row():
            gr.Markdown(
                """📱 **移动端用户提示**: 本工具已优化移动端体验，支持手机访问。
                🌐 **共享访问**: 启动时会自动生成共享链接，可在任何设备上访问。
                💡 **使用建议**: 建议横屏使用以获得更好的操作体验。""",
                elem_classes=["mobile-tip"]
            )
        
        with gr.Tabs():
            # 主要批量处理界面
            with gr.TabItem("🚀 批量处理"):
                with gr.Row():
                    with gr.Column(scale=2):
                        # 素材选择
                        gr.Markdown("## 📹 素材选择")
                        with gr.Row():
                            materials = gr.CheckboxGroup(
                                choices=list_materials(),
                                label="原素材（可多选）",
                                value=[]
                            )
                        
                        with gr.Row():
                            select_all_btn = gr.Button("✅ 全选", size="sm")
                            clear_all_btn = gr.Button("❌ 清空", size="sm")
                        
                        # 参数预设
                        gr.Markdown("## 💾 参数预设")
                        with gr.Row():
                            preset_name = gr.Textbox(
                                label="预设名称",
                                placeholder="输入预设名称",
                                scale=2
                            )
                            save_preset_btn = gr.Button("💾 保存预设", size="sm", scale=1)
                        
                        with gr.Row():
                            preset_dropdown = gr.Dropdown(
                                choices=list_presets(),
                                label="选择预设",
                                scale=2
                            )
                            load_preset_btn = gr.Button("📂 加载预设", size="sm", scale=1)
                            delete_preset_btn = gr.Button("🗑️ 删除预设", size="sm", scale=1)
                        
                        preset_result = gr.Textbox(
                            label="预设操作结果",
                            lines=2,
                            interactive=False
                        )
                        
                        # Alpha模板配置
                        gr.Markdown("## 🎭 Alpha模板配置")
                        top_template = gr.Dropdown(
                            choices=["无"] + list_templates("top_layer"), 
                            value="无", 
                            label="顶层模板"
                        )
                        middle_template = gr.Dropdown(
                            choices=["无"] + list_templates("middle_layer"), 
                            value="无", 
                            label="中层模板"
                        )
                        bottom_template = gr.Dropdown(
                            choices=["无"] + list_templates("bottom_layer"), 
                            value="无", 
                            label="底层模板"
                        )
                        
                        # 时间点控制
                        with gr.Accordion("⏰ 时间点控制", open=False):
                            # 顶级随机时间点开关
                            random_timing_enabled = gr.Checkbox(
                                label="🎲 启用随机时间点合成", 
                                value=False
                            )
                            
                            # 高级随机模式开关（仅决定是否出现窗口/范围单选组）
                            advanced_timing_enabled = gr.Checkbox(
                                label="🔧 启用高级随机时间点模式",
                                value=False
                            )
                            
                            # 高级随机控制组（仅在勾选高级随机时显示）
                            with gr.Group(visible=False) as advanced_controls:
                                random_timing_mode = gr.Radio(
                                    choices=[
                                        ("在N–M秒之间随机出现", "range")
                                    ],
                                    value="range",
                                    label="高级随机模式"
                                )
                                
                                # 范围控制（N-M秒之间）
                                with gr.Row():
                                    random_timing_start = gr.Slider(
                                        minimum=0, maximum=300, value=10, step=1,
                                        label="范围开始时间（秒）"
                                    )
                                    random_timing_end = gr.Slider(
                                        minimum=0, maximum=300, value=60, step=1,
                                        label="范围结束时间（秒）"
                                    )
                            
                            # 基础随机窗口设置（仅在启用随机但未启用高级时显示）
                            with gr.Group(visible=True) as basic_controls:
                                random_timing_window = gr.Slider(
                                    minimum=10, maximum=120, value=40, step=5,
                                    label="前N秒随机窗口（秒）"
                                )
                            
                            # 精确定点开关（独立的开关，不嵌套在高级随机里）
                            exact_timing_enabled = gr.Checkbox(
                                label="🎯 启用精确定点播放模式",
                                value=False
                            )
                            
                            # 定点秒数（只在勾选精确定点时有效）
                            random_timing_exact = gr.Slider(
                                minimum=0, maximum=300, value=30, step=1,
                                label="定点播放时间（秒）"
                            )
                        
                        # 分层Alpha截取
                        with gr.Accordion("✂️ 分层Alpha模板截取", open=False):
                            # 顶层截取
                            top_alpha_clip_enabled = gr.Checkbox(
                                label="启用顶层Alpha截取功能",
                                value=False
                            )
                            with gr.Row():
                                top_alpha_clip_start = gr.Slider(
                                    minimum=0, maximum=60, value=0, step=1,
                                    label="顶层截取开始时间（秒）"
                                )
                                top_alpha_clip_duration = gr.Slider(
                                    minimum=1, maximum=30, value=5, step=1,
                                    label="顶层截取持续时间（秒）"
                                )
                            
                            # 中层截取
                            middle_alpha_clip_enabled = gr.Checkbox(
                                label="启用中层Alpha截取功能",
                                value=False
                            )
                            with gr.Row():
                                middle_alpha_clip_start = gr.Slider(
                                    minimum=0, maximum=60, value=0, step=1,
                                    label="中层截取开始时间（秒）"
                                )
                                middle_alpha_clip_duration = gr.Slider(
                                    minimum=1, maximum=30, value=5, step=1,
                                    label="中层截取持续时间（秒）"
                                )
                            
                            # 底层截取
                            bottom_alpha_clip_enabled = gr.Checkbox(
                                label="启用底层Alpha截取功能",
                                value=False
                            )
                            with gr.Row():
                                bottom_alpha_clip_start = gr.Slider(
                                    minimum=0, maximum=60, value=0, step=1,
                                    label="底层截取开始时间（秒）"
                                )
                                bottom_alpha_clip_duration = gr.Slider(
                                    minimum=1, maximum=30, value=5, step=1,
                                    label="底层截取持续时间（秒）"
                                )
                        
                        # 编码设置
                        with gr.Accordion("⚙️ 编码设置", open=True):
                            preset = gr.Dropdown(
                                choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], 
                                value=Config.DEFAULT_PRESET, 
                                label="编码预设"
                            )
                            with gr.Row():
                                crf = gr.Slider(
                                    minimum=18, maximum=28, value=Config.DEFAULT_CRF, step=1, 
                                    label="视频质量 (CRF)"
                                )
                                audio_bitrate = gr.Slider(
                                    minimum=128, maximum=320, value=Config.DEFAULT_AUDIO_BITRATE, step=32, 
                                    label="音频比特率 (kbps)"
                                )
                        
                        # 并行处理设置
                        with gr.Accordion("🔧 并行处理设置", open=False):
                            max_workers = gr.Slider(
                                minimum=1, maximum=8, value=2, step=1,
                                label="最大并行任务数"
                            )
                    
                    with gr.Column():
                        # 控制按钮
                        gr.Markdown("## 🎮 控制面板")
                        start_batch_btn = gr.Button("🚀 开始批量处理", variant="primary", size="lg")
                        stop_batch_btn = gr.Button("⏹️ 停止处理", variant="stop", size="sm")
                        emergency_stop_btn = gr.Button("🛑 紧急停止", variant="stop", size="sm")
                        
                        # 文件夹操作
                        gr.Markdown("## 📁 文件夹操作")
                        with gr.Row():
                            open_material_btn = gr.Button("📂 素材文件夹", size="sm")
                            open_template_btn = gr.Button("🎭 模板文件夹", size="sm")
                            open_output_btn = gr.Button("📤 输出文件夹", size="sm")
                        
                        # 刷新功能
                        refresh_all_btn = gr.Button("🔄 刷新所有列表", size="sm")
                        
                        # 结果显示
                        batch_result = gr.Textbox(
                            label="处理结果",
                            lines=10,
                            interactive=False,
                            show_copy_button=True
                        )
                        
                        # 视频预览和下载
                        gr.Markdown("## 🎬 视频预览与下载")
                        with gr.Row():
                            output_videos = gr.Dropdown(
                                choices=list_output_videos(),
                                label="输出视频列表",
                                interactive=True
                            )
                            refresh_videos_btn = gr.Button("🔄 刷新", size="sm")
                        
                        with gr.Row():
                            download_btn = gr.Button("📥 下载选中视频", size="sm")
                            delete_video_btn = gr.Button("🗑️ 删除选中视频", variant="stop", size="sm")
                        
                        video_preview = gr.Video(
                            label="视频预览",
                            interactive=False,
                            height=300
                        )
                        
                        video_info = gr.Textbox(
                            label="视频信息",
                            lines=3,
                            interactive=False
                        )
            
            # 素材加工标签页
            with gr.TabItem("🔧 素材加工"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## 📤 素材上传")
                        gr.Markdown("💡 **快速上传**: 支持直接上传素材文件到加工流程")
                        
                        # 文件上传组件
                        processing_material_upload = gr.File(
                            label="📱 选择素材文件",
                            file_types=[".mp4", ".avi", ".mov"],
                            height=100,
                            elem_classes=["mobile-file-upload"],
                            file_count="multiple"
                        )
                        
                        # 上传按钮
                        upload_processing_material_btn = gr.Button("🚀 上传素材", variant="secondary", size="sm")
                        
                        # 上传结果显示
                        processing_upload_result = gr.Textbox(
                            label="上传结果",
                            lines=2,
                            interactive=False,
                            show_copy_button=False
                        )
                        
                        gr.Markdown("## 分辨率/视频分辨率转换")
                        
                        # 素材选择
                        processing_materials = gr.CheckboxGroup(
                            choices=get_material_choices_for_processing(),
                            label="选择要处理的素材（支持从不同文件夹选择）",
                            interactive=True
                        )
                        
                        with gr.Row():
                            select_all_processing_btn = gr.Button("✅ 全选", size="sm")
                            clear_all_processing_btn = gr.Button("❌ 清空", size="sm")
                            delete_selected_materials_btn = gr.Button("🗑️ 删除选中", variant="stop", size="sm")
                            delete_all_materials_btn = gr.Button("💥 一键全删", variant="stop", size="sm")
                        
                        # 编码设置
                        with gr.Accordion("⚙️ 编码设置", open=True):
                            processing_preset = gr.Dropdown(
                                choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], 
                                value="veryfast", 
                                label="编码预设"
                            )
                            processing_crf = gr.Slider(
                                minimum=18, maximum=28, value=23, step=1, 
                                label="视频质量 (CRF)"
                            )
                        
                        # 分辨率转换设置
                        with gr.Accordion("📐 分辨率", open=True):
                            # 分辨率选择
                            resolution_choice = gr.Radio(
                                choices=[
                                    ("横屏 720p (1280x720)", "720p"),
                                    ("横屏 1080p (1920x1080)", "1080p"),
                                    ("竖屏 720p (720x1280)", "vertical_720p"),
                                    ("竖屏 1080p (1080x1920)", "vertical_1080p")
                                ],
                                value="1080p",
                                label="目标分辨率"
                            )
                            
                            # 转换模式
                            resize_mode = gr.Radio(
                                choices=[
                                    ("拉伸模式 (直接缩放)", "stretch"),
                                    ("适配模式 (保持宽高比，添加黑边)", "fit"),
                                    ("裁剪模式 (保持宽高比，裁剪多余部分)", "crop"),
                                    ("竖版嵌入模式 (横屏视频嵌入到竖版画布)", "vertical_embed")
                                ],
                                value="stretch",
                                label="转换模式"
                            )
                        
                        resize_1080p_btn = gr.Button("📱 批量转换", variant="primary")
                        
                        gr.Markdown("## ✂️ 视频时长控制")
                        
                        # 结尾裁剪
                        with gr.Accordion("🔚 结尾裁剪", open=True):
                            trim_seconds = gr.Slider(
                                minimum=1, maximum=60, value=10, step=1,
                                label="删除结尾秒数"
                            )
                            trim_ending_btn = gr.Button("✂️ 批量删除结尾", variant="primary")
                        
                        # 视频切分
                        with gr.Accordion("🔪 批量切分", open=True):
                            with gr.Row():
                                segment_min = gr.Slider(
                                    minimum=10, maximum=120, value=30, step=5,
                                    label="最小段长度（秒）"
                                )
                                segment_max = gr.Slider(
                                    minimum=30, maximum=180, value=90, step=5,
                                    label="最大段长度（秒）"
                                )
                            split_segments_btn = gr.Button("🔪 批量切分视频", variant="primary")
                    
                    with gr.Column():
                        # 处理结果显示
                        processing_result = gr.Textbox(
                            label="处理结果",
                            lines=15,
                            interactive=False,
                            show_copy_button=True
                        )
                        
                        # 刷新素材列表
                        refresh_processing_materials_btn = gr.Button("🔄 刷新素材列表", size="sm")
            
            # 素材上传标签页
            with gr.TabItem("📤 素材上传"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## 📤 上传素材视频")
                        gr.Markdown("💡 **使用说明**: 支持上传 .mp4、.avi、.mov 格式的素材视频文件")
                        
                        # 文件上传组件
                        material_upload = gr.File(
                            label="📱 选择素材文件",
                            file_types=[".mp4", ".avi", ".mov"],
                            height=120,
                            elem_classes=["mobile-file-upload"],
                            file_count="multiple"
                        )
                        
                        # 上传按钮
                        upload_material_btn = gr.Button("🚀 上传素材", variant="primary", size="lg")
                        
                        # 上传结果显示
                        material_upload_result = gr.Textbox(
                            label="上传结果",
                            lines=5,
                            interactive=False,
                            show_copy_button=True
                        )
                    
                    with gr.Column():
                        gr.Markdown("## 📋 素材管理")
                        
                        # 刷新素材列表
                        refresh_materials_btn = gr.Button("🔄 刷新素材列表", variant="secondary")
                        
                        # 显示当前素材
                        gr.Markdown("### 当前素材列表")
                        materials_list_display = gr.Textbox(
                            label="素材文件列表",
                            value="\n".join(list_materials()),
                            lines=10,
                            interactive=False
                        )
                        
                        # 删除素材功能
                        material_to_delete = gr.Dropdown(
                            choices=list_materials(),
                            label="选择要删除的素材",
                            interactive=True
                        )
                        delete_material_btn = gr.Button("🗑️ 删除选中素材", variant="stop", size="sm")
                        delete_material_result = gr.Textbox(
                            label="删除结果",
                            lines=2,
                            interactive=False
                        )
            
            # 模板上传标签页
            with gr.TabItem("📤 模板上传"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## 📤 上传Alpha模板")
                        gr.Markdown("💡 **使用说明**: 支持上传 .mov、.mp4、.avi 格式的Alpha模板视频文件")
                        
                        # 模板类型选择
                        template_type = gr.Radio(
                            choices=[("顶层模板", "top_layer"), ("中层模板", "middle_layer"), ("底层模板", "bottom_layer")],
                            value="top_layer",
                            label="📋 模板类型"
                        )
                        
                        # 文件上传组件
                        template_upload = gr.File(
                            label="📱 选择模板文件",
                            file_types=[".mov", ".mp4", ".avi"],
                            height=120,
                            elem_classes=["mobile-file-upload"]
                        )
                        
                        # 上传按钮
                        upload_template_btn = gr.Button("🚀 上传模板", variant="primary", size="lg")
                        
                        # 上传结果显示
                        upload_result = gr.Textbox(
                            label="上传结果",
                            lines=3,
                            interactive=False,
                            show_copy_button=True
                        )
                    
                    with gr.Column():
                        gr.Markdown("## 📋 模板管理")
                        
                        # 刷新模板列表
                        refresh_templates_btn = gr.Button("🔄 刷新模板列表", variant="secondary")
                        
                        # 显示当前模板
                        gr.Markdown("### 顶层模板")
                        top_templates_list = gr.Textbox(
                            label="顶层模板列表",
                            value="\n".join(list_templates("top_layer")),
                            lines=3,
                            interactive=False
                        )
                        
                        gr.Markdown("### 中层模板")
                        middle_templates_list = gr.Textbox(
                            label="中层模板列表",
                            value="\n".join(list_templates("middle_layer")),
                            lines=3,
                            interactive=False
                        )
                        
                        gr.Markdown("### 底层模板")
                        bottom_templates_list = gr.Textbox(
                            label="底层模板列表",
                            value="\n".join(list_templates("bottom_layer")),
                            lines=3,
                            interactive=False
                        )
            
            # 文件管理标签页
            with gr.TabItem("📂 文件管理"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## 📁 文件夹操作")
                        with gr.Row():
                            open_material_btn2 = gr.Button("📹 素材文件夹", variant="primary")
                            open_template_btn2 = gr.Button("🎭 模板文件夹", variant="primary")
                            open_output_btn2 = gr.Button("📤 输出文件夹", variant="primary")
                        folder_result = gr.Textbox(label="操作结果", lines=2, interactive=False)
                        
                        gr.Markdown("## 🔄 数据管理")
                        refresh_all_btn2 = gr.Button("🔄 刷新所有列表", variant="secondary")
                        refresh_result = gr.Textbox(label="操作结果", lines=1, interactive=False)
                    
                    with gr.Column():
                        gr.Markdown("## 📊 系统信息")
                        system_info = gr.Textbox(
                            label="系统状态",
                            value=f"操作系统: {platform.system()}\n素材目录: {MATERIAL_DIR}\n模板目录: {ALPHA_TEMPLATES_DIR}\n输出目录: {OUTPUT_DIR}",
                            lines=6,
                            interactive=False
                        )
        
        # 事件绑定
        # 全选和清空素材
        select_all_btn.click(
            fn=lambda: gr.update(value=list_materials()),
            outputs=[materials]
        )
        
        clear_all_btn.click(
            fn=lambda: gr.update(value=[]),
            outputs=[materials]
        )
         
        # 参数预设事件绑定
        def save_current_preset(name, materials_val, top_tmpl, middle_tmpl, bottom_tmpl,
                               random_enabled, random_window, advanced_enabled, random_mode,
                               random_start, random_end, random_exact, exact_enabled,
                               top_clip_enabled, top_clip_start, top_clip_duration,
                               middle_clip_enabled, middle_clip_start, middle_clip_duration,
                               bottom_clip_enabled, bottom_clip_start, bottom_clip_duration,
                               preset_val, crf_val, audio_bitrate_val, max_workers_val):
            if not name.strip():
                return "❌ 请输入预设名称", gr.update()
            
            preset_data = {
                'materials': materials_val,
                'top_template': top_tmpl,
                'middle_template': middle_tmpl,
                'bottom_template': bottom_tmpl,
                'random_timing_enabled': random_enabled,
                'random_timing_window': random_window,
                'advanced_timing_enabled': advanced_enabled,
                'random_timing_mode': random_mode,
                'random_timing_start': random_start,
                'random_timing_end': random_end,
                'random_timing_exact': random_exact,
                'exact_timing_enabled': exact_enabled,
                'top_alpha_clip_enabled': top_clip_enabled,
                'top_alpha_clip_start': top_clip_start,
                'top_alpha_clip_duration': top_clip_duration,
                'middle_alpha_clip_enabled': middle_clip_enabled,
                'middle_alpha_clip_start': middle_clip_start,
                'middle_alpha_clip_duration': middle_clip_duration,
                'bottom_alpha_clip_enabled': bottom_clip_enabled,
                'bottom_alpha_clip_start': bottom_clip_start,
                'bottom_alpha_clip_duration': bottom_clip_duration,
                'preset': preset_val,
                'crf': crf_val,
                'audio_bitrate': audio_bitrate_val,
                'max_workers': max_workers_val
            }
            
            result = save_preset(name.strip(), preset_data)
            new_choices = list_presets()
            return result, gr.update(choices=new_choices)
         
        def load_selected_preset(preset_name):
            if not preset_name:
                return ["❌ 请选择预设"] + [gr.update()] * 25
            
            preset_data = load_preset(preset_name)
            if not preset_data:
                return ["❌ 预设不存在或加载失败"] + [gr.update()] * 25
             
            return [
                f"✅ 已加载预设: {preset_name}",
                gr.update(value=preset_data.get('materials', [])),
                gr.update(value=preset_data.get('top_template', '无')),
                gr.update(value=preset_data.get('middle_template', '无')),
                gr.update(value=preset_data.get('bottom_template', '无')),
                gr.update(value=preset_data.get('random_timing_enabled', False)),
                gr.update(value=preset_data.get('random_timing_window', 40)),
                gr.update(value=preset_data.get('advanced_timing_enabled', False)),
                gr.update(value=preset_data.get('random_timing_mode', 'before_window')),
                gr.update(value=preset_data.get('random_timing_start', 10)),
                gr.update(value=preset_data.get('random_timing_end', 60)),
                gr.update(value=preset_data.get('random_timing_exact', 30)),
                gr.update(value=preset_data.get('exact_timing_enabled', False)),
                gr.update(value=preset_data.get('top_alpha_clip_enabled', False)),
                gr.update(value=preset_data.get('top_alpha_clip_start', 0)),
                gr.update(value=preset_data.get('top_alpha_clip_duration', 5)),
                gr.update(value=preset_data.get('middle_alpha_clip_enabled', False)),
                gr.update(value=preset_data.get('middle_alpha_clip_start', 0)),
                gr.update(value=preset_data.get('middle_alpha_clip_duration', 5)),
                gr.update(value=preset_data.get('bottom_alpha_clip_enabled', False)),
                gr.update(value=preset_data.get('bottom_alpha_clip_start', 0)),
                gr.update(value=preset_data.get('bottom_alpha_clip_duration', 5)),
                gr.update(value=preset_data.get('preset', Config.DEFAULT_PRESET)),
                gr.update(value=preset_data.get('crf', Config.DEFAULT_CRF)),
                gr.update(value=preset_data.get('audio_bitrate', Config.DEFAULT_AUDIO_BITRATE)),
                gr.update(value=preset_data.get('max_workers', 2))
            ]
         
        def delete_selected_preset(preset_name):
            if not preset_name:
                return "❌ 请选择要删除的预设", gr.update()
            
            result = delete_preset(preset_name)
            new_choices = list_presets()
            return result, gr.update(choices=new_choices, value=None)
        
        save_preset_btn.click(
            fn=save_current_preset,
            inputs=[
                preset_name, materials, top_template, middle_template, bottom_template,
                random_timing_enabled, random_timing_window, advanced_timing_enabled,
                random_timing_mode, random_timing_start, random_timing_end, random_timing_exact,
                exact_timing_enabled, top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                preset, crf, audio_bitrate, max_workers
            ],
            outputs=[preset_result, preset_dropdown]
        )
        
        load_preset_btn.click(
            fn=load_selected_preset,
            inputs=[preset_dropdown],
            outputs=[
                preset_result, materials, top_template, middle_template, bottom_template,
                random_timing_enabled, random_timing_window, advanced_timing_enabled,
                random_timing_mode, random_timing_start, random_timing_end, random_timing_exact,
                exact_timing_enabled, top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                preset, crf, audio_bitrate, max_workers
            ]
        )
        
        delete_preset_btn.click(
            fn=delete_selected_preset,
            inputs=[preset_dropdown],
            outputs=[preset_result, preset_dropdown]
        )
        
        # 素材上传事件绑定
        def upload_material_handler(files):
            if not files:
                return "❌ 请选择要上传的素材文件"
            
            try:
                import shutil
                import os
                
                uploaded_files = []
                failed_files = []
                
                # 确保素材目录存在
                os.makedirs(MATERIAL_DIR, exist_ok=True)
                
                # 处理多个文件
                for file in files:
                    try:
                        # 获取文件名和扩展名
                        file_name = os.path.basename(file.name)
                        file_ext = os.path.splitext(file_name)[1].lower()
                        
                        # 检查文件格式
                        if file_ext not in ['.mp4', '.avi', '.mov']:
                            failed_files.append(f"{file_name} (不支持的格式: {file_ext})")
                            continue
                        
                        # 目标文件路径
                        target_path = os.path.join(MATERIAL_DIR, file_name)
                        
                        # 检查文件是否已存在
                        if os.path.exists(target_path):
                            failed_files.append(f"{file_name} (文件已存在)")
                            continue
                        
                        # 复制文件
                        shutil.copy2(file.name, target_path)
                        uploaded_files.append(file_name)
                        
                    except Exception as e:
                        failed_files.append(f"{file_name} (错误: {str(e)})")
                
                # 生成结果报告
                result_lines = []
                if uploaded_files:
                    result_lines.append(f"✅ 成功上传 {len(uploaded_files)} 个文件:")
                    for file in uploaded_files:
                        result_lines.append(f"  📄 {file}")
                
                if failed_files:
                    result_lines.append(f"\n❌ 失败 {len(failed_files)} 个文件:")
                    for file in failed_files:
                        result_lines.append(f"  ❌ {file}")
                
                if not uploaded_files and not failed_files:
                    return "❌ 没有文件被处理"
                
                return "\n".join(result_lines)
                
            except Exception as e:
                return f"❌ 上传失败: {str(e)}"
        
        def refresh_material_lists():
            materials_list = list_materials()
            return (
                "\n".join(materials_list) if materials_list else "暂无素材",
                gr.update(choices=materials_list, value=None)
            )
        
        def delete_material_handler(material_name):
            if not material_name:
                return "❌ 请选择要删除的素材", gr.update()
            
            try:
                import os
                material_path = os.path.join(MATERIAL_DIR, material_name)
                
                if not os.path.exists(material_path):
                    return "❌ 文件不存在", gr.update()
                
                os.remove(material_path)
                
                # 刷新列表
                updated_materials = list_materials()
                
                return f"✅ 已删除素材: {material_name}", gr.update(choices=updated_materials, value=None)
                
            except Exception as e:
                return f"❌ 删除失败: {str(e)}", gr.update()
        
        def delete_selected_materials_handler(selected_materials):
            """删除选中的多个素材文件"""
            if not selected_materials:
                return "❌ 请先选择要删除的素材", gr.update(choices=list_materials(), value=[])
            
            try:
                import os
                deleted_files = []
                failed_files = []
                
                for material_name in selected_materials:
                    material_path = os.path.join(MATERIAL_DIR, material_name)
                    
                    if os.path.exists(material_path):
                        try:
                            os.remove(material_path)
                            deleted_files.append(material_name)
                        except Exception as e:
                            failed_files.append(f"{material_name}: {str(e)}")
                    else:
                        failed_files.append(f"{material_name}: 文件不存在")
                
                # 刷新列表
                updated_materials = list_materials()
                
                result_lines = []
                if deleted_files:
                    result_lines.append(f"✅ 成功删除 {len(deleted_files)} 个文件:")
                    for file in deleted_files:
                        result_lines.append(f"  ✅ {file}")
                
                if failed_files:
                    result_lines.append(f"❌ 删除失败 {len(failed_files)} 个文件:")
                    for file in failed_files:
                        result_lines.append(f"  ❌ {file}")
                
                if not deleted_files and not failed_files:
                    return "❌ 没有文件被处理", gr.update(choices=updated_materials, value=[])
                
                return "\n".join(result_lines), gr.update(choices=updated_materials, value=[])
                
            except Exception as e:
                return f"❌ 删除失败: {str(e)}", gr.update(choices=list_materials(), value=[])
        
        def delete_all_materials_handler():
            """一键删除所有素材文件"""
            try:
                import os
                all_materials = list_materials()
                
                if not all_materials:
                    return "❌ 没有素材文件可删除", gr.update(choices=[], value=[])
                
                deleted_files = []
                failed_files = []
                
                for material_name in all_materials:
                    material_path = os.path.join(MATERIAL_DIR, material_name)
                    
                    if os.path.exists(material_path):
                        try:
                            os.remove(material_path)
                            deleted_files.append(material_name)
                        except Exception as e:
                            failed_files.append(f"{material_name}: {str(e)}")
                    else:
                        failed_files.append(f"{material_name}: 文件不存在")
                
                # 刷新列表
                updated_materials = list_materials()
                
                result_lines = []
                result_lines.append(f"💥 一键全删操作完成！")
                
                if deleted_files:
                    result_lines.append(f"✅ 成功删除 {len(deleted_files)} 个文件:")
                    for file in deleted_files:
                        result_lines.append(f"  ✅ {file}")
                
                if failed_files:
                    result_lines.append(f"❌ 删除失败 {len(failed_files)} 个文件:")
                    for file in failed_files:
                        result_lines.append(f"  ❌ {file}")
                
                return "\n".join(result_lines), gr.update(choices=updated_materials, value=[])
                
            except Exception as e:
                return f"❌ 一键全删失败: {str(e)}", gr.update(choices=list_materials(), value=[])
        
        upload_material_btn.click(
            fn=upload_material_handler,
            inputs=[material_upload],
            outputs=[material_upload_result]
        )
        
        refresh_materials_btn.click(
            fn=refresh_material_lists,
            outputs=[materials_list_display, material_to_delete]
        )
        
        delete_material_btn.click(
            fn=delete_material_handler,
            inputs=[material_to_delete],
            outputs=[delete_material_result, material_to_delete]
        )
        
        # 文件管理事件绑定
        open_material_btn2.click(
            fn=lambda: open_folder_cross_platform(MATERIAL_DIR),
            outputs=[folder_result]
        )
        
        open_template_btn2.click(
            fn=lambda: open_folder_cross_platform(ALPHA_TEMPLATES_DIR),
            outputs=[folder_result]
        )
        
        open_output_btn2.click(
            fn=lambda: open_folder_cross_platform(OUTPUT_DIR),
            outputs=[folder_result]
        )
        
        refresh_all_btn2.click(
            fn=lambda: "✅ 已刷新所有列表",
            outputs=[refresh_result]
        )
        
        # 模板上传事件绑定
        def upload_template_handler(file, template_type):
            if file is None:
                return "❌ 请选择要上传的模板文件"
            
            try:
                import shutil
                import os
                
                # 获取文件名和扩展名
                file_name = os.path.basename(file.name)
                file_ext = os.path.splitext(file_name)[1].lower()
                
                # 检查文件格式
                if file_ext not in ['.mov', '.mp4', '.avi']:
                    return f"❌ 不支持的文件格式: {file_ext}，请上传 .mov、.mp4 或 .avi 文件"
                
                # 确定目标目录
                target_dir = os.path.join(ALPHA_TEMPLATES_DIR, template_type)
                os.makedirs(target_dir, exist_ok=True)
                
                # 目标文件路径
                target_path = os.path.join(target_dir, file_name)
                
                # 检查文件是否已存在
                if os.path.exists(target_path):
                    return f"❌ 文件已存在: {file_name}，请重命名后重新上传"
                
                # 复制文件
                shutil.copy2(file.name, target_path)
                
                return f"✅ 模板上传成功！\n📁 类型: {template_type}\n📄 文件: {file_name}\n📍 路径: {target_path}"
                
            except Exception as e:
                return f"❌ 上传失败: {str(e)}"
        
        def refresh_template_lists():
            top_list = list_templates("top_layer")
            middle_list = list_templates("middle_layer")
            bottom_list = list_templates("bottom_layer")
            
            return (
                "\n".join(top_list) if top_list else "暂无模板",
                "\n".join(middle_list) if middle_list else "暂无模板",
                "\n".join(bottom_list) if bottom_list else "暂无模板"
            )
        
        upload_template_btn.click(
            fn=upload_template_handler,
            inputs=[template_upload, template_type],
            outputs=[upload_result]
        )
        
        refresh_templates_btn.click(
            fn=refresh_template_lists,
            outputs=[top_templates_list, middle_templates_list, bottom_templates_list]
        )
        
        # 事件绑定
        start_batch_btn.click(
            fn=process_batch_with_features,
            inputs=[
                materials, top_template, middle_template, bottom_template,
                random_timing_enabled, random_timing_window, advanced_timing_enabled,
                random_timing_mode, random_timing_start, random_timing_end, random_timing_exact,
                exact_timing_enabled, top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                preset, crf, audio_bitrate, max_workers
            ],
            outputs=[batch_result]
        )
        
        stop_batch_btn.click(
            fn=emergency_stop,
            outputs=[batch_result]
        )
        
        emergency_stop_btn.click(
            fn=emergency_stop,
            outputs=[batch_result]
        )
        
        # 文件夹操作事件
        open_material_btn.click(
            fn=lambda: open_folder_cross_platform(MATERIAL_DIR),
            outputs=[batch_result]
        )
        
        open_template_btn.click(
            fn=lambda: open_folder_cross_platform(ALPHA_TEMPLATES_DIR),
            outputs=[batch_result]
        )
        
        open_output_btn.click(
            fn=lambda: open_folder_cross_platform(OUTPUT_DIR),
            outputs=[batch_result]
        )
        
        # 刷新功能
        def refresh_all_lists():
            materials_list = list_materials()
            top_templates = ["无"] + list_templates("top_layer")
            middle_templates = ["无"] + list_templates("middle_layer")
            bottom_templates = ["无"] + list_templates("bottom_layer")
            
            return (
                gr.update(choices=materials_list, value=[]),
                gr.update(choices=top_templates, value="无"),
                gr.update(choices=middle_templates, value="无"),
                gr.update(choices=bottom_templates, value="无"),
                f"✅ 已刷新所有列表 - 素材: {len(materials_list)}个"
            )
        
        refresh_all_btn.click(
            fn=refresh_all_lists,
            outputs=[materials, top_template, middle_template, bottom_template, batch_result]
        )
        

        
        # 视频预览和下载事件
        def refresh_video_list():
            videos = list_output_videos()
            return gr.update(choices=videos, value=None)
        
        refresh_videos_btn.click(
            fn=refresh_video_list,
            outputs=[output_videos]
        )
        
        output_videos.change(
            fn=get_video_preview_and_info,
            inputs=[output_videos],
            outputs=[video_preview, video_info]
        )
        
        delete_video_btn.click(
            fn=delete_output_video,
            inputs=[output_videos],
            outputs=[batch_result, output_videos]
        )
        
        # 参数预设事件绑定
        def save_preset_handler(name, top_tmpl, middle_tmpl, bottom_tmpl, random_enabled, random_window, 
                              advanced_enabled, random_mode, random_start, random_end, random_exact,
                              exact_enabled, top_clip_enabled, top_clip_start, top_clip_duration,
                              middle_clip_enabled, middle_clip_start, middle_clip_duration,
                              bottom_clip_enabled, bottom_clip_start, bottom_clip_duration,
                              preset_val, crf_val, audio_bitrate_val, max_workers_val):
            if not name.strip():
                return "❌ 请输入预设名称", gr.update()
            
            preset_data = {
                'top_template': top_tmpl,
                'middle_template': middle_tmpl,
                'bottom_template': bottom_tmpl,
                'random_timing_enabled': random_enabled,
                'random_timing_window': random_window,
                'advanced_timing_enabled': advanced_enabled,
                'random_timing_mode': random_mode,
                'random_timing_start': random_start,
                'random_timing_end': random_end,
                'random_timing_exact': random_exact,
                'exact_timing_enabled': exact_enabled,
                'top_alpha_clip_enabled': top_clip_enabled,
                'top_alpha_clip_start': top_clip_start,
                'top_alpha_clip_duration': top_clip_duration,
                'middle_alpha_clip_enabled': middle_clip_enabled,
                'middle_alpha_clip_start': middle_clip_start,
                'middle_alpha_clip_duration': middle_clip_duration,
                'bottom_alpha_clip_enabled': bottom_clip_enabled,
                'bottom_alpha_clip_start': bottom_clip_start,
                'bottom_alpha_clip_duration': bottom_clip_duration,
                'preset': preset_val,
                'crf': crf_val,
                'audio_bitrate': audio_bitrate_val,
                'max_workers': max_workers_val
            }
            
            result = save_preset(name.strip(), preset_data)
            updated_choices = list_presets()
            return result, gr.update(choices=updated_choices)
        
        def load_preset_handler(preset_name):
            if not preset_name:
                return "❌ 请选择要加载的预设", *([gr.update()] * 24)
            
            try:
                preset_data = load_preset(preset_name)
                if preset_data is None:
                    return "❌ 预设加载失败", *([gr.update()] * 24)
                
                # 处理音频比特率格式兼容性
                audio_bitrate_val = preset_data.get('audio_bitrate', 192)
                if isinstance(audio_bitrate_val, str):
                    # 如果是字符串格式如"192k"，提取数字部分
                    audio_bitrate_val = int(audio_bitrate_val.replace('k', '').replace('K', ''))
                
                return (
                    f"✅ 已加载预设: {preset_name}",
                    gr.update(value=preset_data.get('top_template', '无')),
                    gr.update(value=preset_data.get('middle_template', '无')),
                    gr.update(value=preset_data.get('bottom_template', '无')),
                    gr.update(value=preset_data.get('random_timing_enabled', False)),
                    gr.update(value=preset_data.get('random_timing_window', 40)),
                    gr.update(value=preset_data.get('advanced_timing_enabled', False)),
                    gr.update(value=preset_data.get('random_timing_mode', 'between_range')),
                    gr.update(value=preset_data.get('random_timing_start', 10)),
                    gr.update(value=preset_data.get('random_timing_end', 50)),
                    gr.update(value=preset_data.get('random_timing_exact', 30)),
                    gr.update(value=preset_data.get('exact_timing_enabled', False)),
                    gr.update(value=preset_data.get('top_alpha_clip_enabled', False)),
                    gr.update(value=preset_data.get('top_alpha_clip_start', 0)),
                gr.update(value=preset_data.get('top_alpha_clip_duration', 5)),
                gr.update(value=preset_data.get('middle_alpha_clip_enabled', False)),
                gr.update(value=preset_data.get('middle_alpha_clip_start', 0)),
                gr.update(value=preset_data.get('middle_alpha_clip_duration', 5)),
                gr.update(value=preset_data.get('bottom_alpha_clip_enabled', False)),
                gr.update(value=preset_data.get('bottom_alpha_clip_start', 0)),
                gr.update(value=preset_data.get('bottom_alpha_clip_duration', 5)),
                gr.update(value=preset_data.get('preset', Config.DEFAULT_PRESET)),
                gr.update(value=preset_data.get('crf', Config.DEFAULT_CRF)),
                gr.update(value=audio_bitrate_val),
                gr.update(value=preset_data.get('max_workers', 2))
            )
            except Exception as e:
                print(f"预设加载错误: {e}")
                return f"❌ 预设加载失败: {str(e)}", *([gr.update()] * 24)
        
        def delete_preset_handler(preset_name):
            if not preset_name:
                return "❌ 请选择要删除的预设", gr.update()
            
            result = delete_preset(preset_name)
            updated_choices = list_presets()
            return result, gr.update(choices=updated_choices, value=None)
        
        save_preset_btn.click(
            fn=save_preset_handler,
            inputs=[
                preset_name, top_template, middle_template, bottom_template,
                random_timing_enabled, random_timing_window, advanced_timing_enabled,
                random_timing_mode, random_timing_start, random_timing_end, random_timing_exact,
                exact_timing_enabled, top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                preset, crf, audio_bitrate, max_workers
            ],
            outputs=[preset_result, preset_dropdown]
        )
        
        load_preset_btn.click(
            fn=load_preset_handler,
            inputs=[preset_dropdown],
            outputs=[
                preset_result, top_template, middle_template, bottom_template,
                random_timing_enabled, random_timing_window, advanced_timing_enabled,
                random_timing_mode, random_timing_start, random_timing_end, random_timing_exact,
                exact_timing_enabled, top_alpha_clip_enabled, top_alpha_clip_start, top_alpha_clip_duration,
                middle_alpha_clip_enabled, middle_alpha_clip_start, middle_alpha_clip_duration,
                bottom_alpha_clip_enabled, bottom_alpha_clip_start, bottom_alpha_clip_duration,
                preset, crf, audio_bitrate, max_workers
            ]
        )
        
        delete_preset_btn.click(
            fn=delete_preset_handler,
            inputs=[preset_dropdown],
            outputs=[preset_result, preset_dropdown]
        )
        
        # 控制组显示/隐藏逻辑
        def toggle_timing_controls(random_enabled, advanced_enabled):
            # 基础控制组：启用随机但未启用高级时显示
            basic_visible = random_enabled and not advanced_enabled
            # 高级控制组：启用高级时显示
            advanced_visible = advanced_enabled
            return gr.update(visible=basic_visible), gr.update(visible=advanced_visible)
        
        # 绑定事件
        random_timing_enabled.change(
            fn=toggle_timing_controls,
            inputs=[random_timing_enabled, advanced_timing_enabled],
            outputs=[basic_controls, advanced_controls]
        )
        
        advanced_timing_enabled.change(
            fn=toggle_timing_controls,
            inputs=[random_timing_enabled, advanced_timing_enabled],
            outputs=[basic_controls, advanced_controls]
        )
        
        # 素材加工功能事件绑定
        
        resize_1080p_btn.click(
            fn=batch_resolution_convert,
            inputs=[processing_materials, resolution_choice, resize_mode, processing_preset, processing_crf],
            outputs=[processing_result]
        )
        
        trim_ending_btn.click(
            fn=trim_video_ending,
            inputs=[processing_materials, trim_seconds, processing_preset, processing_crf],
            outputs=[processing_result]
        )
        
        split_segments_btn.click(
            fn=split_video_segments,
            inputs=[processing_materials, segment_min, segment_max, processing_preset, processing_crf],
            outputs=[processing_result]
        )
        
        refresh_processing_materials_btn.click(
            fn=lambda: gr.update(choices=get_material_choices_for_processing()),
            outputs=[processing_materials]
        )
        
        # 素材加工页面的文件上传功能
        def upload_processing_material_handler(files):
            if not files:
                return "❌ 请选择要上传的素材文件"
            
            try:
                import shutil
                import os
                
                uploaded_files = []
                failed_files = []
                
                # 确保素材目录存在
                os.makedirs(MATERIAL_DIR, exist_ok=True)
                
                # 处理多个文件
                for file in files:
                    try:
                        # 获取文件名和扩展名
                        file_name = os.path.basename(file.name)
                        file_ext = os.path.splitext(file_name)[1].lower()
                        
                        # 检查文件格式
                        if file_ext not in ['.mp4', '.avi', '.mov']:
                            failed_files.append(f"{file_name} (不支持的格式: {file_ext})")
                            continue
                        
                        # 目标文件路径
                        target_path = os.path.join(MATERIAL_DIR, file_name)
                        
                        # 检查文件是否已存在
                        if os.path.exists(target_path):
                            failed_files.append(f"{file_name} (文件已存在)")
                            continue
                        
                        # 复制文件
                        shutil.copy2(file.name, target_path)
                        uploaded_files.append(file_name)
                        
                    except Exception as e:
                        failed_files.append(f"{file_name}: {str(e)}")
                
                # 生成结果信息
                result_lines = []
                if uploaded_files:
                    result_lines.append(f"✅ 成功上传 {len(uploaded_files)} 个文件")
                
                if failed_files:
                    result_lines.append(f"❌ 失败 {len(failed_files)} 个文件")
                    for failed in failed_files[:3]:  # 只显示前3个失败的文件
                        result_lines.append(f"  • {failed}")
                    if len(failed_files) > 3:
                        result_lines.append(f"  • ... 还有 {len(failed_files) - 3} 个文件失败")
                
                return "\n".join(result_lines) if result_lines else "❌ 上传失败"
                
            except Exception as e:
                return f"❌ 上传过程中发生错误: {str(e)}"
        
        def upload_and_refresh_processing_materials(files):
            # 先执行上传
            upload_result = upload_processing_material_handler(files)
            # 然后刷新素材列表
            updated_choices = get_material_choices_for_processing()
            return upload_result, gr.update(choices=updated_choices)
        
        upload_processing_material_btn.click(
            fn=upload_and_refresh_processing_materials,
            inputs=[processing_material_upload],
            outputs=[processing_upload_result, processing_materials]
        )
        
        # 素材加工页面的全选、清空、删除功能
        select_all_processing_btn.click(
            fn=lambda: gr.update(value=get_material_choices_for_processing()),
            outputs=[processing_materials]
        )
        
        clear_all_processing_btn.click(
            fn=lambda: gr.update(value=[]),
            outputs=[processing_materials]
        )
        
        delete_selected_materials_btn.click(
            fn=delete_selected_materials_handler,
            inputs=[processing_materials],
            outputs=[processing_result, processing_materials]
        )
        
        delete_all_materials_btn.click(
            fn=delete_all_materials_handler,
            inputs=[],
            outputs=[processing_result, processing_materials]
        )
    
    return demo

def find_free_port():
    """查找一个空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

# 主程序入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量Alpha视频合成工具')
    parser.add_argument('--port', type=int, default=None, help='Web界面端口号')
    parser.add_argument('--share', action='store_true', help='启用Gradio共享链接')
    
    args = parser.parse_args()
    
    # 直接启动Web界面模式
    print("🚀 启动批量Alpha视频合成工具 - Web界面模式")
    
    try:
        demo = create_gradio_interface()
        port = args.port or find_free_port()
        
        print(f"📡 使用端口: {port}")
        print(f"🌐 本地访问: http://localhost:{port}")
        if args.share:
            print(f"📱 共享链接: 启动后将显示Gradio共享链接，可在手机等设备访问")
        print(f"💡 移动端优化: 界面已适配手机访问，建议横屏使用")
        
        # 检测是否为EXE环境
        is_exe = getattr(sys, 'frozen', False)
        
        demo.launch(
                server_port=port,
                share=args.share,  # 根据命令行参数决定是否开启共享
                inbrowser=True,  # 始终自动打开浏览器
                show_error=True,
                server_name="127.0.0.1" if not args.share else "0.0.0.0",  # 本地模式使用127.0.0.1
                favicon_path=None,
                quiet=is_exe,  # EXE模式下减少输出
                app_kwargs={
                    "docs_url": None,
                    "redoc_url": None
                }
            )
    except Exception as e:
        print(f"❌ Web界面启动失败: {str(e)}")
        sys.exit(1)