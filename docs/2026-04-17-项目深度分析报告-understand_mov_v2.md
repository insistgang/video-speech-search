# 项目深度分析报告 - understand_mov_v2

> 结论先行：这是一个**架构思路清晰、功能链条完整、明显带有“MVP 但已认真工程化”特征**的视频画面检索系统。前端层、搜索索引设计、任务恢复思路都不错，但后端当前存在几处会直接影响可运行性与可部署性的关键问题，尤其是 **OCR 依赖加载链、Docker 前端鉴权注入、两阶段扫描默认行为、异步流水线中的阻塞 I/O**。

## 1. 项目概览

### 1.1 项目名称、目标与业务场景

| 项 | 内容 |
|---|---|
| 项目名称 | `understand_mov_v2` / 视频画面内容检索平台 |
| 核心目标 | 将无声屏幕录制视频转成“可结构化理解、可全文检索、可定位回放”的证据库 |
| 一句话业务场景 | 面向考试监控、编程场景审计、作弊排查、AI 工具使用取证的屏幕录制内容检索平台 |
| 详细描述 | 系统导入本地视频后，使用 `ffprobe` 获取元数据、`ffmpeg` 抽帧、本地 OCR 做粗筛、多模态视觉模型做精扫，将结构化结果写入 SQLite/FTS5，再由 React 前端提供搜索、聚合片段查看、结果详情回放、关键词词库扫描与任务监控能力 |

### 1.2 技术栈、框架、语言版本、运行环境

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12+, FastAPI, SQLite + FTS5, SlowAPI |
| AI/视觉 | `openai` 兼容客户端，对接智谱 / Moonshot / Kimi CLI |
| 视频处理 | FFmpeg / ffprobe |
| OCR | `rapidocr-onnxruntime` |
| 前端 | React 19, React Router DOM 7, Vite 7, TypeScript 5, Tailwind CSS 3 |
| 测试 | pytest, Vitest, Testing Library, jsdom |
| 部署 | Docker Compose, Nginx, Python slim / Node alpine |

### 1.3 项目规模

| 维度 | 规模 |
|---|---|
| 整个 workspace 文件数 | 约 `6480` 个文件 |
| 可维护源码/测试/文档子集 | 约 `152` 个文件 |
| 后端源码 | `63` 个文件，约 `4016` 行 Python |
| 前端 `src` | `24` 个文件，约 `2232` 行 TS/TSX/CSS |
| 后端测试 | `28` 个文件，约 `2800` 行 Python |
| 前端测试 | `7` 个测试文件，实测 `29` 个测试通过 |
| 主要模块数 | 后端 API `9`、后端服务 `12`、前端页面 `5`、前端共享库 `4` |
| 当前工作区状态 | `git status --short` 显示 `32` 项变更（`24` modified + `8` untracked），说明本报告基于当前工作区状态，而非某个干净提交快照 |

---

## 2. 整体架构设计

### 2.1 架构模式判断

该项目并非 MVC，也不是微服务，更接近于：

**前后端分离的模块化单体（Modular Monolith） + 分层架构（Layered Architecture） + 持久化本地任务队列**

它具备以下典型特征：

- FastAPI 作为单一后端进程，承载 API、任务调度、SQLite 持久化与外部工具调用。
- React SPA 独立负责展示层，通过 REST API 与后端交互。
- 后端内部使用 `api -> service -> repository -> db` 的分层结构。
- 视频处理、OCR、视觉模型、搜索索引、任务管理均以“内部模块”形式存在，而不是独立服务。

### 2.2 分层结构与职责

| 层 | 代表文件 | 职责 |
|---|---|---|
| 表现层 | `frontend/src/pages/*` | 检索、导入、任务监控、详情播放、词库管理 |
| API 层 | `backend/api/*.py` | 路由、参数接收、权限校验、组装响应 |
| 应用服务层 | `backend/services/pipeline.py`, `task_queue.py`, `searcher.py` | 编排视频处理流程、任务恢复、搜索聚合 |
| 领域/模型层 | `backend/models.py` | 请求/响应模型、帧分析记录、路径安全解析 |
| 数据访问层 | `backend/repositories.py` | SQLite CRUD、任务状态、分析数据、FTS 写入 |
| 基础设施适配层 | `frame_extractor.py`, `video_clipper.py`, `vision_analyzer.py`, `local_ocr.py` | 适配 FFmpeg、视觉模型、OCR、本地 CLI |
| 持久化层 | `backend/db.py` + `data/` | SQLite schema、FTS5、帧文件、数据库文件 |

