# 项目技术栈全景报告

范围：只读审查，未修改业务代码。项目根目录：`E:\understand_mov`

## 1. 整体架构

| 项目项 | 结论 |
|---|---|
| 架构形态 | 前后端分离，同仓库管理（`backend/` + `frontend/`） |
| 后端入口 | [backend/main.py](/E:/understand_mov/backend/main.py#L184) |
| 前端入口 | [frontend/src/main.tsx](/E:/understand_mov/frontend/src/main.tsx#L1) |
| 前端应用入口 | [frontend/src/App.tsx](/E:/understand_mov/frontend/src/App.tsx#L1) |
| 前端路由入口 | [frontend/src/router.tsx](/E:/understand_mov/frontend/src/router.tsx#L1) |

| 启动项 | 命令 | 来源 |
|---|---|---|
| 后端安装 | `python -m pip install -r requirements.txt` | [README.md](/E:/understand_mov/README.md#L33) |
| 后端启动 | `uvicorn backend.main:app --reload` | [README.md](/E:/understand_mov/README.md#L39) |
| 后端测试 | `pytest -q` | [README.md](/E:/understand_mov/README.md#L45) |
| 前端安装 | `cd frontend && npm install` | [README.md](/E:/understand_mov/README.md#L53) |
| 前端启动 | `cd frontend && npm run dev` | [README.md](/E:/understand_mov/README.md#L60) |
| 前端构建 | `cd frontend && npm run build` | [README.md](/E:/understand_mov/README.md#L66) |

## 2. 后端技术栈

| 维度 | 结论 | 关键文件 |
|---|---|---|
| Web 框架 | FastAPI | [backend/main.py](/E:/understand_mov/backend/main.py#L8) |
| 数据模型/配置 | Pydantic `BaseModel` + 自定义 `Settings` | [backend/models.py](/E:/understand_mov/backend/models.py#L6), [backend/config.py](/E:/understand_mov/backend/config.py#L10) |
| 视频处理 | `ffprobe` 做探测，`ffmpeg` 做抽帧，均通过 `subprocess` 调用；未使用 OpenCV/moviepy | [backend/services/video_import.py](/E:/understand_mov/backend/services/video_import.py#L34), [backend/services/frame_extractor.py](/E:/understand_mov/backend/services/frame_extractor.py#L22) |
| 抽帧策略 | 固定时间间隔抽帧，默认每 `3` 秒一帧，范围 `1-10` 秒，可由 `FRAME_INTERVAL` 配置 | [backend/config.py](/E:/understand_mov/backend/config.py#L17), [backend/config.py](/E:/understand_mov/backend/config.py#L44), [backend/services/frame_extractor.py](/E:/understand_mov/backend/services/frame_extractor.py#L7) |
| 是否读取原视频帧率 | 不读取原视频 fps；`ffprobe` 只读时长/格式/分辨率，抽帧直接用 `ffmpeg -vf fps=1/{interval}` | [backend/services/video_import.py](/E:/understand_mov/backend/services/video_import.py#L40), [backend/services/frame_extractor.py](/E:/understand_mov/backend/services/frame_extractor.py#L15) |
| OCR / 视觉分析 | Moonshot/Kimi，走 OpenAI 兼容 SDK；默认模型 `kimi-k2.5` | [backend/services/vision_analyzer.py](/E:/understand_mov/backend/services/vision_analyzer.py#L12), [backend/config.py](/E:/understand_mov/backend/config.py#L13), [backend/config.py](/E:/understand_mov/backend/config.py#L14) |
| 其他视觉模式 | `mock` 本地模拟；`kimi_cli` 走 `kimi` CLI | [backend/services/vision_analyzer.py](/E:/understand_mov/backend/services/vision_analyzer.py#L39), [backend/services/vision_analyzer.py](/E:/understand_mov/backend/services/vision_analyzer.py#L43), [backend/services/vision_analyzer.py](/E:/understand_mov/backend/services/vision_analyzer.py#L93) |
| 搜索实现 | SQLite FTS5 全文检索为主，文件名/路径 `LIKE` 为补充；无向量检索 | [backend/db.py](/E:/understand_mov/backend/db.py#L84), [backend/services/searcher.py](/E:/understand_mov/backend/services/searcher.py#L16), [backend/services/searcher.py](/E:/understand_mov/backend/services/searcher.py#L24), [backend/services/searcher.py](/E:/understand_mov/backend/services/searcher.py#L54) |
| 索引内容 | `screen_text`、`application`、`url`、`operation`、`ai_tool_name`、`code_content_summary`、`risk_indicators`、`summary` 拼平后写入 FTS | [backend/services/indexer.py](/E:/understand_mov/backend/services/indexer.py#L4) |
| 数据存储 | SQLite 存元数据/任务/帧/分析/FTS；文件系统存抽出的 JPEG；原视频按本地路径引用 | [backend/db.py](/E:/understand_mov/backend/db.py#L11), [backend/repositories.py](/E:/understand_mov/backend/repositories.py#L21), [backend/repositories.py](/E:/understand_mov/backend/repositories.py#L147), [backend/config.py](/E:/understand_mov/backend/config.py#L20) |
| 后台任务 | 内存队列 `InMemoryTaskQueue`，非持久化 | [backend/services/task_queue.py](/E:/understand_mov/backend/services/task_queue.py#L10), [backend/main.py](/E:/understand_mov/backend/main.py#L147) |
| mock/live 切换 | `VISION_ANALYZER_MODE` 显式指定优先；未指定时：有 `MOONSHOT_API_KEY` 则 `live`，否则 `mock` | [backend/config.py](/E:/understand_mov/backend/config.py#L34), [backend/config.py](/E:/understand_mov/backend/config.py#L37) |

## 3. 前端技术栈

| 维度 | 结论 | 关键文件 |
|---|---|---|
| 框架 | React 19 + TypeScript | [frontend/package.json](/E:/understand_mov/frontend/package.json#L11), [frontend/src/main.tsx](/E:/understand_mov/frontend/src/main.tsx#L1) |
| 路由 | `react-router-dom` | [frontend/package.json](/E:/understand_mov/frontend/package.json#L14), [frontend/src/router.tsx](/E:/understand_mov/frontend/src/router.tsx#L1) |
| 构建工具 | Vite | [frontend/package.json](/E:/understand_mov/frontend/package.json#L7), [frontend/vite.config.ts](/E:/understand_mov/frontend/vite.config.ts#L1) |
| UI 方案 | 无 Ant Design/MUI；Tailwind 工具链已接入，但当前页面主要是自定义 CSS 类 | [frontend/package.json](/E:/understand_mov/frontend/package.json#L21), [frontend/tailwind.config.ts](/E:/understand_mov/frontend/tailwind.config.ts#L1), [frontend/src/styles.css](/E:/understand_mov/frontend/src/styles.css#L1) |
| 状态管理 | 无 Redux/Zustand；主要使用组件内 `useState` / `useEffect` + 简单 API 封装 | [frontend/src/pages/ImportPage.tsx](/E:/understand_mov/frontend/src/pages/ImportPage.tsx#L1), [frontend/src/pages/SearchPage.tsx](/E:/understand_mov/frontend/src/pages/SearchPage.tsx#L1), [frontend/src/pages/TasksPage.tsx](/E:/understand_mov/frontend/src/pages/TasksPage.tsx#L1), [frontend/src/lib/api.ts](/E:/understand_mov/frontend/src/lib/api.ts#L72) |

## 4. 关键文件地图

| 类别 | 文件 |
|---|---|
| 视频导入 API | [backend/api/videos.py](/E:/understand_mov/backend/api/videos.py#L12) |
| 视频探测/导入服务 | [backend/services/video_import.py](/E:/understand_mov/backend/services/video_import.py#L34) |
| 处理调度与主流程 | [backend/main.py](/E:/understand_mov/backend/main.py#L29) |
| 后台任务队列 | [backend/services/task_queue.py](/E:/understand_mov/backend/services/task_queue.py#L10) |
| 抽帧命令构造 | [backend/services/frame_extractor.py](/E:/understand_mov/backend/services/frame_extractor.py#L7) |
| 抽帧执行 | [backend/services/frame_extractor.py](/E:/understand_mov/backend/services/frame_extractor.py#L22) |
| 视觉分析 | [backend/services/vision_analyzer.py](/E:/understand_mov/backend/services/vision_analyzer.py#L18) |
| 搜索入口 | [backend/services/searcher.py](/E:/understand_mov/backend/services/searcher.py#L16) |
| FTS 搜索 SQL | [backend/services/searcher.py](/E:/understand_mov/backend/services/searcher.py#L24) |
| 文件名/路径补充搜索 | [backend/services/searcher.py](/E:/understand_mov/backend/services/searcher.py#L54) |
| 搜索内容拼装 | [backend/services/indexer.py](/E:/understand_mov/backend/services/indexer.py#L4) |
| SQLite schema / FTS5 | [backend/db.py](/E:/understand_mov/backend/db.py#L7) |
| Repository 数据访问层 | [backend/repositories.py](/E:/understand_mov/backend/repositories.py#L12) |
| 路由定义：health | [backend/api/health.py](/E:/understand_mov/backend/api/health.py#L6) |
| 路由定义：videos | [backend/api/videos.py](/E:/understand_mov/backend/api/videos.py#L12) |
| 路由定义：tasks | [backend/api/tasks.py](/E:/understand_mov/backend/api/tasks.py#L8) |
| 路由定义：search | [backend/api/search.py](/E:/understand_mov/backend/api/search.py#L9) |
| 路由定义：frames | [backend/api/frames.py](/E:/understand_mov/backend/api/frames.py#L11) |
| 路由定义：keywords | [backend/api/keywords.py](/E:/understand_mov/backend/api/keywords.py#L9) |
| 后端配置 | [backend/config.py](/E:/understand_mov/backend/config.py#L10) |
| 环境变量样例 | [.env.example](/E:/understand_mov/.env.example#L1) |
| 前端 API 基址配置 | [frontend/src/lib/api.ts](/E:/understand_mov/frontend/src/lib/api.ts#L62) |
| Vite 配置 | [frontend/vite.config.ts](/E:/understand_mov/frontend/vite.config.ts#L1) |

## 5. 依赖清单

### 后端依赖

| 功能组 | 依赖 |
|---|---|
| Web/API | `fastapi`, `uvicorn`, `python-multipart` |
| 配置/数据模型 | `pydantic` |
| 外部模型调用 | `openai` |
| 测试 | `pytest` |

来源：[requirements.txt](/E:/understand_mov/requirements.txt#L1)  
备注：项目中未发现 `pyproject.toml`，当前以后端 `requirements.txt` 为准。

### 前端依赖

| 功能组 | 依赖 |
|---|---|
| 运行时 | `react`, `react-dom`, `react-router-dom` |
| 构建/编译 | `vite`, `@vitejs/plugin-react`, `typescript` |
| 样式工具链 | `tailwindcss`, `postcss`, `autoprefixer` |
| 测试 | `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom` |
| 类型 | `@types/react`, `@types/react-dom` |

来源：[frontend/package.json](/E:/understand_mov/frontend/package.json#L1)

## 简短结论

| 项目项 | 结论 |
|---|---|
| 技术路线 | FastAPI + SQLite FTS5 + FFmpeg + React/Vite |
| 检索能力 | 结构化画面文本检索为主，当前不是向量检索 |
| 视觉分析模式 | `live` / `mock` / `kimi_cli` 三种 |
| 当前实现风格 | 轻量 MVP，依赖少，后端任务队列和数据库都偏本地化/单机化 |
