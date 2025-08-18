# 新建配置文件
class Config:
    # 默认设置
    DEFAULT_PORT = 7877
    DEFAULT_HOST = "0.0.0.0"
    
    # 视频处理参数
    DEFAULT_CRF = 23
    DEFAULT_PRESET = "medium"
    DEFAULT_AUDIO_BITRATE = 192
    
    # 文件路径
    MATERIAL_DIR = "material_videos"
    ALPHA_TEMPLATES_DIR = "alpha_templates"
    OUTPUT_DIR = "output_processed_videos"
    
    # 素材加工专用文件夹
    RESOLUTION_CONVERTED_DIR = "pixels_trans"  # 分辨率转换后的文件
    TRIMMED_DIR = "End_cut"  # 结尾裁剪后的文件
    SEGMENTS_DIR = "segments"  # 视频切分后的文件