### 2.3 高层调用关系

```text
React 页面
  -> frontend/src/lib/api.ts
  -> FastAPI Router
  -> ProcessingService / SearchService / VideoImportService
  -> Repository
  -> SQLite / FTS5 / data/frames

后台处理链
  -> SQLiteTaskQueue
  -> ProcessingPipeline
  -> FFmpeg / OCR / VisionAnalyzer
  -> Repository.save_frame_analysis + upsert_fts
```

### 2.4 核心设计决策与评价

| 设计决策 | 体现位置 | 优点 | 代价 |
|---|---|---|---|
| 用 SQLite 同时存业务数据、FTS、任务队列 | `backend/db.py`, `task_queue.py` | 运维成本极低，MVP 上手快 | 扩展性、迁移能力、并发能力有限 |
| FTS 内容由应用层构建，不依赖 DB trigger | `backend/db.py:143-146`, `backend/services/indexer.py` | 可结合 `jieba` 做中文分词 | 需要应用侧手工维护一致性 |
| 粗扫/精扫/全量深扫三种模式 | `backend/services/pipeline.py` | 可平衡成本、速度与覆盖率 | 模式行为复杂，易出现“用户以为扫了其实没扫到”的认知偏差 |
| 视频模式精扫仅保留代表帧 | `pipeline.py` 视频模式逻辑 | 兼容既有 UI 与 FTS 模型 | 会牺牲时间线完整性与细粒度证据 |
| 单 API Key 保护系统 | `backend/auth.py` | 简单直接 | 不支持多用户、审计、权限分级 |
| 前端轮询任务状态 | `ImportPage.tsx`, `TasksPage.tsx` | 简单可靠 | 不够实时，长任务下浪费请求 |

---

## 3. 目录结构详解

| 路径 | 重要性 | 说明 |
|---|---|---|
| `backend/main.py` | 极高 | 应用入口、上下文装配、CORS、路由注册、任务队列启动 |
| `backend/services/pipeline.py` | 极高 | 全项目核心业务编排器，负责粗扫/精扫/深扫 |
| `backend/repositories.py` | 极高 | SQLite 数据访问中心，承担任务、视频、帧、分析、FTS、词库读写 |
| `backend/db.py` | 极高 | 数据库 schema 定义；也是系统持久化边界的“事实来源” |
| `backend/services/vision_analyzer.py` | 极高 | 兼容多模型供应商与 `kimi_cli` 的视觉分析适配器 |
| `backend/services/task_queue.py` | 极高 | SQLite 持久化任务队列，支持恢复 pending/running 状态 |
| `backend/services/searcher.py` | 高 | FTS 检索、视频元数据回退、结果片段聚合 |
| `backend/models.py` | 高 | 请求模型、路径输入清洗/规范化/允许目录校验 |
| `backend/api/videos.py` | 高 | 导入、列表、重扫、分段获取、处理触发等视频主入口 |
| `backend/services/frame_extractor.py` | 高 | FFmpeg 抽帧命令生成与执行 |
| `backend/services/local_ocr.py` | 高 | 本地 OCR 入口，但当前也是后端运行脆弱点之一 |
| `frontend/src/lib/api.ts` | 极高 | 前端与后端契约的中心文件；请求、类型、媒体 URL 全在这里 |
| `frontend/src/pages/SearchPage.tsx` | 高 | 主搜索 UI，直接体现检索产品体验 |
| `frontend/src/pages/ImportPage.tsx` | 高 | 导入/排队/实时进度的主交互入口 |
| `frontend/src/pages/TasksPage.tsx` | 中高 | 队列监控与失败重试 |
| `frontend/src/pages/ResultDetailPage.tsx` | 中高 | 结果详情与视频时间点回放 |
| `frontend/src/pages/KeywordsPage.tsx` | 中高 | 关键词词库与批量扫描 |
| `tests/backend/*` | 高 | 后端测试覆盖面相当广，说明作者有测试意识 |
| `.github/workflows/ci.yml` | 高 | CI 流程包含后端测试、前端类型检查、前端测试、Docker 构建 |
| `docs/` | 中 | 有 PRD、操作手册、审计报告与阶段性总结，文档意识较好 |

