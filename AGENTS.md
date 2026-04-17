# 视频画面内容检索平台

本文件包含 AI 编码助手处理本项目时需要了解的关键信息。

## 项目概述

这是一个**视频画面内容检索 MVP**，用于导入无声屏幕录制视频，使用 FFmpeg 提取 JPEG 帧，将帧发送给多模态视觉模型进行结构化理解，将扁平化文本索引到 SQLite FTS5 中，并提供 React UI 用于查看匹配结果。

**使用场景**：屏幕录制视频分析，用于检测考试/编程场景中的 AI 工具使用、可疑操作和预先准备好的内容。

### 核心功能
- 导入单个视频或批量导入文件夹
- 通过 FFmpeg 以可配置间隔提取帧
- 使用多模态视觉模型分析关键帧（默认 Zhipu GLM-4.6v-flashx，兼容 Moonshot / OpenAI 格式）
- 通过 SQLite FTS5 进行全文搜索
- 支持 quick / two_stage / deep 三种处理模式
- 关键词集合管理用于批量筛选
- 带视频播放的帧级结果详情
- 任务失败后可从前端或 API 重试

## 技术栈

### 后端
| 组件 | 技术 |
|-----------|------------|
| 框架 | FastAPI (Python 3.12+) |
| 数据库 | SQLite with FTS5 extension |
| AI 服务 | Zhipu GLM-4.6v-flashx（兼容 OpenAI 格式，同时支持 Moonshot / Kimi CLI） |
| 视频处理 | FFmpeg (ffprobe + ffmpeg) |
| 任务队列 | SQLite 持久化任务队列（`SQLiteTaskQueue`），支持重启恢复 |
| 配置 | Pydantic 设置与环境变量 |

### 前端
| 组件 | 技术 |
|-----------|------------|
| 框架 | React 19.x |
| 构建工具 | Vite 7.x |
| 路由 | React Router DOM 7.x |
| 样式 | Tailwind CSS 3.x |
| 测试 | Vitest + jsdom + Testing Library |
| 语言 | TypeScript 5.x |

### 依赖
- `fastapi`, `uvicorn` - Web 框架和服务器
- `openai` - 兼容 OpenAI 格式的 API 客户端
- `pydantic` - 数据验证和设置
- `python-multipart` - 文件上传处理
- `pytest` - 测试框架
- `slowapi` - 请求限流
- `jieba` - 中文分词
- `python-dotenv` - 环境变量加载
- `imagehash`, `Pillow` - 帧去重
- `rapidocr-onnxruntime` - 本地 OCR 粗筛

## 项目结构

```
.
├── backend/                    # FastAPI 后端
│   ├── api/                    # API 路由处理器
│   │   ├── deps.py            # 依赖注入
│   │   ├── frames.py          # 帧图片服务
│   │   ├── health.py          # 健康检查端点
│   │   ├── keywords.py        # 关键词集合 CRUD
│   │   ├── search.py          # 搜索端点
│   │   ├── stats.py           # 平台统计端点
│   │   ├── tasks.py           # 任务队列管理
│   │   └── videos.py          # 视频导入、列表、处理、重扫
│   ├── prompts/               # AI 提示模板
│   │   └── screen_analysis.py # 视觉分析提示
│   ├── services/              # 业务逻辑
│   │   ├── frame_extractor.py # FFmpeg 帧提取
│   │   ├── frame_dedup.py     # 帧去重
│   │   ├── indexer.py         # 搜索内容构建器
│   │   ├── json_utils.py      # JSON 解析工具
│   │   ├── pipeline.py        # 核心处理流水线（coarse/fine/deep）
│   │   ├── searcher.py        # FTS 搜索服务
│   │   ├── task_queue.py      # SQLite 持久化任务队列
│   │   ├── video_import.py    # 视频导入服务
│   │   └── vision_analyzer.py # 视觉模型 API 包装器
│   ├── auth.py                # API Key 认证
│   ├── config.py              # Pydantic 设置
│   ├── db.py                  # SQLite 模式和连接
│   ├── main.py                # FastAPI 应用和生命周期
│   ├── models.py              # Pydantic 请求/响应模型
│   └── repositories.py        # 数据库访问层
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── components/        # React 组件
│   │   │   └── AppLayout.tsx  # 带导航的 Shell 布局
│   │   ├── lib/               # 工具和 API 客户端
│   │   │   ├── api.ts         # API 客户端和类型
│   │   │   ├── presentation.ts # 显示格式化
│   │   │   └── tasks.ts       # 任务状态工具
│   │   ├── pages/             # 页面组件
│   │   │   ├── ImportPage.tsx # 视频导入 UI
│   │   │   ├── KeywordsPage.tsx # 关键词管理
│   │   │   ├── ResultDetailPage.tsx # 帧详情视图
│   │   │   ├── SearchPage.tsx # 主搜索 UI
│   │   │   └── TasksPage.tsx  # 任务监控（支持重试）
│   │   ├── test/              # 测试设置
│   │   ├── App.tsx            # 根组件
│   │   ├── main.tsx           # 入口点
│   │   ├── router.tsx         # 路由配置
│   │   └── styles.css         # 全局样式
│   ├── index.html             # HTML 模板
│   ├── package.json           # Node 依赖
│   ├── tsconfig.json          # TypeScript 配置
│   └── vite.config.ts         # Vite 配置
├── tests/                     # 后端测试
│   └── backend/               # pytest 测试文件
├── data/                      # 数据存储 (gitignored)
│   ├── db/                    # SQLite 数据库文件
│   └── frames/                # 提取的帧图片
├── docs/                      # 文档
│   ├── 2026-04-01-project-tech-stack-report.md
│   ├── plans/                 # 实现计划
│   └── 视频画面内容检索平台操作手册.md
├── requirements.txt           # Python 依赖
├── .env.example               # 环境模板
└── README.md                  # 快速入门指南
```

