# Codex 提示词：视频画面内容检索平台 MVP

## 使用方式

将以下内容作为 Codex 的初始提示词，用于引导 Codex 构建项目。

---

## 提示词正文

```
你是一个全栈开发工程师，负责构建一个「视频画面内容检索平台」的 MVP 版本。

## 项目背景

这是一个内部视频排查工具。目标视频是**无语音的屏幕录制视频**（考试场景的作弊行为检测），需要通过多模态大模型理解视频画面内容，然后建立索引供关键词检索。

核心流程：视频导入 → FFmpeg 关键帧提取 → Kimi K2.5 API 画面理解 → 结构化文本存储 → 全文检索 → 结果展示

## 技术栈要求

- **后端**: Python 3.11+, FastAPI
- **前端**: React + TypeScript + TailwindCSS（或 Next.js）
- **数据库**: SQLite + FTS5 全文检索
- **视频处理**: FFmpeg（关键帧提取）
- **多模态 API**: Kimi K2.5（通过 OpenAI SDK 兼容接口调用）
- **任务队列**: 使用 asyncio + 内存队列（MVP 阶段），后续可升级为 Celery

## 项目结构

```
video-visual-search/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理（API Key、抽帧间隔等）
│   ├── models.py               # SQLAlchemy/SQLite 数据模型
│   ├── services/
│   │   ├── video_import.py     # 视频导入服务
│   │   ├── frame_extractor.py  # FFmpeg 关键帧提取
│   │   ├── vision_analyzer.py  # Kimi K2.5 API 调用
│   │   ├── indexer.py          # 全文索引构建
│   │   └── searcher.py         # 检索服务
│   ├── api/
│   │   ├── videos.py           # 视频管理 API
│   │   ├── tasks.py            # 任务管理 API
│   │   ├── search.py           # 检索 API
│   │   └── keywords.py         # 关键词库 API
│   └── prompts/
│       └── screen_analysis.py  # Prompt 模板管理
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ImportPage.tsx      # 视频导入页
│   │   │   ├── TasksPage.tsx       # 任务管理页
│   │   │   ├── SearchPage.tsx      # 搜索页
│   │   │   ├── ResultDetailPage.tsx # 结果详情页
│   │   │   └── KeywordsPage.tsx    # 关键词库页
│   │   └── components/
│   │       ├── VideoPlayer.tsx     # 视频播放器（支持时间点跳转）
│   │       ├── FrameGallery.tsx    # 帧截图展示
│   │       └── SearchResultCard.tsx # 搜索结果卡片
├── data/
│   ├── db/                     # SQLite 数据库
│   ├── frames/                 # 提取的关键帧图片
│   └── videos/                 # 导入的视频文件（或软链接）
└── requirements.txt
```

## 核心模块实现要求

### 1. 关键帧提取（frame_extractor.py）

使用 FFmpeg 从视频中按固定间隔提取关键帧：

```python
import subprocess
import os

def extract_frames(video_path: str, output_dir: str, interval: int = 3) -> list[dict]:
    """
    从视频中提取关键帧
    Args:
        video_path: 视频文件路径
        output_dir: 帧图片输出目录
        interval: 抽帧间隔（秒），默认 3 秒
    Returns:
        [{"frame_index": 0, "timestamp": 0.0, "image_path": "frame_0000.jpg"}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        os.path.join(output_dir, "frame_%04d.jpg")
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    # 返回帧列表，每帧包含 index、timestamp、image_path
```

### 2. 多模态画面理解（vision_analyzer.py）

调用 Kimi K2.5 API 理解每帧画面内容：

```python
import base64
import json
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

SCREEN_ANALYSIS_PROMPT = """你是一个屏幕录制视频内容分析专家。请分析这个屏幕截图，严格返回以下 JSON 格式（不要返回其他内容）：

{
  "screen_text": "画面中可见的所有文字内容（尽可能完整）",
  "application": "当前使用的应用程序或网站名称",
  "url": "如果可见，当前浏览器地址栏的 URL，否则为空字符串",
  "operation": "用户正在执行的操作描述",
  "ai_tool_detected": true或false,
  "ai_tool_name": "如检测到 AI 工具，给出工具名称，否则为空字符串",
  "code_visible": true或false,
  "code_content_summary": "如可见代码，给出代码片段摘要，否则为空字符串",
  "risk_indicators": ["检测到的可疑行为列表，如果没有则为空数组"],
  "summary": "一句话总结画面内容"
}

