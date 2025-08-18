# 🚀 批量Alpha视频合成工具 - 安装指南

## 📋 系统要求

- Python 3.11+
- FFmpeg (系统级安装)
- 至少 4GB 可用内存
- 支持的操作系统：macOS, Linux, Windows

## 🛠️ 安装步骤

### 1. 创建并激活虚拟环境

```bash
# 创建 Python 3.11 虚拟环境
python3.11 -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate

# Windows:
# venv\Scripts\activate
```

### 2. 升级 pip 并安装依赖

```bash
# 升级 pip 到最新版本
pip install --upgrade pip

# 安装所有项目依赖
pip install -r requirements.txt
```

### 3. 验证安装

```bash
# 测试核心模块导入
python -c "import gradio, cv2, numpy, PIL; print('✅ 所有依赖安装成功')"
```

### 4. 启动应用

#### 方式一：使用 run_app.py（推荐）
```bash
python run_app.py
```

#### 方式二：使用 uvicorn
```bash
uvicorn run_app:app --host 0.0.0.0 --port 7860 --reload
```

### 5. 访问应用

- 打开浏览器访问：http://localhost:7860
- 如果使用 run_app.py，应用会自动打开浏览器
- 清除浏览器缓存（Ctrl/Cmd+Shift+R）以确保最新版本

## 🔧 故障排除

### 常见问题

1. **FFmpeg 未找到**
   ```bash
   # macOS (使用 Homebrew)
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt update && sudo apt install ffmpeg
   
   # Windows
   # 下载 FFmpeg 并添加到 PATH
   ```

2. **OpenCV 安装失败**
   ```bash
   # 如果 opencv-python 安装失败，尝试无头版本
   pip uninstall opencv-python
   pip install opencv-python-headless==4.12.0.88
   ```

3. **内存不足**
   - 确保至少有 4GB 可用内存
   - 减少并行处理线程数
   - 关闭其他占用内存的应用

4. **端口冲突**
   ```bash
   # 使用不同端口启动
   uvicorn run_app:app --host 0.0.0.0 --port 8080
   ```

### 日志检查

- 应用日志：`app.log`
- 终端输出：查看启动时的错误信息
- 浏览器控制台：F12 查看前端错误

## 📦 依赖说明

### 核心框架
- **Gradio 5.36.2**: Web UI 框架
- **FastAPI 0.116.1**: 后端 API 框架
- **UVicorn**: ASGI 服务器

### 多媒体处理
- **python-ffmpeg 2.0.12**: 现代 FFmpeg 绑定
- **ffmpeg-python 0.2.0**: 传统 FFmpeg 库（兼容性）
- **OpenCV 4.12.0.88**: 计算机视觉库
- **Pillow 11.3.0**: 图像处理库
- **PyDub 0.25.1**: 音频处理库

### 数值计算
- **NumPy 2.3.1**: 数值计算基础
- **tqdm 4.67.1**: 进度条显示

### 系统工具
- **psutil 7.0.0**: 系统监控
- **python-dotenv 1.1.1**: 环境变量管理

## 🎯 下一步

安装完成后，您可以：

1. 📁 将素材视频放入 `material_videos/` 目录
2. 🎭 将 Alpha 模板放入 `alpha_templates/` 相应层级目录
3. 🚀 开始批量处理视频
4. 📊 监控处理状态和进度
5. 🗜️ 使用内置压缩工具优化模板文件

## 📞 技术支持

如果遇到问题，请检查：
- Python 版本是否为 3.11+
- 所有依赖是否正确安装
- FFmpeg 是否可在命令行中使用
- 系统资源是否充足