# Video Visual Search MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the MVP video visual search platform for silent screen-recording videos using frame extraction, Kimi image understanding, SQLite FTS5 indexing, and a React review UI.

**Architecture:** Use a FastAPI backend to import local videos, extract timestamped JPEG frames with FFmpeg, analyze each frame with Kimi K2.5 through an OpenAI-compatible client, and flatten structured results into SQLite tables plus an FTS5 index. Use a Vite React frontend to manage imports, monitor processing, search hits, and review the matching frame and video timestamp side by side.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, SQLite FTS5, asyncio, FFmpeg, OpenAI Python SDK, React, TypeScript, Vite, TailwindCSS, React Router, pytest, Vitest

---

## Prerequisites

- Initialize version control before starting: `git init`
- Install Python 3.11+, Node.js 20+, npm, and FFmpeg
- Create a virtualenv and install backend dependencies from `requirements.txt`
- Run frontend commands from `frontend/`
- Export the required environment variables before running the worker or API:

```bash
export MOONSHOT_API_KEY="..."
export MOONSHOT_BASE_URL="https://api.moonshot.cn/v1"
export FRAME_INTERVAL="3"
export API_CONCURRENCY="3"
export DB_PATH="data/db/search.db"
export DATA_DIR="data"
```

- Keep original videos in place and store only canonical file paths plus extracted frames under `data/frames/`

### Task 1: Bootstrap the backend API skeleton

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/main.py`
- Create: `backend/api/__init__.py`
- Create: `backend/api/health.py`
- Create: `tests/backend/test_health.py`
- Create: `requirements.txt`

**Step 1: Write the failing healthcheck test**

```python
from fastapi.testclient import TestClient
from backend.main import app

def test_healthcheck():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_health.py::test_healthcheck -q`
Expected: FAIL with `ModuleNotFoundError` for `backend.main`

**Step 3: Write the minimal API implementation**

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def healthcheck():
    return {"status": "ok"}
```

```python
from fastapi import FastAPI
from backend.api.health import router as health_router

app = FastAPI(title="Video Visual Search")
app.include_router(health_router, prefix="/api")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_health.py::test_healthcheck -q`
Expected: PASS

**Step 5: Commit**

```bash
git add requirements.txt backend tests/backend
git commit -m "chore: bootstrap backend api skeleton"
```

### Task 2: Add configuration and SQLite bootstrap

**Files:**
- Create: `backend/config.py`
- Create: `backend/db.py`
- Create: `tests/backend/test_config.py`
- Modify: `backend/main.py`

**Step 1: Write the failing configuration test**

```python
from backend.config import Settings

def test_settings_defaults():
    settings = Settings()
    assert settings.frame_interval == 3
    assert settings.api_concurrency == 3
    assert settings.db_path.endswith("search.db")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_config.py::test_settings_defaults -q`
Expected: FAIL with `ImportError` for `backend.config`

**Step 3: Write minimal settings and DB bootstrap**

```python
from pydantic import BaseModel

class Settings(BaseModel):
    frame_interval: int = 3
    api_concurrency: int = 3
    db_path: str = "data/db/search.db"
```

```python
from pathlib import Path
import sqlite3

def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path, check_same_thread=False)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_config.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add settings and sqlite bootstrap"
```

### Task 3: Define persistence models and FTS5 initialization

**Files:**
- Create: `backend/models.py`
- Create: `backend/repositories.py`
- Create: `tests/backend/test_schema_bootstrap.py`
- Modify: `backend/db.py`

**Step 1: Write the failing schema bootstrap test**

```python
from backend.db import initialize_database, get_connection

def test_initialize_database_creates_tables(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    conn = get_connection(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "video_assets" in names
    assert "frame_analysis_fts" in names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_schema_bootstrap.py::test_initialize_database_creates_tables -q`
Expected: FAIL because `initialize_database` is missing

**Step 3: Add tables and FTS5 bootstrap**

```python
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS video_assets (...);
CREATE TABLE IF NOT EXISTS processing_tasks (...);
CREATE TABLE IF NOT EXISTS video_frames (...);
CREATE TABLE IF NOT EXISTS frame_analysis (...);
CREATE TABLE IF NOT EXISTS keyword_sets (...);
CREATE VIRTUAL TABLE IF NOT EXISTS frame_analysis_fts
USING fts5(video_id, frame_id, timestamp, content);
"""
```

```python
def initialize_database(db_path: str) -> None:
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_schema_bootstrap.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add sqlite schema and fts bootstrap"
```

### Task 4: Implement video metadata probing and import services

**Files:**
- Create: `backend/services/video_import.py`
- Create: `backend/api/videos.py`
- Create: `tests/backend/test_video_import.py`
- Modify: `backend/main.py`

