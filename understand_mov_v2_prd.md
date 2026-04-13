# Video Visual Search V2 — PRD

> **项目代号**: understand_mov V2
> **作者**: Francis (刘钢)
> **日期**: 2026-04-08
> **状态**: Draft
> **目标**: 在 V1 基础上重构，核心解决处理速度问题，保留已验证的产品逻辑

---

## 1. 背景与动机

### V1 已验证的价值

V1 完成了从 MVP 到可用工具的闭环：导入录屏视频 → 抽帧 → 视觉模型分析 → FTS5 检索 → 定位可疑时间段。已在考试录屏审查场景中验证了产品逻辑。

### V1 核心问题

| 问题 | 影响 |
|------|------|
| 每帧都调云端视觉模型 | 80%+ 的帧是重复画面，浪费时间和 token |
| 并发默认为 1 | 处理速度被人为压到最低 |
| 无帧去重 | 相邻帧画面几乎一样仍然逐帧分析 |
| 无两阶段扫描 | 无法先粗后精，长视频处理效率极低 |
| 内存任务队列 | 重启丢任务 |
| 无本地预处理 | 所有智能分析都依赖远程 API |

### V2 目标

**一句话**：同样的视频，处理时间降到 V1 的 1/5 以下，token 消耗降到 1/3 以下。

---

## 2. 产品定位（不变）

面向屏幕录制视频的审查检索平台。把无声录屏视频转成可检索的结构化帧数据，帮助快速定位以下场景：

- 使用 AI 对话平台或 AI 编码助手
- 疑似借助 AI 完成考试/编程任务
- 打开预先准备的答案、代码、文档
- 通过关键词全文搜索快速定位可疑时间段

---

## 3. 架构设计

### 3.1 整体架构

```
前后端分离，同仓库管理

backend/          FastAPI + SQLite FTS5 + FFmpeg
  ├── services/
  │   ├── frame_extractor.py      抽帧
  │   ├── frame_dedup.py          [NEW] 帧去重（pHash/SSIM）
  │   ├── local_ocr.py            [NEW] 本地 OCR 预筛
  │   ├── vision_analyzer.py      云端视觉模型分析
  │   ├── pipeline.py             [NEW] 两阶段处理编排
  │   ├── searcher.py             FTS5 检索
  │   ├── indexer.py              索引构建
  │   ├── task_queue.py           [CHANGED] 持久化任务队列
  │   └── json_utils.py           模型 JSON 容错解析
  ├── api/
  ├── db.py
  ├── config.py
  └── main.py

frontend/         React 19 + Vite + Tailwind
```

### 3.2 技术栈

| 层 | 技术 | 变化 |
|---|------|------|
| Web 框架 | FastAPI | 不变 |
| 数据库 | SQLite + FTS5 | 不变 |
| 视频处理 | FFmpeg / ffprobe | 不变 |
| 帧去重 | Pillow + imagehash (pHash) | **新增** |
| 本地 OCR | PaddleOCR 或 RapidOCR | **新增** |
| 视觉模型 | OpenAI-compatible API (GLM-4V / Kimi) | 不变 |
| 任务队列 | SQLite-backed 持久队列 | **升级** |
| 前端 | React 19 + Vite + Tailwind + React Router | 不变 |

### 3.3 新增依赖

```
# requirements.txt 新增
imagehash>=4.3
Pillow>=10.0
rapidocr-onnxruntime>=1.3    # 轻量本地 OCR，无需 GPU
jieba>=0.42                   # V1 已有
```

---

## 4. 核心改进：处理流水线

### 4.1 V2 处理流程（两阶段）

