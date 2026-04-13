# 代码修复汇总报告

**修复日期**: 2026-04-11

---

## 🔴 高危问题修复（P0）

### 1. 命令注入漏洞 ✅
**文件**: `backend/services/frame_extractor.py`

**修复内容**:
- 添加 `import shlex`
- 使用 `shlex.quote(video_path)` 转义视频路径

```python
# 修复前
safe_video_path = video_path

# 修复后
safe_video_path = shlex.quote(video_path)
```

---

### 2. 路径遍历漏洞 ✅
**文件**: `backend/models.py`

**修复内容**:
- 添加 `ALLOWED_VIDEO_DIRECTORIES` 白名单配置
- 修改 `resolve_path_input()` 验证路径范围

```python
ALLOWED_VIDEO_DIRECTORIES = [
    Path(d).expanduser().resolve()
    for d in os.getenv("ALLOWED_VIDEO_DIRS", ".").split(":")
]

def resolve_path_input(path: str | Path) -> Path:
    resolved = Path(sanitize_path_input(path)).expanduser().resolve()
    for allowed_dir in ALLOWED_VIDEO_DIRECTORIES:
        try:
            resolved.relative_to(allowed_dir)
            return resolved
        except ValueError:
            continue
    raise ValueError(f"Path '{path}' is outside allowed directories")
```

---

### 3. 路由冲突 ✅
**文件**: `backend/api/frames.py`

**修复内容**:
- 修改路径避免冲突：`/{video_id}` → `/video/{video_id}`

```python
# 修复前
@router.get("/{video_id}")

# 修复后
@router.get("/video/{video_id}")
```

**⚠️ 注意**: 前端调用此API的路径需要同步更新。

---

### 4. 无认证授权 ✅
**文件**: `backend/auth.py` (新建), `backend/main.py`

**修复内容**:
- 创建 `backend/auth.py` API Key认证模块
- 使用 `secrets.compare_digest()` 防止时序攻击
- 为敏感路由添加认证依赖

```python
# backend/auth.py
async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    expected_key = get_api_key()
    if api_key is None:
        raise HTTPException(status_code=401, detail="API Key header missing")
    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

# backend/main.py
protected = [Depends(verify_api_key)]
app.include_router(videos_router, prefix="/api", dependencies=protected)
```

---

### 5. CORS配置过宽 ✅
**文件**: `backend/main.py`

**修复内容**:
- 从 `allow_origins=["*"]` 改为环境变量配置

```python
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
```

---

## 🟡 中风险问题修复（P1）

### 6. FFmpeg调用效率 ✅
**文件**: `backend/services/frame_extractor.py`, `backend/services/pipeline.py`

**修复内容**:
- 添加 `start_time` 和 `duration` 参数支持
- 使用 `-ss` 和 `-t` 参数只提取指定时间段

```python
# frame_extractor.py
def build_ffmpeg_command(
    ...,
    start_time: float | None = None,
    duration: float | None = None,
) -> list[str]:
    cmd = [ffmpeg_command, "-y"]
    if start_time is not None and start_time > 0:
        cmd.extend(["-ss", str(start_time)])
    cmd.extend(["-i", safe_video_path])
    if duration is not None and duration > 0:
        cmd.extend(["-t", str(duration)])
    ...

# pipeline.py - 使用精确提取
segment_duration = end_ts - start_ts
frames = extract_frames(
    video["filepath"],
    str(temp_dir),
    start_time=start_ts,
    duration=segment_duration,
)
```

---

### 7. 文件句柄泄漏 ✅
**文件**: `backend/services/frame_dedup.py`

**修复内容**:
- 使用上下文管理器 `with Image.open()` 确保文件句柄关闭

```python
# 修复前
prev_hash = imagehash.phash(Image.open(frame_paths[0]))

# 修复后
with Image.open(frame_paths[0]) as img:
    prev_hash = imagehash.phash(img)
```

---

### 8. 视频流获取错误 ✅
**文件**: `backend/services/video_import.py`

**修复内容**:
- 显式查找视频流（检查 width/height），而非直接取 `streams[0]`

```python
video_stream = None
for stream in streams:
    if stream.get("width") and stream.get("height"):
        video_stream = stream
        break

width = video_stream.get("width", 0) if video_stream else 0
height = video_stream.get("height", 0) if video_stream else 0
```

---

### 9. 前端竞态条件 ✅
**文件**: `frontend/src/pages/ResultDetailPage.tsx`

**修复内容**:
- 添加 `cancelled` 标志防止快速切换显示旧数据

```typescript
useEffect(() => {
  let cancelled = false;
  api.getResult(frameId).then((data) => {
    if (!cancelled) setDetail(data);
  }).catch(() => {
    if (!cancelled) setDetail({});
  });
  return () => { cancelled = true; };
}, [frameId]);
```

---

### 10. 未使用导入清理 ✅
**文件**: `frontend/src/pages/ImportPage.tsx`

**修复内容**:
- 移除未使用的 `useRef` 导入

```typescript
// 修复前
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

// 修复后
import { FormEvent, useEffect, useMemo, useState } from "react";
```

---

## 📁 新增文件

1. **`backend/auth.py`** - API Key认证模块
2. **`frontend/.env.example`** - 前端环境变量模板
3. **`SECURITY_FIXES.md`** - 详细修复文档

---

## ⚙️ 环境变量配置

### 后端 `.env`
```bash
# 新增安全配置
API_KEY=your-secure-random-key-here
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
ALLOWED_VIDEO_DIRS=.:./作弊视频
```

### 前端 `frontend/.env`
```bash
# 新增认证配置
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_API_KEY=your-secure-random-key-here
```

---

## 📝 待办事项

### 必须完成（启动前）
- [ ] 复制 `.env.example` 为 `.env` 并设置 `API_KEY`
- [ ] 复制 `frontend/.env.example` 为 `frontend/.env` 并设置 `VITE_API_KEY`
- [ ] 更新前端 API 调用路径（`/frames/${videoId}` → `/frames/video/${videoId}`）

### 建议后续优化
- [ ] 添加数据库索引（`video_assets.status`, `processing_tasks.status`）
- [ ] 添加请求限流（`slowapi`）
- [ ] 配置Docker资源限制
- [ ] 添加FTS5自动同步触发器

---

## ✅ 验证清单

```bash
# 1. Python语法检查
python -m py_compile backend/*.py backend/**/*.py

# 2. 类型检查（如有mypy）
mypy backend/

# 3. 前端类型检查
cd frontend && npm run build

# 4. 测试
pytest -q
cd frontend && npm test
```

---

## 🔒 安全测试

```bash
# 测试命令注入防护（应返回400）
curl -X POST "http://localhost:8000/api/videos/import" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "; whoami > /tmp/pwned"}'

# 测试路径遍历防护（应返回400）
curl -X POST "http://localhost:8000/api/videos/import" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "../../../etc/passwd"}'

# 测试无API Key访问（应返回401）
curl "http://localhost:8000/api/videos"

# 测试有效API Key访问（应正常返回）
curl "http://localhost:8000/api/videos" \
  -H "X-API-Key: your-api-key"
```

---

**修复完成时间**: 2026-04-11

所有P0和P1级别问题已修复。建议部署前进行全面测试。