**Step 1: Write the failing import service test**

```python
from pathlib import Path
from backend.services.video_import import build_video_record

def test_build_video_record_uses_original_path(tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake")
    record = build_video_record(video_path, duration=12.5, resolution="1920x1080", format_name="mp4")
    assert record["filepath"] == str(video_path.resolve())
    assert record["duration"] == 12.5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_video_import.py::test_build_video_record_uses_original_path -q`
Expected: FAIL because `video_import.py` is missing

**Step 3: Implement probe and import endpoint**

```python
def build_video_record(path, duration, resolution, format_name):
    return {
        "filename": path.name,
        "filepath": str(path.resolve()),
        "duration": duration,
        "resolution": resolution,
        "format": format_name,
        "status": "pending",
    }
```

```python
@router.post("/videos/import")
def import_video(payload: ImportVideoRequest):
    return service.import_one(payload.path)
```

**Step 4: Run service and API tests**

Run: `pytest tests/backend/test_video_import.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add video import service and api"
```

### Task 5: Implement FFmpeg frame extraction

**Files:**
- Create: `backend/services/frame_extractor.py`
- Create: `tests/backend/test_frame_extractor.py`
- Modify: `backend/services/video_import.py`

**Step 1: Write the failing frame extraction command test**

```python
from backend.services.frame_extractor import build_ffmpeg_command

def test_build_ffmpeg_command_uses_interval_and_jpegs():
    command = build_ffmpeg_command("input.mp4", "data/frames/demo", interval=3)
    assert command[:3] == ["ffmpeg", "-i", "input.mp4"]
    assert "fps=1/3" in command
    assert command[-1].endswith("frame_%04d.jpg")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_frame_extractor.py::test_build_ffmpeg_command_uses_interval_and_jpegs -q`
Expected: FAIL because `frame_extractor.py` is missing

**Step 3: Implement extraction helpers**

```python
def build_ffmpeg_command(video_path, output_pattern, interval):
    return [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        output_pattern,
    ]
```

```python
def extract_frames(video_path: str, output_dir: str, interval: int = 3) -> list[dict]:
    ...
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_frame_extractor.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add ffmpeg frame extraction"
```

### Task 6: Add prompt templates and robust Kimi JSON parsing

**Files:**
- Create: `backend/prompts/__init__.py`
- Create: `backend/prompts/screen_analysis.py`
- Create: `backend/services/json_utils.py`
- Create: `tests/backend/test_json_utils.py`

**Step 1: Write the failing JSON cleanup test**