---

## 4. 依赖与技术栈深度分析

### 4.1 后端关键依赖

| 依赖 | 版本策略 | 作用 | 风险点评 |
|---|---|---|---|
| `fastapi` | `>=0.116,<1.0` | API 框架 | 稳定 |
| `uvicorn` | `>=0.35,<1.0` | ASGI 服务 | 稳定 |
| `slowapi` | `>=0.1.9` | 限流 | 默认内存存储，不适合多实例 |
| `openai` | `>=1.108,<2.0` | 兼容 OpenAI 协议调用多模态模型 | 供应商兼容层漂移风险存在 |
| `pydantic` | `>=2.11,<3.0` | 校验与配置模型 | 稳定 |
| `httpx` | `>=0.27,<1.0` | 测试/HTTP 辅助 | 稳定 |
| `jieba` | `>=0.42,<1.0` | 中文分词 | 适配中文检索是合理选择 |
| `imagehash` + `Pillow` | `>=4.3`, `>=10.0` | 帧去重 | 稳定 |
| `rapidocr-onnxruntime` | `>=1.3` | 本地 OCR | **当前真实风险最高**，与 `onnxruntime`/`numpy` ABI 强耦合 |

### 4.2 前端关键依赖

| 依赖 | 版本 | 作用 | 风险点评 |
|---|---|---|---|
| `react` / `react-dom` | `19.1.1` | UI 渲染 | 较新，但本项目使用方式保守 |
| `react-router-dom` | `7.9.1` | 路由 | 稳定 |
| `vite` | `7.1.5` | 构建与开发服务器 | 稳定 |
| `typescript` | `5.9.2` | 类型系统 | 稳定 |
| `vitest` | `3.2.4` | 前端测试 | 稳定 |
| `@testing-library/*` | 近期版本 | UI 测试 | 稳定 |
| `tailwindcss` | `3.4.17` | 样式工具 | 实际项目更多在写手工 CSS，而非重度 utility class |

### 4.3 基础设施与部署依赖

| 依赖 | 用途 | 评价 |
|---|---|---|
| FFmpeg / ffprobe | 视频探测、抽帧、片段裁剪 | 必需；是系统核心基础设施依赖 |
| SQLite + FTS5 | 业务存储 + 全文检索 | 非常适合 MVP/单机部署 |
| Docker Compose | 一键部署前后端 | 配置清晰，但当前前端鉴权注入有缺口 |
| Nginx | 托管 SPA + 反向代理 API | 合理 |

### 4.4 兼容性与安全风险总结

- `requirements.txt` **没有**显式钉住 `numpy<2`，但 `requirements-dev.txt` 有；这会导致“测试环境能好、运行环境炸掉”的分裂。
- `backend/Dockerfile` 只安装 `requirements.txt`，不会得到 `numpy<2` 的保护，和当前观察到的 OCR ABI 问题高度相关。
- `slowapi` 使用默认内存限流，对多进程、多实例和容器水平扩展并不可靠。
- 单机 SQLite 对当前场景合理，但如果未来有大量视频并发处理或多用户同时检索，会成为明显瓶颈。

---

## 5. 核心模块与文件深度解析

### 5.1 后端核心文件

