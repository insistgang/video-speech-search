# Video Visual Search MVP

MVP for importing silent screen-recording videos, extracting JPEG frames with FFmpeg, sending frames to a multimodal vision model for structured understanding, indexing flattened text into SQLite FTS5, and reviewing matches in a React UI.

## Implemented

- FastAPI backend with routes for health, videos, tasks, search, frames, and keyword sets
- SQLite bootstrap with `video_assets`, `processing_tasks`, `video_frames`, `frame_analysis`, `keyword_sets`, and `frame_analysis_fts`
- Local video probing via `ffprobe`
- Fixed-interval frame extraction via `ffmpeg`
- Kimi image-analysis service with concurrency limits and retry
- In-memory processing queue for background video jobs
- React + Vite frontend shell with search, import, tasks, result detail, and keyword pages

## Environment

Copy `.env.example` to `.env` or export the variables before starting:

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

## Backend

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start API:

```powershell
uvicorn backend.main:app --reload
```

Run tests:

```powershell
pytest -q
```

## Frontend

Install dependencies:

```powershell
cd frontend
npm install
```

Start dev server:

```powershell
npm run dev
```

Build and test:

```powershell
npm run build
npm run test
```

## Docker Deployment

Build and start both services with Docker Compose:

```powershell
docker compose up --build -d
```

After startup:

- Frontend: `http://<server-ip>/`
- Backend API: `http://<server-ip>:8000/api/health`

Important deployment notes:

- `docker-compose.yml` mounts `./data` into the backend container, so the database and extracted frames persist on disk.
- `VIDEO_IMPORT_PATH` controls which host directory is mounted into the backend as `/app/videos`.
- When importing videos from the web UI in Docker, enter the container path, for example:

```text
/app/videos/使用AI平台.mp4
```

- If your server already uses port `80`, change the frontend port mapping in `docker-compose.yml`.
- For server deployment, set a real `VISION_API_KEY` in `.env` before running `docker compose up`.

## Notes

- The backend loads the repository-root `.env` before other modules resolve runtime settings. `API_KEY`, `ALLOWED_VIDEO_DIRS`, and other startup settings therefore take effect on a fresh `import backend.main`.
- Set `ALLOW_ANY_VIDEO_PATHS=true` for a single-user local deployment that should accept arbitrary absolute paths on the host machine.
- `FINE_SCAN_MODE=video` enables segment-level video understanding. The backend still stores one representative preview frame per suspicious segment so the existing search results and detail view continue to work.
- Protected media resources (`/api/frames/*/image`, `/api/videos/*/file`) accept either the normal `X-API-Key` header or an `api_key` query parameter so `<img>` and `<video>` tags can load them directly.
- `ALLOWED_VIDEO_DIRS` uses the system path separator. Windows uses `;`, while Linux/macOS use `:`.
- Set both `API_KEY` and `VITE_API_KEY` to the same value so browser fetches and media URLs use one consistent credential.
- `FINE_SCAN_MODE=frame` keeps the original frame-by-frame path. `FINE_SCAN_MODE=video` sends suspicious clips directly to the multimodal model and indexes the returned segment analysis.
- In `VISION_ANALYZER_MODE=live`, video processing requires `VISION_API_KEY`.
- For UI or local pipeline verification without a real API key, set `VISION_ANALYZER_MODE=mock`.
- The project still accepts legacy `MOONSHOT_API_KEY` / `MOONSHOT_BASE_URL` environment variables for backward compatibility.
- If `ffmpeg` / `ffprobe` are not in `PATH`, set `FFMPEG_COMMAND` and `FFPROBE_COMMAND` to their absolute executable paths.
- For Kimi Code CLI based multimodal analysis with a `coding/v1` key, set:

```powershell
$env:VISION_API_KEY="your-coding-key"
$env:VISION_BASE_URL="https://api.kimi.com/coding/v1"
$env:MODEL_NAME="kimi-for-coding"
$env:VISION_ANALYZER_MODE="kimi_cli"
```

- Task execution is in-memory. Restarting the backend does not resume interrupted jobs yet.