## 构建和运行命令

### 后端

```powershell
# 安装依赖
python -m pip install -r requirements.txt

# 启动开发服务器 (自动重载)
uvicorn backend.main:app --reload

# 运行测试
pytest -q
```

### 前端

```powershell
# 安装依赖
cd frontend
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 运行测试
npm run test
```

### 环境配置

复制 `.env.example` 并进行配置：

```powershell
$env:VISION_PROVIDER="zhipu"
$env:VISION_API_KEY="your-key"
$env:VISION_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
$env:VISION_ANALYZER_MODE="live"      # live | mock | kimi_cli
$env:KIMI_CLI_COMMAND="kimi"
$env:FRAME_INTERVAL="3"               # 帧间隔秒数
$env:API_CONCURRENCY="3"              # 并发 API 调用数
$env:API_KEY="your-secure-random-key-here"
$env:CORS_ORIGINS="http://localhost:5173,http://localhost:3000"
$env:ALLOWED_VIDEO_DIRS=".;.\作弊视频;/app/videos"
$env:DB_PATH="data/db/search.db"
$env:FRAMES_DIR="data/frames"
$env:VITE_API_BASE_URL="http://127.0.0.1:8000/api"
```

**视觉分析器模式：**
- `live`: 调用远程 API (需要 API key)
- `mock`: 返回模拟分析 (用于无 API 的 UI 测试)
- `kimi_cli`: 使用本地 Kimi CLI 配合 coding/v1 API

## 代码风格指南

### Python (后端)
- 使用 `from __future__ import annotations` 进行前向引用
- 所有函数签名需要类型提示
- 使用 Pydantic 模型进行请求/响应验证
- 数据库访问使用 Repository 模式
- I/O 操作使用 Async/await
- 变量/函数使用 snake_case，类使用 PascalCase

### TypeScript (前端)
- 启用严格 TypeScript 模式
- 使用 hooks 的函数式组件
- 优先使用命名导出
- 变量/函数使用 camelCase，组件使用 PascalCase
- 类型定义在 `lib/api.ts`

## API 端点

| 方法 | 路径 | 描述 |
|--------|------|-------------|
| GET | `/api/health` | 健康检查与模式信息 |
| GET | `/api/videos` | 列出所有视频 |
| POST | `/api/videos/import` | 导入单个视频 |
| POST | `/api/videos/import-folder` | 批量导入文件夹 |
| GET | `/api/videos/{id}` | 获取视频及帧信息 |
| GET | `/api/videos/{id}/file` | 流式传输视频文件 |
| POST | `/api/videos/{id}/process` | 按指定模式重新处理视频 |
| GET | `/api/videos/{id}/segments` | 获取视频可疑时间段 |
| POST | `/api/videos/{id}/rescan` | 对指定 stage 重新扫描 |
| GET | `/api/tasks` | 列出处理任务 |
| GET | `/api/tasks/{id}/progress` | 获取任务详情/进度 |
| POST | `/api/tasks/{id}/retry` | 重试失败任务 |
| POST | `/api/search` | 搜索已索引的帧 |
| GET | `/api/search/results/{frame_id}` | 获取结果详情 |
| GET | `/api/keywords` | 列出关键词集合 |
| POST | `/api/keywords` | 创建关键词集合 |
| PUT | `/api/keywords/{id}` | 更新关键词集合 |
| DELETE | `/api/keywords/{id}` | 删除关键词集合 |
| POST | `/api/keywords/{id}/scan` | 使用关键词集合扫描 |
| GET | `/api/frames/video/{video_id}` | 获取视频的帧列表 |
| GET | `/api/frames/{frame_id}/image` | 获取帧图片 |
| GET | `/api/frames/{frame_id}/analysis` | 获取帧分析结果 |
| GET | `/api/stats` | 平台统计 |