| 文件 | 职责 | 核心逻辑 | 交互关系 |
|---|---|---|---|
| `backend/main.py` | 应用装配中心 | 创建 `AppContext`，注册任务处理器，配置 CORS 和路由，启动/停止队列 | 连接全部核心模块 |
| `backend/config.py` | 配置与环境解析 | 读取 `.env`，解析路径、模式、并发、视频白名单 | 被几乎所有后端模块依赖 |
| `backend/models.py` | 请求模型与路径安全层 | `sanitize_path_input`、路径 normalize、允许目录校验、Pydantic request model | 导入 API 与视频导入服务高度依赖 |
| `backend/db.py` | Schema 与连接工厂 | 初始化 10 张表/虚拟表；定义索引与 FTS 策略 | Repository 的底层基础 |
| `backend/repositories.py` | 数据访问总线 | 视频、任务、帧、分析、词库、FTS、可疑片段全部在此读写 | 被 API、pipeline、searcher 全量依赖 |
| `backend/services/pipeline.py` | 业务主引擎 | `quick` / `two_stage` / `deep`，粗扫 OCR、精扫视觉分析、视频片段分析、进度上报 | 与 FFmpeg、OCR、VisionAnalyzer、Repository 深度耦合 |
| `backend/services/vision_analyzer.py` | 视觉模型适配层 | `mock/live/kimi_cli` 三模态，带限流重试、JSON 修复、视频片段分析 | 被 pipeline 调用，是“模型网关” |
| `backend/services/task_queue.py` | 本地持久化任务系统 | SQLite 保存 job 状态，重启恢复 pending/running，worker 异步执行 | 被 `ProcessingService` 驱动 |
| `backend/services/searcher.py` | 搜索聚合层 | FTS 查询 + 视频元数据回退 + 结果去重 + 可疑片段聚合 | 由搜索 API 直接调用 |
| `backend/services/json_utils.py` | 模型输出容错层 | 清洗 think block、提取 JSON、修复尾逗号/未加引号 key | 提升模型兼容性，非常实用 |
| `backend/api/videos.py` | 视频主路由 | 导入、列表、处理、重扫、分段获取、视频文件流 | 直接连接用户主流程 |
| `backend/services/frame_extractor.py` | 抽帧适配器 | 构造 FFmpeg 命令，执行抽帧，并计算时间戳 | 被粗扫、精扫、深扫复用 |

### 5.2 前端核心文件

| 文件 | 职责 | 核心逻辑 | 交互关系 |
|---|---|---|---|
| `frontend/src/lib/api.ts` | API 契约层 | 统一请求、错误翻译、类型定义、媒体 URL 生成、重试 | 所有页面共享 |
| `frontend/src/pages/SearchPage.tsx` | 主搜索页 | 视频筛选、AI 筛选、时间筛选、结果卡片、聚合片段展示 | 使用 `/search`、`/videos`、`/health` |
| `frontend/src/pages/ImportPage.tsx` | 导入页 | 单视频/文件夹导入、处理模式选择、任务追踪与轮询 | 使用 `/videos/import*`、`/tasks` |
| `frontend/src/pages/TasksPage.tsx` | 任务页 | 轮询任务列表、展示 token/阶段、支持重试 | 使用 `/tasks`、`/tasks/{id}/retry` |
| `frontend/src/pages/ResultDetailPage.tsx` | 详情页 | 同步视频播放时间、展示结构化分析、帧时间线 | 使用 `/search/results/{frame_id}` 与媒体 URL |
| `frontend/src/pages/KeywordsPage.tsx` | 词库页 | 创建词库、扫描词库、删除词库 | 使用 `/keywords*` 系列接口 |

---

## 6. 数据流与调用关系

### 6.1 视频导入与处理主流程

```text
ImportPage
  -> POST /api/videos/import
  -> backend/api/videos.py#import_video
  -> resolve_path_input()
  -> VideoImportService.import_one()
  -> ffprobe 探测视频元信息
  -> Repository.create_video_asset() 写入 video_assets
  -> ProcessingService.schedule_video_processing()
  -> Repository.create_task() 写 processing_tasks
  -> SQLiteTaskQueue.enqueue() 写 task_queue + 内存队列
  -> worker 启动 ProcessingPipeline.process_video()
```

### 6.2 `two_stage` 模式的数据流

```text
stage_coarse
  -> FFmpeg 抽 coarse_interval 帧
  -> 写入 video_frames
  -> pHash 去重
  -> 本地 OCR
  -> 写 frame_ocr_cache
  -> 写 frame_analysis（粗扫占位/初始分析）
  -> build_search_content() + upsert_fts()
  -> 关键词命中时写 suspicious_segments

stage_fine
  -> 读取 suspicious_segments
  -> FINE_SCAN_MODE=frame:
       再抽细帧 -> 视觉模型逐帧分析 -> 覆盖 frame_analysis -> upsert_fts
  -> FINE_SCAN_MODE=video:
       裁剪视频片段 -> 视频级视觉分析 -> 生成代表帧 -> 写 frame_analysis -> upsert_fts
```

### 6.3 搜索流程

```text
SearchPage
  -> POST /api/search
  -> SearchService.search()
      -> frame_analysis_fts MATCH
      -> 若 FTS 无结果，再按 video filename/filepath LIKE 回退
      -> 合并去重
      -> build_segments() 聚合时间段
  -> 返回 results + segments
  -> 前端跳转到 /results/{frameId}
```