```
用户导入视频
    │
    ▼
Stage 0: 元数据探测 (ffprobe)
    │
    ▼
Stage 1: 粗扫 ──────────────────────────────────
    │  ① FFmpeg 大间隔抽帧 (10s)
    │  ② pHash 帧去重 (阈值 ≤ 8)
    │  ③ 本地 OCR 提取屏幕文字
    │  ④ 关键词命中检测 (匹配预设词库)
    │  ⑤ 命中帧写入 FTS，标记可疑时间段
    │
    ▼
Stage 2: 精扫（仅对可疑时间段）─────────────────
    │  ① FFmpeg 小间隔抽帧 (3s)，仅覆盖可疑段 ± 缓冲
    │  ② pHash 帧去重
    │  ③ 云端视觉模型结构化分析
    │  ④ 分析结果写入 DB + FTS
    │
    ▼
完成，前端可检索
```

### 4.2 帧去重模块

```python
# backend/services/frame_dedup.py

from PIL import Image
import imagehash

def deduplicate_frames(
    frame_paths: list[str],
    hash_threshold: int = 8
) -> list[str]:
    """
    输入：按时间排序的帧文件路径列表
    输出：去重后的帧路径列表
    逻辑：相邻帧 pHash 汉明距离 ≤ threshold 则跳过
    """
    if not frame_paths:
        return []

    kept = [frame_paths[0]]
    prev_hash = imagehash.phash(Image.open(frame_paths[0]))

    for path in frame_paths[1:]:
        curr_hash = imagehash.phash(Image.open(path))
        if abs(curr_hash - prev_hash) > hash_threshold:
            kept.append(path)
            prev_hash = curr_hash

    return kept
```

**预期效果**：录屏视频中大量静止或微动画面，帧去重可过滤 50-80% 的重复帧。

### 4.3 本地 OCR 预筛模块

```python
# backend/services/local_ocr.py

from rapidocr_onnxruntime import RapidOCR

ocr_engine = RapidOCR()

def extract_screen_text(image_path: str) -> str:
    """本地 OCR 提取屏幕文字，毫秒级，零成本"""
    result, _ = ocr_engine(image_path)
    if not result:
        return ""
    return " ".join([line[1] for line in result])

def check_keywords(text: str, keywords: list[str]) -> list[str]:
    """返回命中的关键词列表"""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]
```

**预期效果**：粗扫阶段 100% 本地完成，零 API 调用。只有 OCR 命中关键词的时间段才进入精扫。

### 4.4 两阶段编排

```python
# backend/services/pipeline.py

class ProcessingPipeline:
    """两阶段处理编排"""

    async def process_video(self, video_id: str, mode: str = "two_stage"):
        if mode == "quick":
            await self.stage_coarse(video_id)
        elif mode == "full":
            await self.stage_coarse(video_id)
            await self.stage_fine(video_id)
        elif mode == "deep":
            # 全帧精扫，兼容 V1 行为
            await self.stage_fine_all(video_id)

    async def stage_coarse(self, video_id: str):
        """粗扫：大间隔抽帧 → 去重 → 本地 OCR → 关键词命中 → 标记可疑段"""
        frames = extract_frames(video_path, interval=COARSE_INTERVAL)
        unique_frames = deduplicate_frames(frames)
        for frame in unique_frames:
            text = extract_screen_text(frame.path)
            hits = check_keywords(text, active_keywords)
            if hits:
                mark_suspicious_segment(video_id, frame.timestamp, buffer=15)
            index_frame_text(video_id, frame, text)  # 粗扫结果也入 FTS

    async def stage_fine(self, video_id: str):
        """精扫：仅对可疑时间段做云端模型分析"""
        segments = get_suspicious_segments(video_id)
        for seg in segments:
            frames = extract_frames(video_path,
                interval=FINE_INTERVAL,
                start=seg.start - BUFFER,
                end=seg.end + BUFFER)
            unique_frames = deduplicate_frames(frames)
            await analyze_batch_with_model(unique_frames, concurrency=API_CONCURRENCY)
```

---

## 5. 配置体系

### 5.1 新增配置项

