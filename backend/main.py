from __future__ import annotations

from backend.bootstrap import ensure_environment_loaded

ensure_environment_loaded()

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.auth import verify_api_key

from backend.api.frames import router as frames_router
from backend.api.health import router as health_router
from backend.api.keywords import router as keywords_router
from backend.api.search import router as search_router
from backend.api.stats import router as stats_router
from backend.api.tasks import router as tasks_router
from backend.api.videos import router as videos_router
from backend.config import Settings, get_settings
from backend.db import initialize_database
from backend.repositories import Repository
from backend.services.pipeline import ProcessingPipeline
from backend.services.searcher import SearchService
from backend.services.task_queue import SQLiteTaskQueue
from backend.services.video_import import VideoImportService
from backend.services.vision_analyzer import VisionAnalyzer

LOCALHOST_CORS_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
IMMUTABLE_TASK_DETAIL_KEYS = frozenset({"mode", "requested_mode", "action", "target_stage", "queue_job_id"})
logger = logging.getLogger(__name__)


def merge_task_progress_details(
    current_details: dict[str, Any],
    updates: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(current_details)
    if not updates:
        return merged
    for key, value in updates.items():
        if key in IMMUTABLE_TASK_DETAIL_KEYS:
            continue
        merged[key] = value
    return merged


@dataclass
class ProcessingService:
    settings: Settings
    repository: Repository
    task_queue: SQLiteTaskQueue
    vision_analyzer: VisionAnalyzer
    processing_pipeline: ProcessingPipeline

    def register_handlers(self) -> None:
        """Register job handlers with the task queue."""
        self.task_queue.register_job_handler("video_process", self._handle_video_process)

    async def schedule_video_processing(
        self,
        video_id: int,
        mode: str = "two_stage",
        *,
        action: str = "process",
        target_stage: str | None = None,
    ) -> dict[str, Any]:
        """Schedule a video for processing."""
        details: dict[str, Any] = {
            "action": action,
            "mode": mode,
            "requested_mode": mode,
            "stage": "pending",
        }
        if target_stage is not None:
            details["target_stage"] = target_stage

        # Create task record in processing_tasks table
        task = await asyncio.to_thread(
            self.repository.create_task,
            video_id=video_id,
            task_type="video_process",
            status="pending",
            progress=0.0,
            details=details,
        )
        # Add to persistent task queue
        job_id = await self.task_queue.enqueue(
            name="video_process",
            video_id=video_id,
            mode=mode,
            stage=target_stage or "coarse",
        )
        details["queue_job_id"] = job_id
        updated_task = await asyncio.to_thread(self.repository.update_task, task["id"], details=details)
        return updated_task or task

    async def _handle_video_process(self, ctx: Any) -> None:
        """Handle video processing job from the queue."""
        from backend.services.task_queue import JobContext

        assert isinstance(ctx, JobContext)
        video_id = ctx.video_id

        # Get the latest task for this video
        tasks = await asyncio.to_thread(self.repository.list_tasks, active_only=False)
        video_tasks = [t for t in tasks if t["video_id"] == video_id and t["task_type"] == "video_process"]
        if not video_tasks:
            await ctx.mark_failed("No task record found for video")
            return

        task = next(
            (item for item in video_tasks if int(item.get("details", {}).get("queue_job_id", -1)) == ctx.job_id),
            max(video_tasks, key=lambda t: t["id"]),
        )
        task_id = task["id"]
        current_details = dict(task.get("details", {}) or {})
        mode = str(current_details.get("mode", "two_stage"))
        action = str(current_details.get("action", "process"))
        target_stage = current_details.get("target_stage")
        current_progress = float(task.get("progress") or 0.0)

        async def report_progress(
            progress: float | None = None,
            stage: str | None = None,
            details: dict[str, Any] | None = None,
        ) -> None:
            nonlocal current_details, current_progress

            if details:
                current_details = merge_task_progress_details(current_details, details)
            if stage is not None:
                current_details["stage"] = stage
            if progress is not None:
                current_progress = progress

            await asyncio.to_thread(
                self.repository.update_task,
                task_id,
                progress=current_progress,
                details=current_details.copy(),
            )
            await self.task_queue.update_job_status(
                ctx.job_id,
                progress=current_progress,
                stage=stage or str(current_details.get("stage", "")),
            )

        try:
            await ctx.mark_running(stage=str(target_stage or "processing"))
            await asyncio.to_thread(
                self.repository.update_task,
                task_id,
                status="running",
                progress=0.0,
                details=current_details.copy(),
            )

            if action == "rescan":
                await asyncio.to_thread(self.repository.update_video_status, video_id, "processing")
                if target_stage == "coarse":
                    await self.processing_pipeline.stage_coarse(video_id, progress_callback=report_progress)
                elif target_stage == "fine":
                    await self.processing_pipeline.stage_fine(video_id, progress_callback=report_progress)
                else:
                    raise ValueError(f"Unsupported rescan target_stage: {target_stage}")
                await asyncio.to_thread(self.repository.update_video_status, video_id, "completed")
            else:
                await self.processing_pipeline.process_video(
                    video_id,
                    mode=mode,
                    progress_callback=report_progress,
                )

            await ctx.mark_completed(result={"mode": mode, "video_id": video_id})
            current_details["stage"] = "completed"
            await asyncio.to_thread(
                self.repository.update_task,
                task_id,
                status="completed",
                progress=1.0,
                details=current_details.copy(),
            )
        except Exception as exc:
            error_msg = str(exc)
            if action == "rescan":
                await asyncio.to_thread(self.repository.update_video_status, video_id, "failed")
            await ctx.mark_failed(error_msg)
            current_details["stage"] = "failed"
            await asyncio.to_thread(
                self.repository.update_task,
                task_id,
                status="failed",
                progress=1.0,
                error_message=error_msg,
                details=current_details.copy(),
            )


@dataclass
class AppContext:
    settings: Settings
    repository: Repository
    video_import_service: VideoImportService
    task_queue: SQLiteTaskQueue
    processing_service: ProcessingService
    processing_pipeline: ProcessingPipeline
    search_service: SearchService


def build_context(settings: Settings) -> AppContext:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.frames_dir).mkdir(parents=True, exist_ok=True)
    initialize_database(settings.db_path)
    logger.info("Fine scan mode: %s", settings.fine_scan_mode)
    repository = Repository(settings.db_path)
    task_queue = SQLiteTaskQueue(db_path=settings.db_path, worker_count=settings.task_worker_count)
    vision_analyzer = VisionAnalyzer(
        api_key=settings.api_key,
        base_url=settings.base_url,
        model_name=settings.model_name,
        mode=settings.vision_analyzer_mode,
        cli_command=settings.kimi_cli_command,
        concurrency=settings.api_concurrency,
        max_retries=settings.api_max_retries,
        min_interval_seconds=settings.api_min_interval_seconds,
    )
    processing_pipeline = ProcessingPipeline(
        settings=settings,
        repository=repository,
        vision_analyzer=vision_analyzer,
    )
    processing_service = ProcessingService(
        settings=settings,
        repository=repository,
        task_queue=task_queue,
        vision_analyzer=vision_analyzer,
        processing_pipeline=processing_pipeline,
    )
    # Register job handlers before starting the queue
    processing_service.register_handlers()
    return AppContext(
        settings=settings,
        repository=repository,
        video_import_service=VideoImportService(repository, ffprobe_command=settings.ffprobe_command),
        task_queue=task_queue,
        processing_service=processing_service,
        processing_pipeline=processing_pipeline,
        search_service=SearchService(repository),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    context = build_context(get_settings())
    app.state.context = context
    await context.task_queue.start()
    try:
        yield
    finally:
        await context.task_queue.stop()


# 创建限流器（使用内存存储，生产环境建议使用Redis）
limiter = Limiter(key_func=get_remote_address)


def get_cors_configuration() -> tuple[list[str], str | None]:
    configured = os.getenv("CORS_ORIGINS", "").strip()
    is_production = os.getenv("ENV", "development").lower() == "production"
    if configured:
        origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
        return origins, None if is_production else LOCALHOST_CORS_REGEX
    return [], LOCALHOST_CORS_REGEX


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 默认允许本机开发来源，可通过 CORS_ORIGINS 覆盖为显式列表
cors_origins, cors_origin_regex = get_cors_configuration()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# 包含健康检查路由（用于其他健康检查端点）
app.include_router(health_router, prefix="/api")

# 受保护路由（需要API Key）
protected = [Depends(verify_api_key)]
app.include_router(videos_router, prefix="/api")
app.include_router(tasks_router, prefix="/api", dependencies=protected)
app.include_router(search_router, prefix="/api", dependencies=protected)
app.include_router(keywords_router, prefix="/api", dependencies=protected)
app.include_router(frames_router, prefix="/api")
app.include_router(stats_router, prefix="/api", dependencies=protected)