### 6.4 详情播放流程

```text
ResultDetailPage
  -> GET /api/search/results/{frame_id}
  -> 返回 video + current frame + analysis + all frames of this video
  -> 前端设置 <video>.currentTime = frame.timestamp
  -> 用户可在时间线上切换帧
```

### 6.5 任务状态流

```text
ProcessingService.report_progress()
  -> 更新 processing_tasks.details/progress
  -> 同步更新 task_queue.progress/stage
  -> ImportPage / TasksPage 轮询 /api/tasks
  -> 前端显示阶段、进度、错误、token 用量
```

---

## 7. 代码质量与最佳实践评估

### 7.1 综合评价

| 维度 | 评价 | 说明 |
|---|---|---|
| 架构清晰度 | 良好 | 模块分层清楚，业务主链条容易追踪 |
| 命名规范 | 良好 | Python/TS 命名整体规范，语义明确 |
| 可读性 | 中上 | 代码大多直白，但 `pipeline.py` 过大、`dict[str, Any]` 使用偏多 |
| 可维护性 | 中等 | Repository/Service 思路正确，但迁移、双状态同步和大文件问题明显 |
| 错误处理 | 中上 | 前端错误翻译做得好，后端对外部命令异常也有包装 |
| 安全基线 | 中等 | 有 API Key、路径白名单、非 root 容器，但仍有公开列表接口与 query-string key 问题 |
| 性能意识 | 中等偏弱 | 有 dedup、限流、片段分析，但异步流水线里仍有明显阻塞 I/O |
| 测试意识 | 良好 | 后端测试文件很多，前端测试跑通；但后端当前可执行性被依赖链破坏 |
| 运维成熟度 | 中等 | 有 Docker、Nginx、CI、healthcheck，但部署鉴权注入与 schema 演进不足 |
| 生产就绪度 | 中等偏弱 | 更像“认真做过工程化的 MVP”，而不是稳健生产版 |

### 7.2 实测验证结果

| 验证项 | 结果 | 结论 |
|---|---|---|
| `npm run build` | 通过 | 前端生产构建健康 |
| `npm run test -- --run` | 通过，`7` 个文件 `29` 个测试 | 前端核心 UI/工具层较稳定 |
| `pytest tests/backend -q` | 收集阶段失败，`18` 个错误 | 后端当前运行链被 OCR/NumPy/包初始化耦合破坏 |
| `pytest -q` | 额外被临时目录/权限目录干扰 | 仓库测试收集边界配置不足 |

### 7.3 明显做得好的地方

- `backend/models.py` 的路径解析很用心，考虑了引号、Unicode 归一化、路径白名单与灵活匹配。
- `backend/services/json_utils.py` 对模型输出 JSON 做了多层修复，实际工程价值很高。
- `backend/db.py` 明确说明为什么 FTS 不用 trigger，而由应用层维护，设计理由自洽。
- `backend/services/task_queue.py` 做到了 SQLite 持久化与重启恢复，适合单机 MVP。
- 前端错误信息做了中文化翻译，用户体验明显优于原始异常直出。
- Docker 镜像与 Nginx 都采取了非 root 运行，基础安全意识不错。
- CI 已覆盖后端测试、前端类型检查、前端测试和 Docker 构建，说明有持续集成意识。

### 7.4 明显不足的地方

- 后端大量模块通过 `dict[str, Any]` 传递状态，领域边界不够硬。
- `pipeline.py` 过于庞大，已经成为“业务上帝文件”。
- 异步函数里直接执行同步 OCR/FFmpeg/文件系统操作，理论并发与实际并发不一致。
- 任务状态在 `processing_tasks` 和 `task_queue` 两套表中重复维护，后续复杂度会持续上升。
- 缺少数据库迁移机制；schema 演进目前依赖“初始化 SQL 碰运气”。
- 部分 API 与前端能力不完全对齐，例如后端支持更新关键词集，前端没有编辑入口。

---

## 8. 潜在问题与风险清单