```env
# ===== 粗扫配置 =====
COARSE_INTERVAL=10              # 粗扫抽帧间隔（秒）
HASH_THRESHOLD=8                # pHash 去重阈值（0-64，越小越严格）
SUSPICIOUS_BUFFER=15            # 可疑段前后缓冲（秒）

# ===== 精扫配置 =====
FINE_INTERVAL=3                 # 精扫抽帧间隔（秒）
API_CONCURRENCY=3               # 模型并发数
API_MAX_RETRIES=3               # 模型重试次数

# ===== 处理模式 =====
PROCESSING_MODE=two_stage       # quick | two_stage | deep

# ===== 模型配置（沿用 V1） =====
VISION_PROVIDER=zhipu
VISION_API_KEY=
VISION_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL_NAME=glm-4.6v-flash
VISION_ANALYZER_MODE=live

# ===== 基础配置（沿用 V1） =====
FFMPEG_COMMAND=ffmpeg
FFPROBE_COMMAND=ffprobe
FRAME_MAX_WIDTH=1280
FRAME_JPEG_QUALITY=5
DB_PATH=data/db/search.db
DATA_DIR=data
FRAMES_DIR=data/frames
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

### 5.2 处理模式说明

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `quick` | 仅粗扫（本地 OCR + FTS） | 快速批量筛查，不调模型 |
| `two_stage` | 粗扫 + 对可疑段精扫 | **默认推荐**，平衡速度和精度 |
| `deep` | 全帧精扫（V1 行为） | 对重点视频做最细粒度分析 |

---

## 6. 数据库变更

### 6.1 新增表

```sql
-- 可疑时间段表
CREATE TABLE IF NOT EXISTS suspicious_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_time REAL NOT NULL,          -- 起始秒数
    end_time REAL NOT NULL,            -- 结束秒数
    trigger_type TEXT NOT NULL,        -- 'keyword' | 'model'
    trigger_detail TEXT,               -- 命中的关键词或模型标签
    stage TEXT NOT NULL DEFAULT 'coarse',  -- 'coarse' | 'fine'
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES video_assets(id)
);

-- 持久化任务队列（替代内存队列）
CREATE TABLE IF NOT EXISTS task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    stage TEXT NOT NULL,               -- 'coarse' | 'fine'
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | running | completed | failed
    progress REAL DEFAULT 0,
    total_frames INTEGER DEFAULT 0,
    processed_frames INTEGER DEFAULT 0,
    skipped_frames INTEGER DEFAULT 0,  -- 被去重跳过的帧数
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES video_assets(id)
);

-- 帧 OCR 缓存（避免重复 OCR）
CREATE TABLE IF NOT EXISTS frame_ocr_cache (
    frame_id INTEGER PRIMARY KEY,
    ocr_text TEXT,
    keyword_hits TEXT,                 -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (frame_id) REFERENCES video_frames(id)
);
```

### 6.2 已有表保持不变

- `video_assets`
- `video_frames`
- `frame_analysis`
- `frame_analysis_fts`
- `keyword_sets`

---

## 7. API 变更

### 7.1 新增接口

```
POST /api/videos/{video_id}/process
  Body: { "mode": "quick" | "two_stage" | "deep" }
  说明: 手动触发指定模式的处理

GET /api/videos/{video_id}/segments
  说明: 获取可疑时间段列表

POST /api/videos/{video_id}/rescan
  Body: { "stage": "coarse" | "fine" }
  说明: 对已处理视频重新扫描

GET /api/stats
  说明: 全局统计（总视频数、总帧数、跳过帧数、token 消耗）
```

### 7.2 变更接口

```
POST /api/videos/import
  新增返回字段: estimated_coarse_time, estimated_frames

GET /api/tasks
  新增返回字段: stage, skipped_frames