重点关注以下行为：
1. 使用 AI 对话平台（ChatGPT、Claude、Kimi、文心一言、通义千问等）
2. 使用云平台 AI 服务（AWS Bedrock、Azure OpenAI、Google Vertex AI 等）
3. 通过 CLI/终端调用 AI API 或 SDK
4. 在 IDE 中使用 AI 代码助手（GitHub Copilot、Cursor、Codeium 等）
5. 打开预先准备好的文件、文档或答案
6. 从外部来源（网页、文件、聊天窗口）复制粘贴内容
7. 访问题库、答案网站或在线考试作弊工具"""

async def analyze_frame(image_path: str) -> dict:
    """分析单帧画面内容，返回结构化 JSON"""
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    completion = client.chat.completions.create(
        model="kimi-k2.5",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                },
                {"type": "text", "text": SCREEN_ANALYSIS_PROMPT}
            ]
        }],
        extra_body={"thinking": {"type": "disabled"}}  # 关闭思考模式，加速响应
    )

    raw_text = completion.choices[0].message.content
    # 解析 JSON，处理可能的 markdown 代码块包裹
    clean = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(clean)
```

### 3. 数据模型（models.py）

```python
# 核心表结构
VideoAsset:
  - id: INTEGER PRIMARY KEY
  - filename: TEXT
  - filepath: TEXT
  - duration: REAL (秒)
  - format: TEXT
  - resolution: TEXT
  - status: TEXT (pending/processing/completed/failed)
  - created_at: DATETIME

ProcessingTask:
  - id: INTEGER PRIMARY KEY
  - video_id: INTEGER REFERENCES VideoAsset(id)
  - task_type: TEXT (frame_extract/vision_analyze/index_build)
  - status: TEXT (pending/running/completed/failed)
  - progress: REAL (0.0-1.0)
  - error_message: TEXT
  - created_at: DATETIME
  - updated_at: DATETIME

VideoFrame:
  - id: INTEGER PRIMARY KEY
  - video_id: INTEGER REFERENCES VideoAsset(id)
  - frame_index: INTEGER
  - timestamp: REAL (秒)
  - image_path: TEXT

FrameAnalysis:
  - id: INTEGER PRIMARY KEY
  - frame_id: INTEGER REFERENCES VideoFrame(id)
  - video_id: INTEGER REFERENCES VideoAsset(id)
  - raw_json: TEXT (原始 JSON 响应)
  - screen_text: TEXT
  - application: TEXT
  - operation: TEXT
  - ai_tool_detected: BOOLEAN
  - ai_tool_name: TEXT
  - summary: TEXT
  - risk_indicators: TEXT (JSON 数组)
  - timestamp: REAL

-- FTS5 虚拟表用于全文检索
SearchableContent (FTS5):
  - video_id
  - frame_id
  - timestamp
  - content (合并 screen_text + operation + summary + ai_tool_name)

KeywordSet:
  - id: INTEGER PRIMARY KEY
  - name: TEXT
  - category: TEXT
  - terms: TEXT (JSON 数组)
  - created_at: DATETIME
```

### 4. 检索服务（searcher.py）

```python
def search(query: str, filters: dict = None) -> list[dict]:
    """
    全文检索，返回命中结果
    - 使用 SQLite FTS5 的 MATCH 语法
    - 支持按视频 ID、时间范围筛选
    - 返回结果包含：video_name, timestamp, matched_text, frame_image_path, analysis_summary
    """
```

### 5. API 接口设计

```
POST   /api/videos/import          # 导入单个视频
POST   /api/videos/import-folder   # 导入文件夹
GET    /api/videos                  # 获取视频列表
GET    /api/videos/{id}             # 获取视频详情

GET    /api/tasks                   # 获取任务列表
POST   /api/tasks/{id}/retry       # 重试失败任务
GET    /api/tasks/{id}/progress    # 获取任务进度

POST   /api/search                 # 执行检索
GET    /api/search/results/{id}    # 获取检索结果详情

GET    /api/keywords               # 获取关键词库列表
POST   /api/keywords               # 创建关键词库
PUT    /api/keywords/{id}          # 更新关键词库
DELETE /api/keywords/{id}          # 删除关键词库
POST   /api/keywords/{id}/scan     # 基于词库执行筛查

GET    /api/frames/{video_id}      # 获取视频的所有帧
GET    /api/frames/{frame_id}/image # 获取帧截图
GET    /api/frames/{frame_id}/analysis # 获取帧分析结果
```

### 6. 前端核心页面

**搜索页（最重要）**：
- 顶部搜索栏：支持关键词输入
- 筛选器：按视频名称、时间范围、AI工具检测结果筛选
- 结果列表：每条结果显示视频名称、命中时间点、命中文本摘要、命中帧缩略图
- 点击结果进入详情页

**结果详情页**：
- 左侧：视频播放器（支持跳转到命中时间点）
- 右侧上方：命中帧截图（支持左右浏览相邻帧）
- 右侧下方：结构化分析结果（JSON 展开视图）
- 底部：时间线标注（标记所有命中时间点）

## 重要注意事项

1. **API 调用必须有速率控制**：Kimi K2.5 API 有限流，使用 asyncio.Semaphore 控制并发数（建议初始值 3-5）
2. **Prompt 返回 JSON 需要鲁棒解析**：模型可能返回 markdown 包裹的 JSON，需要清理
3. **成本感知**：每帧一次 API 调用，100 个视频 × 每个 60 帧 = 6000 次调用。在 UI 上显示预估成本
4. **帧图片存储**：使用 JPEG 格式压缩，quality=85 即可，减少存储占用
5. **国内端点**：Kimi API 国内使用 `https://api.moonshot.cn/v1`，海外使用 `https://api.moonshot.ai/v1`
6. **关闭思考模式**：调用时传入 `extra_body={"thinking": {"type": "disabled"}}` 以加速响应和降低成本
7. **视频文件不要复制**：使用软链接或记录原始路径，避免大文件重复存储

## 启动顺序

请按以下顺序构建：

1. 先搭建项目骨架和数据库模型
2. 实现 FFmpeg 关键帧提取功能并验证
3. 实现 Kimi K2.5 API 调用并验证（先用单张图片测试）
4. 实现全文检索
5. 实现后端 API
6. 实现前端搜索页和结果详情页
7. 实现关键词库管理
8. 端到端联调测试

请现在开始构建这个项目。
```

---

## 补充说明

### 环境变量

```bash
export MOONSHOT_API_KEY="your-api-key-here"
export FRAME_INTERVAL=3          # 抽帧间隔（秒）
export API_CONCURRENCY=3         # API 并发数
export DB_PATH="data/db/search.db"
```

### 依赖安装

```bash
pip install fastapi uvicorn openai sqlalchemy aiosqlite python-multipart
# FFmpeg 需要系统级安装
# apt install ffmpeg 或 brew install ffmpeg
```
