# 批量Alpha视频合成工具

这是一个用于批量处理视频的工具，可以将原始素材视频与多层Alpha通道模板进行合成，生成叠加效果的视频。

## 功能特点

- 🎬 **多层模板叠加**：支持底层、中间层和顶层三层模板叠加
- 🔄 **批量处理**：一次处理多个素材视频
- 🎯 **Alpha通道支持**：正确处理带有透明度的视频
- 🔍 **Alpha通道检测**：检查视频是否包含Alpha通道
- 📊 **实时进度显示**：处理过程中显示详细进度
- 🎛️ **简洁界面**：易用的Gradio Web界面

## 目录结构

```
./
├── material_videos/           # 原始素材视频目录
├── alpha_templates/          # Alpha模板目录
│   ├── bottom_layer/         # 底层模板（最接近原素材）
│   ├── middle_layer/         # 中间层模板
│   └── top_layer/            # 顶层模板（最上层）
├── output_processed_videos/  # 处理后的输出视频
├── run.py                    # 程序启动入口
├── gradio_ui.py              # Gradio界面实现
├── main.py                   # 核心处理逻辑
└── utils.py                  # 工具函数
```

## 安装与使用

### 前置要求

- Python 3.6+
- FFmpeg（用于视频处理）

### 安装依赖

```bash
# 安装FFmpeg（macOS）
brew install ffmpeg

# 安装Python依赖
pip install gradio
```

### 启动程序

```bash
python run.py
```

启动后，访问 http://localhost:7877 打开Web界面。

## 使用方法

1. 将原始素材视频放入 `material_videos` 目录
2. 将Alpha通道模板视频放入对应的模板目录：
   - `alpha_templates/bottom_layer/`：底层模板
   - `alpha_templates/middle_layer/`：中间层模板
   - `alpha_templates/top_layer/`：顶层模板
3. 启动程序并打开Web界面
4. 选择要处理的素材视频和模板
5. 点击「开始批量处理」按钮
6. 处理完成后，输出视频将保存在 `output_processed_videos` 目录

## Alpha通道检测

点击「检查Alpha通道」按钮可以检查当前所有模板和素材视频是否包含Alpha通道。这对于确保模板视频正确保留透明度非常有用。

## 命令行使用

除了Web界面外，也可以通过命令行直接使用核心功能：

```bash
python main.py
```

命令行模式提供以下选项：
1. 批量处理所有素材
2. 重新处理使用alpha-2的素材
3. 重新处理使用alpha-1的素材
4. 处理单个素材

## 注意事项

- 模板视频应当包含Alpha通道（透明度），推荐使用MOV格式
- 如果从剪映导出Alpha视频，建议打包成ZIP后传输，以避免Alpha通道丢失
- 可以使用 `check_alpha.py` 脚本检查视频是否包含Alpha通道