# 后端 Dockerfile
FROM python:3.12-slim

# 安装 FFmpeg、ffprobe 和 curl（用于健康检查）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 设置工作目录
WORKDIR /app

# 先复制依赖与迁移配置，利用 Docker 缓存层
COPY requirements.txt alembic.ini ./

# 安装运行时依赖，并在构建阶段直接验证 OCR 相关导入链
RUN python -m pip install --no-cache-dir -r requirements.txt && \
    python -c "import numpy; print(f'numpy={numpy.__version__}'); from rapidocr_onnxruntime import RapidOCR; RapidOCR(); print('RapidOCR import check passed')"

# 复制后端代码
COPY backend/ ./backend/

# 验证后端懒加载 OCR 模块至少可以安全导入
RUN python -c "from backend.services.local_ocr import get_local_ocr; ocr = get_local_ocr(); print(type(ocr).__name__)"

# 创建数据目录并赋予非 root 用户权限
RUN mkdir -p /app/data/db /app/data/frames && chown -R appuser:appuser /app/data

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