```

### 7.3 保留接口（不变）

```
GET  /api/health
GET  /api/videos
POST /api/videos/import-folder
POST /api/search
GET  /api/search/results/{frame_id}
GET  /api/frames/{frame_id}/image
GET  /api/videos/{video_id}/file
GET  /api/keywords
POST /api/keywords
DELETE /api/keywords/{keyword_set_id}
POST /api/keywords/{keyword_set_id}/scan
```

---

## 8. 前端变更

### 8.1 导入页

- 新增"处理模式"选择：快速扫描 / 标准扫描 / 深度扫描
- 显示预估处理时间
- 导入后显示粗扫进度和精扫进度分别展示

### 8.2 任务页

- 每个任务显示 stage 标签（粗扫/精扫）
- 新增"跳过帧数"列，展示帧去重效果
- 支持从页面直接触发重试

### 8.3 检索页

- 搜索结果标注来源：OCR 命中 / 模型分析命中
- 新增"可疑时间段"视图，聚合展示

### 8.4 详情页

- 不变，保持 V1 逻辑

---

## 9. 性能预估

以一个 60 分钟录屏视频为例：

| 指标 | V1 (deep) | V2 (two_stage) | 提升 |
|------|-----------|----------------|------|
| 粗扫抽帧数 | - | 360 帧 (10s间隔) | - |
| 粗扫去重后 | - | ~100 帧 | - |
| 粗扫耗时 | - | ~30 秒 (纯本地) | - |
| 可疑段占比 | 100% | ~20% | - |
| 精扫帧数 | 1200 帧 | ~80 帧 | **15x 减少** |
| 精扫去重后 | 1200 帧 | ~50 帧 | **24x 减少** |
| 模型调用次数 | 1200 次 | ~50 次 | **24x 减少** |
| 并发 (API_CONCURRENCY) | 1 | 3 | 3x |
| 总处理时间 | ~60 分钟 | ~3 分钟 | **20x 加速** |
| Token 消耗 | ~1200 次 | ~50 次 | **24x 降低** |

---

## 10. 实施计划

### Phase 1: 基础重构（Day 1-2）

- [ ] 项目初始化，迁移 V1 可复用代码
- [ ] 持久化任务队列替换内存队列
- [ ] 配置体系升级，支持新配置项
- [ ] 数据库 schema 升级

### Phase 2: 帧去重 + 本地 OCR（Day 3-4）

- [ ] 实现 `frame_dedup.py`（pHash 去重）
- [ ] 实现 `local_ocr.py`（RapidOCR 集成）
- [ ] 粗扫流程完整跑通
- [ ] 单元测试覆盖

### Phase 3: 两阶段编排（Day 5-6）

- [ ] 实现 `pipeline.py`（两阶段编排）
- [ ] 可疑时间段标记与存储
- [ ] 精扫仅覆盖可疑段
- [ ] 并发提升到 3-5

### Phase 4: 前端适配（Day 7-8）

- [ ] 导入页增加处理模式选择
- [ ] 任务页适配两阶段展示
- [ ] 检索页标注命中来源
- [ ] 页面重试按钮

### Phase 5: 集成测试 + Docker（Day 9-10）

- [ ] 端到端测试（导入→粗扫→精扫→检索→详情）
- [ ] Docker Compose 更新
- [ ] 文档更新
- [ ] 性能基准测试

---

## 11. 已知限制（V2 不解决）

- SQLite 仍为单机方案，不支持高并发多用户
- 不支持在线视频 URL 导入
- 不支持向量检索
- 不支持视频内音频分析
- CORS 仍需在生产环境收紧

---

## 12. 成功标准

| 指标 | 目标 |
|------|------|
| 60 分钟视频 two_stage 处理时间 | ≤ 5 分钟 |
| 模型调用次数相比 V1 | 减少 ≥ 80% |
| 粗扫（quick 模式）无 API 调用 | 100% 本地 |
| 服务重启后任务可恢复 | 支持 |
| V1 全部检索功能保留 | 100% |

---

## 13. 文件清单

本 PRD 对应的关键新增/变更文件：

```
backend/services/frame_dedup.py       [NEW]  帧去重
backend/services/local_ocr.py         [NEW]  本地 OCR
backend/services/pipeline.py          [NEW]  两阶段编排
backend/services/task_queue.py        [CHANGED] 持久化队列
backend/config.py                     [CHANGED] 新配置项
backend/db.py                         [CHANGED] 新表
backend/api/videos.py                 [CHANGED] 新接口
frontend/src/pages/ImportPage.tsx     [CHANGED] 模式选择
frontend/src/pages/TasksPage.tsx      [CHANGED] 两阶段展示
```
