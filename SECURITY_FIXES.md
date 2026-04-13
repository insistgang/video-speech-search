# 安全漏洞修复方案

**生成日期**: 2026-04-11  
**风险等级**: 高危 (P0)

---

## 🔴 问题1: 命令注入漏洞

### 位置
`backend/services/frame_extractor.py:52`

### 漏洞描述
视频路径直接传入 `subprocess.run()`，恶意构造的路径（如 `; rm -rf /` 或 `$(whoami)`）可执行任意系统命令。

### 当前代码
```python
def build_ffmpeg_command(
    video_path: str,
    output_dir: str,
    ffmpeg_command: str = "ffmpeg",
    interval: int = 3,
    max_width: int = 1280,
    jpeg_quality: int = 5,
) -> list[str]:
    output_pattern = str(Path(output_dir) / "frame_%04d.jpg")
    video_filters = [
        f"fps=1/{interval}",
        f"scale={max_width}:-2:flags=lanczos:force_original_aspect_ratio=decrease",
    ]
    return [
        ffmpeg_command,
        "-y",
        "-i",
        video_path,  # ⚠️ 未转义
        "-vf",
        ",".join(video_filters),
        "-q:v",
        str(jpeg_quality),
        output_pattern,
    ]

def extract_frames(...):
    ...
    subprocess.run(command, capture_output=True, text=True, ...)  # ⚠️ 危险
```

### 修复方案

**方式A: 使用列表参数（推荐）**
```python
import shlex
from pathlib import Path

def build_ffmpeg_command(
    video_path: str,
    output_dir: str,
    ffmpeg_command: str = "ffmpeg",
    interval: int = 3,
    max_width: int = 1280,
    jpeg_quality: int = 5,
) -> list[str]:
    # 转义视频路径防止命令注入
    safe_video_path = shlex.quote(video_path)
    output_pattern = str(Path(output_dir) / "frame_%04d.jpg")
    video_filters = [
        f"fps=1/{interval}",
        f"scale={max_width}:-2:flags=lanczos:force_original_aspect_ratio=decrease",
    ]
    return [
        ffmpeg_command,
        "-y",
        "-i",
        safe_video_path,
        "-vf",
        ",".join(video_filters),
        "-q:v",
        str(jpeg_quality),
        output_pattern,
    ]
```

**方式B: 验证路径白名单**
```python
def validate_video_path(path: str, allowed_dirs: list[str]) -> Path:
    """验证视频路径是否在允许的目录内。"""
    resolved = Path(path).expanduser().resolve()
    for allowed in allowed_dirs:
        if str(resolved).startswith(str(Path(allowed).resolve())):
            return resolved
    raise ValueError(f"Path {path} is outside allowed directories")
```

---

## 🔴 问题2: 路径遍历漏洞

### 位置
`backend/models.py:70-71`

### 漏洞描述
`resolve_path_input()` 未限制路径范围，攻击者可使用 `../../../etc/passwd` 访问任意系统文件。

### 当前代码
```python
def resolve_path_input(path: str | Path) -> Path:
    return Path(sanitize_path_input(path)).expanduser().resolve()  # ⚠️ 无范围限制
```

### 修复方案

**步骤1: 修改 `backend/models.py`**
```python
from pathlib import Path
from typing import Any
import os

from pydantic import BaseModel, Field


# 允许的根目录（从环境变量读取，默认当前目录）
ALLOWED_VIDEO_DIRECTORIES = [
    Path(d).expanduser().resolve()
    for d in os.getenv("ALLOWED_VIDEO_DIRS", ".").split(":")
]


def resolve_path_input(path: str | Path) -> Path:
    """解析并验证路径，确保在允许的目录范围内。"""
    resolved = Path(sanitize_path_input(path)).expanduser().resolve()
    
    # 路径遍历验证
    for allowed_dir in ALLOWED_VIDEO_DIRECTORIES:
        try:
            resolved.relative_to(allowed_dir)
            return resolved
        except ValueError:
            continue
    
    raise ValueError(
        f"Path '{path}' is outside allowed directories: "
        f"{[str(d) for d in ALLOWED_VIDEO_DIRECTORIES]}"
    )


def normalize_path(path: str | Path) -> str:
    """规范化路径为绝对路径字符串。"""
    return str(resolve_path_input(path))
```

**步骤2: 更新 `.env.example`**
```bash
# 允许的视频目录（用冒号分隔多个目录）
ALLOWED_VIDEO_DIRS=/app/videos:/data/videos
```