1. **严重 | OCR 依赖与包初始化耦合会直接拖垮后端启动与测试收集**  
   证据：`backend/services/__init__.py:5-6`、`backend/services/local_ocr.py:3-5`、`requirements.txt:1-12`、`requirements-dev.txt:1-3`、`backend/Dockerfile:17-20`。  
   影响：当前环境中 `pytest tests/backend -q` 已因 `onnxruntime` 与 `NumPy 2.4.4` ABI 不兼容而在收集阶段失败；更严重的是，任何导入 `backend.services.*` 的代码都会被 `local_ocr` 的模块级初始化牵连。

2. **严重 | Docker 化前端大概率拿不到 `VITE_API_KEY`，静态部署后会访问失败**  
   证据：`frontend/src/lib/api.ts:137-185`、`frontend/vite.config.ts:4-20`、`docker-compose.yml:35-40`、`frontend/Dockerfile:6-19`。  
   影响：Compose 只向前端 build 传了 `VITE_API_BASE_URL`，没有传 `VITE_API_KEY`；且前端 build context 是 `./frontend`，`envDir: ".."` 在容器构建时也看不到项目根 `.env`。结果是构建产物里 `API_KEY` 很可能为空，受保护 API 与媒体 URL 会失效。

3. **高 | 默认 `two_stage` 模式对“没有关键词集”的情况几乎失去精扫能力**  
   证据：`backend/services/pipeline.py:131-136`、`190-203`、`254-268`。  
   影响：粗扫阶段只有命中 `keyword_sets` 才会生成 `suspicious_segments`；如果词库为空，`stage_fine()` 会直接返回 `segments_processed = 0`。这会让“标准扫描”在默认新装环境里只做 OCR 和索引，不做视觉精扫。

4. **高 | 异步流水线中存在明显阻塞 I/O，会压制并发并拖慢整个服务事件循环**  
   证据：`backend/services/pipeline.py:98-105`、`156-157`、`507-516`、`629-638`、`704-711`，以及 `backend/services/frame_extractor.py:80-81`、`backend/services/local_ocr.py:18-21`。  
   影响：FFmpeg 抽帧、RapidOCR 推理都在 async 流程里同步执行；当前 `task_queue` worker 是 asyncio task，不是隔离进程池，理论上会阻塞其他后台任务，甚至影响 API 响应及时性。

5. **高 | 鉴权策略不一致，且媒体访问支持 query-string API Key，存在泄露风险**  
   证据：`backend/main.py:299-305`、`backend/api/videos.py:79-84`、`frontend/src/lib/api.ts:140-153`、`backend/auth.py:72-80`。  
   影响：`GET /api/videos` 当前未强制鉴权，会暴露视频资产列表；同时媒体访问把 `api_key` 放进 URL，会出现在浏览器历史、日志、代理层访问记录中。

6. **中高 | 搜索结果的“片段聚合”使用了错误的时间间隔基准**  
   证据：`backend/api/search.py:27-30`，而实际抽帧使用 `coarse_interval` / `fine_interval` / 视频片段模式，见 `pipeline.py:98-105`、`507-516`、`704-711`。  
   影响：聚合片段时统一用 `FRAME_INTERVAL`，会导致粗扫结果被切得过碎，或在不同模式下聚合不准确。

7. **中高 | 数据库 schema 没有迁移机制，后续版本升级风险会越来越大**  
   证据：`backend/db.py:7-147`, `157-160`。  
   影响：当前只有 `CREATE TABLE IF NOT EXISTS`，没有 schema version、migration、backfill 机制。一旦列结构、索引或默认值变化，老库升级不可控。

8. **中 | 任务状态双写到 `processing_tasks` 与 `task_queue`，并靠 JSON 中的 `queue_job_id` 做关联，长期维护成本高**  
   证据：`backend/main.py:87-104`、`113-123`，`backend/db.py:23-34`、`103-116`，`backend/services/task_queue.py:122-137`。  
   影响：当前还能工作，但随着重试、取消、批量任务、任务查询维度增加，状态不一致与定位困难会逐渐成为主问题。

9. **中 | 测试与工作区卫生不足，`pytest -q` 容易被临时目录污染**  
   证据：`.gitignore:1-18` 未覆盖 `.tmp`、`codex_tmp_tests`、`pytest-cache-files-*`、`tmp*` 等目录；仓库中也缺少 `pytest.ini`/`testpaths`。  
   影响：当前 `pytest -q` 在本地会误扫权限受限目录，增加“非代码问题式失败”。

