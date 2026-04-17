from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from backend.bootstrap import ensure_environment_loaded


def _get_first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class Settings(BaseModel):
    app_name: str = "视频画面内容检索平台"
    vision_provider: str = Field(default="zhipu")
    api_key: str = Field(default="")
    auth_api_key: str = Field(default="")
    base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4")
    model_name: str = Field(default="glm-4.6v-flashx")
    vision_analyzer_mode: str = Field(default="live")
    kimi_cli_command: str = Field(default="kimi")
    ffmpeg_command: str = Field(default="ffmpeg")
    ffprobe_command: str = Field(default="ffprobe")
    frame_interval: int = Field(default=3, ge=1, le=10)
    frame_max_width: int = Field(default=1280, ge=640, le=3840)
    frame_jpeg_quality: int = Field(default=5, ge=2, le=15)
    coarse_interval: int = Field(default=10, ge=1, le=60)
    hash_threshold: int = Field(default=8, ge=1, le=20)
    suspicious_buffer: float = Field(default=15.0, ge=0.0, le=300.0)
    fine_interval: int = Field(default=3, ge=1, le=30)
    processing_mode: str = Field(default="two_stage")
    api_concurrency: int = Field(default=3, ge=1, le=10)
    task_worker_count: int = Field(default=1, ge=1, le=10)
    api_max_retries: int = Field(default=6, ge=1, le=10)
    api_min_interval_seconds: float = Field(default=1.5, ge=0.0, le=60.0)
    db_path: str = Field(default="data/db/search.db")
    data_dir: str = Field(default="data")
    frames_dir: str = Field(default="data/frames")
    # Video segment analysis (V2)
    fine_scan_mode: str = Field(default="frame")
    video_clip_max_size_mb: int = Field(default=20, ge=1, le=200)
    video_clip_crf: int = Field(default=28, ge=18, le=35)
    allow_any_video_paths: bool = Field(default=False)
    allowed_video_dirs_raw: str = Field(default=".")

    @property
    def db_path_abs(self) -> Path:
        return Path(self.db_path).resolve()

    @property
    def frames_dir_abs(self) -> Path:
        return Path(self.frames_dir).resolve()

    @property
    def allowed_video_directories(self) -> tuple[Path, ...]:
        configured_dirs = [
            Path(segment.strip()).expanduser().resolve()
            for segment in re.split(rf"[{re.escape(os.pathsep)}\n]", self.allowed_video_dirs_raw)
            if segment.strip()
        ]
        if configured_dirs:
            return tuple(configured_dirs)
        return (Path(".").resolve(),)

    @field_validator("fine_scan_mode")
    @classmethod
    def validate_fine_scan_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"frame", "video"}:
            raise ValueError("FINE_SCAN_MODE must be either 'frame' or 'video'.")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    ensure_environment_loaded()
    api_key = _get_first_env("VISION_API_KEY", "ZHIPU_API_KEY", "MOONSHOT_API_KEY")
    base_url = _get_first_env(
        "VISION_BASE_URL",
        "ZHIPU_BASE_URL",
        "MOONSHOT_BASE_URL",
        default="https://open.bigmodel.cn/api/paas/v4",
    )
    provider = _get_first_env("VISION_PROVIDER", default="zhipu")
    configured_mode = os.getenv("VISION_ANALYZER_MODE")
    vision_analyzer_mode = configured_mode if configured_mode else ("live" if api_key else "mock")
    return Settings(
        vision_provider=provider,
        api_key=api_key,
        auth_api_key=os.getenv("API_KEY", "").strip(),
        base_url=base_url,
        model_name=os.getenv("MODEL_NAME", "glm-4.6v-flashx"),
        vision_analyzer_mode=vision_analyzer_mode,
        kimi_cli_command=os.getenv("KIMI_CLI_COMMAND", "kimi"),
        ffmpeg_command=os.getenv("FFMPEG_COMMAND", "ffmpeg"),
        ffprobe_command=os.getenv("FFPROBE_COMMAND", "ffprobe"),
        frame_interval=int(os.getenv("FRAME_INTERVAL", "3")),
        frame_max_width=int(os.getenv("FRAME_MAX_WIDTH", "1280")),
        frame_jpeg_quality=int(os.getenv("FRAME_JPEG_QUALITY", "5")),
        coarse_interval=int(os.getenv("COARSE_INTERVAL", "10")),
        hash_threshold=int(os.getenv("HASH_THRESHOLD", "8")),
        suspicious_buffer=float(os.getenv("SUSPICIOUS_BUFFER", "15.0")),
        fine_interval=int(os.getenv("FINE_INTERVAL", "3")),
        processing_mode=os.getenv("PROCESSING_MODE", "two_stage"),
        api_concurrency=int(os.getenv("API_CONCURRENCY", "3")),
        task_worker_count=int(os.getenv("TASK_WORKER_COUNT", "1")),
        api_max_retries=int(os.getenv("API_MAX_RETRIES", "6")),
        api_min_interval_seconds=float(os.getenv("API_MIN_INTERVAL_SECONDS", "1.5")),
        db_path=os.getenv("DB_PATH", "data/db/search.db"),
        data_dir=os.getenv("DATA_DIR", "data"),
        frames_dir=os.getenv("FRAMES_DIR", "data/frames"),
        fine_scan_mode=os.getenv("FINE_SCAN_MODE", "frame"),
        video_clip_max_size_mb=int(os.getenv("VIDEO_CLIP_MAX_SIZE_MB", "20")),
        video_clip_crf=int(os.getenv("VIDEO_CLIP_CRF", "28")),
        allow_any_video_paths=os.getenv("ALLOW_ANY_VIDEO_PATHS", "false").strip().lower() in {"1", "true", "yes", "on"},
        allowed_video_dirs_raw=os.getenv("ALLOWED_VIDEO_DIRS", "."),
    )