**步骤3: 验证调用点**
检查所有调用 `resolve_path_input()` 的位置，确保捕获 `ValueError`：
- `backend/api/videos.py:import_video()`
- `backend/api/videos.py:import_folder()`

---

## 🔴 问题3: 路由冲突

### 位置
`backend/api/frames.py:14-19`

### 漏洞描述
路径参数 `/{video_id}` 和 `/{frame_id}/image` 存在冲突，`/123/image` 会被第一个路由匹配为 `video_id="123/image"`。

### 当前代码
```python
@router.get("/{video_id}")           # 匹配所有 /{anything}
def list_frames(video_id: int, ...):
    ...

@router.get("/{frame_id}/image")     # 永远不会匹配 /number/image
async def get_frame_image(frame_id: int, ...):
    ...
```

### 修复方案

**修改 `backend/api/frames.py`**
```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.api.deps import get_context


router = APIRouter(prefix="/frames", tags=["frames"])


@router.get("/video/{video_id}")  # ✅ 明确区分路径
def list_frames(video_id: int, context=Depends(get_context)) -> list[dict]:
    """获取视频的所有帧列表。"""
    return context.repository.get_frames_for_video(video_id)


@router.get("/{frame_id}/image")  # ✅ 现在能正确匹配
async def get_frame_image(frame_id: int, context=Depends(get_context)):
    """获取帧图片文件。"""
    frame = context.repository.get_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    image_path = Path(frame["image_path"])
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Frame image missing")
    return FileResponse(image_path)


@router.get("/{frame_id}/analysis")
def get_frame_analysis(frame_id: int, context=Depends(get_context)) -> dict:
    """获取帧分析结果。"""
    analysis = context.repository.get_frame_analysis(frame_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis
```

**注意**: 此修改会改变API路径，需要同步更新前端调用：
- `frontend/src/api.ts` 中的 `listFrames()` 函数路径从 `/frames/${videoId}` 改为 `/frames/video/${videoId}`

---

## 🔴 问题4: 无认证授权

### 位置
所有API端点 (`backend/main.py`)

### 漏洞描述
API无任何认证机制，任何人可调用接口导入视频、查看结果、删除数据。

### 修复方案

**步骤1: 创建API Key认证模块 `backend/auth.py`**
```python
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key() -> str:
    """从环境变量获取API Key，如未设置则生成随机值。"""
    key = os.getenv("API_KEY")
    if not key:
        # 生产环境必须设置 API_KEY
        if os.getenv("ENV", "development") == "production":
            raise RuntimeError("API_KEY must be set in production environment")
        # 开发环境使用随机生成的key（每次重启变化）
        key = secrets.token_urlsafe(32)
        print(f"[WARN] Using randomly generated API_KEY for development: {key}")
    return key


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """验证API Key。"""
    expected_key = get_api_key()
    
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key header missing",
            headers={"WWW-Authenticate": f"ApiKey {API_KEY_NAME}"},
        )
    
    # 使用secrets.compare_digest防止时序攻击
    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": f"ApiKey {API_KEY_NAME}"},
        )
    
    return api_key
```

**步骤2: 修改 `backend/main.py` 添加认证**
```python
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from backend.auth import verify_api_key  # 新增


# 公开路由（健康检查）
app.include_router(health_router, prefix="/api")

# 受保护路由
protected_dependencies = [Depends(verify_api_key)]
app.include_router(videos_router, prefix="/api", dependencies=protected_dependencies)
app.include_router(tasks_router, prefix="/api", dependencies=protected_dependencies)
app.include_router(search_router, prefix="/api", dependencies=protected_dependencies)
app.include_router(keywords_router, prefix="/api", dependencies=protected_dependencies)
app.include_router(frames_router, prefix="/api", dependencies=protected_dependencies)
app.include_router(stats_router, prefix="/api", dependencies=protected_dependencies)
```

**步骤3: 更新 `.env.example`**
```bash
# API认证（生产环境必须设置）
API_KEY=your-secure-random-key-here
```

**步骤4: 前端适配 (`frontend/src/api.ts`)**
```typescript
const API_KEY = import.meta.env.VITE_API_KEY || "";

async function request<T>(method: string, endpoint: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,  // 添加认证头
  };
  // ... 其余代码
}
```

---

## 🟡 问题5: FFmpeg调用效率

### 位置
`backend/services/pipeline.py:312-321`

