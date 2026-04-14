# 视频画面内容检索平台

一个用于导入无声录屏视频、提取视频帧、通过多模态视觉模型理解画面内容、建立 SQLite FTS5 全文索引，并在 React 前端中检索和查看匹配的 MVP 项目。

## 已实现功能

- **FastAPI 后端**：提供健康检查、视频管理、任务队列、内容搜索、视频帧查看、关键词集等接口
- **SQLite 数据库**：包含 `video_assets`（视频资产）、`processing_tasks`（处理任务）、`video_frames`（视频帧）、`frame_analysis`（帧分析）、`keyword_sets`（关键词集）及 FTS5 全文索引表
- **本地视频探针**：通过 `ffprobe` 获取视频元信息
- **固定间隔抽帧**：通过 `ffmpeg` 按设定间隔提取 JPEG 帧
- **视觉分析服务**：支持调用智谱/Kimi 等多模态模型，带并发限制与自动重试
- **内存任务队列**：后台异步处理视频分析任务
- **React + Vite 前端**：包含搜索页、导入页、任务页、结果详情页、关键词管理页

## 环境配置

复制 `.env.example` 为 `.env`，或在启动前通过环境变量导出：

```powershell
$env:VISION_PROVIDER="zhipu"
$env:VISION_API_KEY="your-key"
$env:VISION_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
$env:MODEL_NAME="glm-4.6v-flashx"
$env:VISION_ANALYZER_MODE="live"
$env:KIMI_CLI_COMMAND="kimi"
$env:FFMPEG_COMMAND="ffmpeg"
$env:FFPROBE_COMMAND="ffprobe"
$env:FRAME_INTERVAL="5"
$env:FRAME_MAX_WIDTH="1280"
$env:FRAME_JPEG_QUALITY="5"
$env:API_CONCURRENCY="1"
$env:API_MAX_RETRIES="6"
$env:API_MIN_INTERVAL_SECONDS="1.5"
$env:FINE_SCAN_MODE="video"
$env:DATA_DIR="data"
$env:DB_PATH="data/db/search.db"
$env:FRAMES_DIR="data/frames"
$env:API_KEY="your-secure-random-key-here"
$env:VITE_API_KEY="your-secure-random-key-here"
$env:ALLOW_ANY_VIDEO_PATHS="false"
$env:ALLOWED_VIDEO_DIRS=".;.\作弊视频;/app/videos"
$env:VITE_API_BASE_URL="http://127.0.0.1:8000/api"
```

## 后端启动

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动 API 服务：

```powershell
uvicorn backend.main:app --reload
```

运行测试：

```powershell
pytest -q
```

## 前端启动

安装依赖：

```powershell
cd frontend
npm install
```

启动开发服务器：

```powershell
npm run dev
```

构建与测试：

```powershell
npm run build
npm run test
```

## Docker 部署

通过 Docker Compose 一键构建并启动前后端：

```powershell
docker compose up --build -d
```

启动后访问：

- 前端：`http://<服务器IP>/`
- 后端 API：`http://<服务器IP>:8000/api/health`

### 部署注意事项

- `docker-compose.yml` 将主机的 `./data` 目录挂载到后端容器，数据库与抽帧结果会持久化到本地磁盘。
- `VIDEO_IMPORT_PATH` 控制将主机的哪个目录挂载为容器内的 `/app/videos`。
- 在 Web UI 中导入视频时，请填写容器内的路径，例如：

  ```text
  /app/videos/使用AI平台.mp4
  ```

- 若服务器已占用 `80` 端口，请修改 `docker-compose.yml` 中的前端端口映射。
- 部署前请在 `.env` 中设置真实的 `VISION_API_KEY`。

## 补充说明

- 后端会优先加载项目根目录的 `.env` 文件。`API_KEY`、`ALLOWED_VIDEO_DIRS` 等配置在重新导入 `backend.main` 时生效。
- 本地单用户部署可设置 `ALLOW_ANY_VIDEO_PATHS=true`，允许传入主机上的任意绝对路径。
- `FINE_SCAN_MODE=video` 启用分段级视频理解。后端仍为每个可疑片段保存一张预览帧，以确保现有搜索结果和详情页正常展示。
- 受保护媒体资源（`/api/frames/*/image`、`/api/videos/*/file`）支持通过 `X-API-Key` 请求头或 `api_key` 查询参数访问，便于 `<img>` 和 `<video>` 标签直接加载。
- `ALLOWED_VIDEO_DIRS` 使用系统路径分隔符：Windows 用 `;`，Linux/macOS 用 `:`。
- 请确保 `API_KEY` 与 `VITE_API_KEY` 设为相同值，以保证浏览器请求与媒体 URL 使用一致的凭证。
- `FINE_SCAN_MODE=frame` 保持原有的逐帧分析模式；`FINE_SCAN_MODE=video` 则将可疑片段直接发送给多模态模型并索引返回的片段分析结果。
- `VISION_ANALYZER_MODE=live` 模式下，视频处理需要配置有效的 `VISION_API_KEY`。
- 若仅用于 UI 调试或本地流程验证，没有真实 API Key 时，可设置 `VISION_ANALYZER_MODE=mock`。
- 项目仍兼容旧版 `MOONSHOT_API_KEY` / `MOONSHOT_BASE_URL` 环境变量。
- 若 `ffmpeg` / `ffprobe` 不在系统 `PATH` 中，请通过 `FFMPEG_COMMAND` 和 `FFPROBE_COMMAND` 指定其绝对路径。
- 使用 Kimi Code CLI 多模态分析（`coding/v1` key）时，配置如下：

  ```powershell
  $env:VISION_API_KEY="your-coding-key"
  $env:VISION_BASE_URL="https://api.kimi.com/coding/v1"
  $env:MODEL_NAME="kimi-for-coding"
  $env:VISION_ANALYZER_MODE="kimi_cli"
  ```

- 当前任务队列为内存级实现，后端重启后不会自动恢复中断的任务。