10. **低中 | 前端存在若干用户体验与功能闭环小缺口**  
    证据：`frontend/src/pages/KeywordsPage.tsx:34-38` 仅按英文逗号切分，但占位符是中文逗号 `:95`；`backend/api/search.py:42-49` 详情接口一次返回整段视频的全部帧。  
    影响：前者会让中文输入场景下词库创建异常；后者在长视频上会拉高详情页 payload 与渲染成本。

---

## 9. 改进建议优先级

| 优先级 | 建议 | 原因 | 预期收益 | 难度 |
|---|---|---|---|---|
| P0 | **拆掉 `backend/services/__init__.py` 对 `local_ocr` 的 eager import，并将 OCR 初始化改成懒加载/可降级** | 当前是后端可运行性的最大单点 | 后端能启动、测试能收集、OCR 成为可选能力而不是全局炸点 | 中 |
| P0 | **统一运行时依赖策略：把 `numpy<2` 放入运行时依赖，或升级 OCR/onnxruntime 版本并在 Docker 中验证** | 当前测试与 Docker 依赖不一致 | 消除“本地/CI/容器”分裂 | 中 |
| P0 | **修复 Docker 前端鉴权注入：通过 build arg/runtime config 注入 `VITE_API_KEY`，或改成更安全的 cookie/signed URL 方案** | 当前容器部署可用性存疑 | 让 Compose 部署真正可用 | 中 |
| P1 | **重设计 `two_stage` 的粗筛策略，不要把精扫入口完全绑定到人工关键词集** | 当前默认标准模式覆盖率不足 | 提升真正的 AI/异常操作发现率 | 中高 |
| P1 | **把 FFmpeg、OCR、pHash 等阻塞工作迁移到 `asyncio.to_thread` / 专用 worker / 进程池，并把 `task_queue` worker 并发与 `api_concurrency` 解耦** | 当前异步模型名义并发高、实际阻塞重 | 提升吞吐、稳定性与可预测性 | 中高 |
| P1 | **引入数据库迁移机制（Alembic 或最小自研 schema versioning）** | schema 演化风险已存在 | 提升长期可维护性与升级安全性 | 中 |
| P2 | **收紧鉴权与安全边界：保护 `/api/videos`、减少 query-string API key、补 Nginx 安全头** | 当前仍有信息暴露面 | 提升内网审计系统的安全基线 | 中 |
| P2 | **补仓库工程卫生：新增 `pytest.ini`、扩充 `.gitignore`、固化本地测试命令** | 当前开发体验不稳定 | 降低伪失败，提高团队效率 | 低 |
| P3 | **补产品完成度：关键词编辑 UI、中文逗号兼容、详情页分页/虚拟化、统计页接入** | 功能闭环不完整 | 提升易用性与用户感知质量 | 低中 |

---

## 10. 总结与下一步推荐

### 10.1 当前成熟度评估

**综合成熟度：6/10**

这不是一个“玩具项目”。它已经具备：

- 清晰的模块边界
- 完整的导入-处理-索引-检索-回放闭环
- 前端可用性与测试基础
- 任务恢复、FTS 中文检索、视频模式精扫等实用设计

但它也还没有达到“稳定生产可运维”的程度，主要短板集中在：

- 运行时依赖稳定性
- Docker 部署可用性
- 两阶段扫描的真实检测覆盖率
- 异步流水线中的阻塞操作
- 数据与任务状态模型的长期演进能力

### 10.2 建议的下一步行动优先级

1. 先修 **后端启动/测试链路**：OCR 懒加载 + NumPy/onnxruntime 版本策略统一。
2. 再修 **Docker 部署链路**：前端 `VITE_API_KEY` 注入与媒体鉴权方案。
3. 随后重做 **两阶段扫描入口逻辑**：让“标准扫描”在没有人工词库时仍能产出可疑片段。
4. 接着治理 **并发与阻塞问题**：把 FFmpeg/OCR 从事件循环里移出去。
5. 然后补 **schema migration + 任务状态建模**，为后续迭代打基础。
6. 最后处理 **安全边界和 UX 补漏**：公开视频列表、query-string key、词库编辑、中文输入兼容等。

---  
分析生成于: 2026-04-17 15:55:19 +08:00  
由本地 Codex 深度分析生成