### 问题描述
`stage_fine` 对每个可疑片段都提取整个视频，然后过滤，效率极低。

### 当前代码
```python
# 低效：提取整个视频
frames = extract_frames(
    video["filepath"],
    str(temp_dir),
    interval=self.settings.fine_interval,
    ...
)
# 再过滤
ranged_frames = [f for f in frames if start_ts <= f["timestamp"] <= end_ts]
```

### 修复方案

**步骤1: 增强 `frame_extractor.py` 支持时间段提取**
```python
def build_ffmpeg_command(
    video_path: str,
    output_dir: str,
    ffmpeg_command: str = "ffmpeg",
    interval: int = 3,
    max_width: int = 1280,
    jpeg_quality: int = 5,
    start_time: float | None = None,  # 新增
    duration: float | None = None,     # 新增
) -> list[str]:
    import shlex
    safe_video_path = shlex.quote(video_path)
    output_pattern = str(Path(output_dir) / "frame_%04d.jpg")
    video_filters = [
        f"fps=1/{interval}",
        f"scale={max_width}:-2:flags=lanczos:force_original_aspect_ratio=decrease",
    ]
    
    cmd = [ffmpeg_command, "-y"]
    
    # 添加起始时间（快速定位，不重新编码）
    if start_time is not None:
        cmd.extend(["-ss", str(start_time)])
    
    cmd.extend(["-i", safe_video_path])
    
    # 添加持续时间
    if duration is not None:
        cmd.extend(["-t", str(duration)])
    
    cmd.extend([
        "-vf", ",".join(video_filters),
        "-q:v", str(jpeg_quality),
        output_pattern,
    ])
    
    return cmd
```

**步骤2: 修改 `pipeline.py` 使用时间段提取**
```python
# 计算片段持续时间
segment_duration = end_ts - start_ts

frames = extract_frames(
    video["filepath"],
    str(temp_dir),
    ffmpeg_command=self.settings.ffmpeg_command,
    interval=self.settings.fine_interval,
    max_width=self.settings.frame_max_width,
    jpeg_quality=self.settings.frame_jpeg_quality,
    start_time=start_time,      # 新增
    duration=segment_duration,  # 新增
)

# 移除过滤步骤（已精确提取）
# ranged_frames = [f for f in frames if ...]  # 不需要了
```

---

## 🛡️ 附加安全加固

### 1. 收紧CORS配置
```python
# backend/main.py
from backend.config import get_settings

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # 从配置读取，默认仅localhost
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
```

### 2. 添加请求限流
```bash
pip install slowapi
```

```python
# backend/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(...)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/health")
@limiter.limit("10/minute")  # 健康检查限流
def health_check(...):
    ...
```

### 3. 错误信息脱敏
```python
# backend/main.py
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 生产环境不返回详细错误
    if os.getenv("ENV") == "production":
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
    # 开发环境返回详细信息
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )
```

---

## ✅ 修复检查清单

- [ ] 命令注入: 添加 `shlex.quote()` 到 `frame_extractor.py`
- [ ] 路径遍历: 修改 `models.py` 添加 `ALLOWED_VIDEO_DIRECTORIES`
- [ ] 路由冲突: 修改 `frames.py` 路径为 `/video/{video_id}`
- [ ] 无认证: 创建 `auth.py` 并在 `main.py` 应用
- [ ] FFmpeg效率: 添加 `-ss`/`-t` 参数支持
- [ ] CORS配置: 修改为环境变量控制
- [ ] 请求限流: 添加 `slowapi` 限流
- [ ] 前端适配: 更新API路径和添加认证头
- [ ] 环境变量: 更新 `.env.example`
- [ ] 测试验证: 确认所有修复生效

---

## 📝 测试用例

### 测试命令注入防护
```bash
# 应被拒绝或安全处理
curl -X POST "http://localhost:8000/api/videos/import" \
  -H "Content-Type: application/json" \
  -d '{"path": "; whoami > /tmp/pwned"}'
```

### 测试路径遍历防护
```bash
# 应返回400错误
curl -X POST "http://localhost:8000/api/videos/import" \
  -H "Content-Type: application/json" \
  -d '{"path": "../../../etc/passwd"}'
```

### 测试API认证
```bash
# 无API Key应返回401
curl "http://localhost:8000/api/videos"

# 有API Key应正常返回
curl "http://localhost:8000/api/videos" \
  -H "X-API-Key: your-api-key"
```

---

**注意**: 所有修复应先在本机测试通过，再部署到生产环境。