```python
from backend.services.json_utils import parse_model_json

def test_parse_model_json_strips_markdown_fences():
    payload = "```json\n{\"summary\": \"ok\"}\n```"
    result = parse_model_json(payload)
    assert result["summary"] == "ok"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_json_utils.py::test_parse_model_json_strips_markdown_fences -q`
Expected: FAIL because parser module is missing

**Step 3: Implement prompt and parser**

```python
SCREEN_ANALYSIS_PROMPT = """
You are a screen-recording analysis expert...
Return strict JSON only.
"""
```

```python
def parse_model_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_json_utils.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add screen analysis prompt and json parser"
```

### Task 7: Implement the Kimi vision analyzer with concurrency and retry

**Files:**
- Create: `backend/services/vision_analyzer.py`
- Create: `tests/backend/test_vision_analyzer.py`
- Modify: `backend/config.py`

**Step 1: Write the failing analyzer behavior test**

```python
import asyncio
from backend.services.vision_analyzer import VisionAnalyzer

def test_vision_analyzer_uses_disabled_thinking(fake_client, sample_image):
    analyzer = VisionAnalyzer(client=fake_client, concurrency=2)
    result = asyncio.run(analyzer.analyze_frame(sample_image))
    assert result["summary"] == "mock summary"
    assert fake_client.last_extra_body == {"thinking": {"type": "disabled"}}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_vision_analyzer.py::test_vision_analyzer_uses_disabled_thinking -q`
Expected: FAIL because `VisionAnalyzer` is missing

**Step 3: Implement analyzer, semaphore, and retry loop**

```python
class VisionAnalyzer:
    def __init__(self, client, concurrency: int):
        self.client = client
        self.semaphore = asyncio.Semaphore(concurrency)
```

```python
async def analyze_frame(self, image_path: str) -> dict:
    async with self.semaphore:
        ...
        return parse_model_json(raw_text)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_vision_analyzer.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add kimi vision analyzer with retry controls"
```

### Task 8: Build the in-memory task queue and processing pipeline

**Files:**
- Create: `backend/services/task_queue.py`
- Create: `backend/api/tasks.py`
- Create: `tests/backend/test_task_queue.py`
- Modify: `backend/main.py`
- Modify: `backend/services/video_import.py`

**Step 1: Write the failing queue progression test**

```python
import asyncio
from backend.services.task_queue import InMemoryTaskQueue

def test_queue_runs_jobs_in_order():
    queue = InMemoryTaskQueue()
    seen = []
    async def job():
        seen.append("done")
    asyncio.run(queue.enqueue(job))
    asyncio.run(queue.drain())
    assert seen == ["done"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_task_queue.py::test_queue_runs_jobs_in_order -q`
Expected: FAIL because queue module is missing

**Step 3: Implement queue and task endpoints**

```python
class InMemoryTaskQueue:
    def __init__(self):
        self.queue = asyncio.Queue()
```

```python
@router.get("/tasks")
def list_tasks():
    return repository.list_tasks()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_task_queue.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add in-memory processing queue"
```

### Task 9: Flatten analysis into FTS content and implement search

**Files:**
- Create: `backend/services/indexer.py`
- Create: `backend/services/searcher.py`
- Create: `backend/api/search.py`
- Create: `tests/backend/test_searcher.py`

**Step 1: Write the failing FTS search test**

```python
from backend.services.searcher import search

def test_search_returns_matching_frame(tmp_path):
    results = search("ChatGPT", db_path=str(tmp_path / "search.db"))
    assert isinstance(results, list)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_searcher.py::test_search_returns_matching_frame -q`
Expected: FAIL because `searcher.py` is missing

**Step 3: Implement index projection and search query**

```python
def build_search_content(analysis: dict) -> str:
    return " ".join([
        analysis.get("screen_text", ""),
        analysis.get("operation", ""),
        analysis.get("summary", ""),
        analysis.get("ai_tool_name", ""),
    ]).strip()
```

```python
def search(query: str, filters: dict | None = None, db_path: str = "data/db/search.db") -> list[dict]:
    ...
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_searcher.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add fts indexing and search service"
```

### Task 10: Add frame detail APIs and keyword management

**Files:**
- Create: `backend/api/frames.py`
- Create: `backend/api/keywords.py`
- Create: `tests/backend/test_keywords_api.py`
- Modify: `backend/main.py`

**Step 1: Write the failing keyword API test**

```python
from fastapi.testclient import TestClient
from backend.main import app

def test_create_keyword_set():
    client = TestClient(app)
    response = client.post("/api/keywords", json={"name": "AI", "category": "tool", "terms": ["ChatGPT"]})
    assert response.status_code == 201
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_keywords_api.py::test_create_keyword_set -q`
Expected: FAIL because keyword router is missing

**Step 3: Implement keyword CRUD and frame detail endpoints**

```python
@router.post("/keywords", status_code=201)
def create_keyword_set(payload: KeywordSetCreate):
    return repository.create_keyword_set(payload)
```

```python
@router.get("/frames/{frame_id}/analysis")
def get_frame_analysis(frame_id: int):
    return repository.get_frame_analysis(frame_id)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_keywords_api.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend tests/backend
git commit -m "feat: add frame detail and keyword apis"
```

### Task 11: Bootstrap the React frontend shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.cjs`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/router.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/AppLayout.tsx`
- Create: `frontend/src/pages/ImportPage.tsx`
- Create: `frontend/src/pages/TasksPage.tsx`
- Create: `frontend/src/pages/SearchPage.tsx`
- Create: `frontend/src/pages/ResultDetailPage.tsx`
- Create: `frontend/src/pages/KeywordsPage.tsx`
- Create: `frontend/src/pages/__tests__/AppShell.test.tsx`

**Step 1: Write the failing frontend shell test**

```tsx
import { render, screen } from "@testing-library/react";
import { App } from "../App";

test("renders navigation labels", () => {
  render(<App />);
  expect(screen.getByText("Search")).toBeInTheDocument();
  expect(screen.getByText("Tasks")).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- AppShell.test.tsx`
Expected: FAIL because frontend app files are missing

**Step 3: Implement the shell and router**

```tsx
export function App() {
  return <RouterProvider router={router} />;
}
```

```tsx
const router = createBrowserRouter([
  { path: "/", element: <SearchPage /> },
  { path: "/import", element: <ImportPage /> },
  { path: "/tasks", element: <TasksPage /> },
  { path: "/results/:videoId/:frameId", element: <ResultDetailPage /> },
  { path: "/keywords", element: <KeywordsPage /> },
]);
```

**Step 4: Run tests to verify they pass**

Run: `npm run test -- AppShell.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend
git commit -m "feat: bootstrap react frontend shell"
```

### Task 12: Implement import and task monitoring pages

**Files:**
- Create: `frontend/src/components/ImportForm.tsx`
- Create: `frontend/src/components/TaskTable.tsx`
- Create: `frontend/src/pages/__tests__/ImportPage.test.tsx`
- Modify: `frontend/src/pages/ImportPage.tsx`
- Modify: `frontend/src/pages/TasksPage.tsx`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Write the failing import page test**

```tsx
import { render, screen } from "@testing-library/react";
import { ImportPage } from "../ImportPage";

test("shows import form fields", () => {
  render(<ImportPage />);
  expect(screen.getByLabelText("Video path")).toBeInTheDocument();
  expect(screen.getByText("Import folder")).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- ImportPage.test.tsx`
Expected: FAIL because import UI is not implemented

**Step 3: Implement import and task status UI**

```tsx
export function ImportPage() {
  return <ImportForm onImport={api.importVideo} onImportFolder={api.importFolder} />;
}
```

```tsx
export function TasksPage() {
  return <TaskTable tasks={tasks} />;
}
```

**Step 4: Run tests to verify they pass**

Run: `npm run test -- ImportPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add import and task monitoring pages"
```

### Task 13: Implement search, result detail, and keyword pages

**Files:**
- Create: `frontend/src/components/SearchBar.tsx`
- Create: `frontend/src/components/SearchResultCard.tsx`
- Create: `frontend/src/components/FrameGallery.tsx`
- Create: `frontend/src/components/VideoPlayer.tsx`
- Create: `frontend/src/components/KeywordEditor.tsx`
- Create: `frontend/src/pages/__tests__/SearchPage.test.tsx`
- Modify: `frontend/src/pages/SearchPage.tsx`
- Modify: `frontend/src/pages/ResultDetailPage.tsx`
- Modify: `frontend/src/pages/KeywordsPage.tsx`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Write the failing search page test**

```tsx
import { render, screen } from "@testing-library/react";
import { SearchPage } from "../SearchPage";

test("renders search filters", () => {
  render(<SearchPage />);
  expect(screen.getByPlaceholderText("Search keywords or phrases")).toBeInTheDocument();
  expect(screen.getByLabelText("AI tool detected")).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- SearchPage.test.tsx`
Expected: FAIL because search UI is not implemented

**Step 3: Implement search and review flows**

```tsx
export function SearchPage() {
  return (
    <>
      <SearchBar onSubmit={api.search} />
      {results.map((result) => <SearchResultCard key={result.frameId} result={result} />)}
    </>
  );
}
```

```tsx
export function ResultDetailPage() {
  return (
    <>
      <VideoPlayer src={videoUrl} currentTime={timestamp} />
      <FrameGallery frames={frames} selectedFrameId={frameId} />
    </>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `npm run test -- SearchPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add search results and keyword management ui"
```

### Task 14: Add end-to-end verification and local runbooks

**Files:**
- Create: `tests/backend/test_search_api.py`
- Create: `tests/backend/test_pipeline_smoke.py`
- Create: `README.md`
- Create: `.env.example`
- Modify: `requirements.txt`
- Modify: `frontend/package.json`

**Step 1: Write the failing pipeline smoke test**

```python
def test_pipeline_smoke(tmp_path):
    """
    1. create temp DB
    2. insert one mocked analysis row
    3. query search API
    4. assert one result comes back
    """
    assert False, "replace with real smoke test"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_pipeline_smoke.py::test_pipeline_smoke -q`
Expected: FAIL because the placeholder assertion fails

**Step 3: Replace with a real smoke test and document run commands**

```python
def test_pipeline_smoke(tmp_path, client):
    response = client.post("/api/search", json={"query": "ChatGPT"})
    assert response.status_code == 200
```

```bash
uvicorn backend.main:app --reload
npm install
npm run dev
pytest -q
npm run test
```

**Step 4: Run full verification**

Run: `pytest -q`
Expected: PASS

Run: `npm run test`
Expected: PASS

**Step 5: Commit**

```bash
git add .env.example README.md requirements.txt frontend/package.json tests/backend
git commit -m "docs: add local setup and smoke coverage"
```

## Notes for Execution

- Keep the MVP on the image-frame path only. Do not build `video_url` support in the first pass.
- Use fixed-interval JPEG extraction first. Scene-change extraction is explicitly deferred to V2.1.
- Use SQLite FTS5 only. Do not add vector search, Elasticsearch, or Celery in MVP.
- Log API failures, token usage, and per-video progress from the beginning so the audit trail exists before scaling.
- Record cost estimates in the import flow using `duration / frame_interval` as the first approximation.