## 数据库模式

### 表
- `video_assets` - 视频元数据 (文件名、路径、时长、格式、分辨率、状态)
- `processing_tasks` - 后台任务跟踪 (video_id、类型、状态、进度、错误、details)
- `video_frames` - 提取的帧元数据 (video_id、索引、时间戳、图片路径)
- `frame_analysis` - AI 分析结果 (结构化字段)
- `keyword_sets` - 用户定义的关键词组
- `search_query_logs` - 搜索审计日志
- `frame_analysis_fts` - 用于全文搜索的虚拟 FTS5 表
- `suspicious_segments` - 可疑时间段聚合
- `task_queue` - 持久化任务队列作业
- `frame_ocr_cache` - 本地 OCR 结果缓存

### frame_analysis 中的关键字段
- `screen_text` - 帧中的 OCR 文本
- `application` - 检测到的应用/网站名称
- `url` - 浏览器 URL（如果可见）
- `operation` - 用户操作描述
- `ai_tool_detected` - 布尔标志
- `ai_tool_name` - 检测到的 AI 工具名称
- `code_visible` - 布尔标志
- `code_content_summary` - 代码片段摘要
- `risk_indicators` - 风险标签的 JSON 数组
- `summary` - 一句话摘要

## 测试说明

### 后端测试
```powershell
# 运行所有测试
pytest -q

# 运行特定测试文件
pytest tests/backend/test_searcher.py -v

# 带覆盖率运行
pytest --cov=backend -q
```

### 前端测试
```powershell
cd frontend
npm run test
```

### 测试数据
- 示例视频位于 `作弊视频/` 目录（AI 使用场景的屏幕录制）
- 无 API key 测试时可使用 Mock 模式

## 安全注意事项

1. **API Keys**: 视觉模型 API key 和 `API_KEY` 均存储在环境变量中，永不提交到版本控制
2. **CORS**: 通过 `CORS_ORIGINS` 环境变量配置允许来源，不再默认允许所有来源
3. **文件访问**: 后端通过 `ALLOWED_VIDEO_DIRS` 白名单限制可访问的视频路径
4. **SQL 注入**: 通过 SQLite 使用参数化查询
5. **XSS**: React 内置转义；如 API 响应作为 HTML 显示需确保已清理

## 开发注意事项

### 帧处理流水线
1. 视频导入创建 `video_assets` 记录
2. 任务进入 `SQLiteTaskQueue` 持久化队列，支持重启后恢复
3. FFmpeg 按 `FRAME_INTERVAL` 秒数提取帧（V2 支持片段级精确提取）
4. 分析阶段支持 `quick`（仅粗筛）、`two_stage`（粗筛+精扫）、`deep`（全量精扫）三种模式
5. 结果存储在 `frame_analysis` 并索引到 FTS5
6. 全程更新任务进度，失败任务可通过 `/tasks/{id}/retry` 重试

### 重要实现细节
- 任务队列已改为 **SQLite 持久化** (`SQLiteTaskQueue`)，重启后 pending 任务会自动恢复
- 帧图片存储在 `FRAMES_DIR/video_{id:04d}/`
- FTS5 使用 `frame_analysis_fts` 虚拟表进行搜索，并通过 trigger 自动同步
- `frame_extractor.py` 使用 `validate_path()` 正则过滤防止 shell 特殊字符注入
- VisionAnalyzer 支持三种模式以适应不同开发场景

### 前端路由
- `/` - 搜索页（默认）
- `/import` - 视频导入
- `/tasks` - 任务监控（支持重试）
- `/results/{frameId}` - 帧详情视图
- `/keywords` - 关键词管理

## 文档

- `2026-03-30-video-visual-search-prd-v2.md` - 完整 PRD (中文)
- `docs/视频画面内容检索平台操作手册.md` - 用户手册
- `codex-prompt-video-visual-search.md` - 开发提示词
