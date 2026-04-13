from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.models import normalize_path, resolve_path_input


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def is_supported_video(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def build_video_record(
    path: Path,
    *,
    duration: float,
    resolution: str,
    format_name: str,
) -> dict[str, str | float]:
    return {
        "filename": path.name,
        "filepath": normalize_path(path),
        "duration": duration,
        "format": format_name,
        "resolution": resolution,
        "status": "pending",
    }


def validate_folder_path(folder_path: str | Path) -> Path:
    folder = resolve_path_input(folder_path)
    if not folder.exists():
        raise ValueError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise ValueError(f"Folder path is not a directory: {folder}")
    return folder


def probe_video(video_path: str | Path, ffprobe_command: str = "ffprobe") -> dict[str, str | float]:
    path = resolve_path_input(video_path)
    command = [
        ffprobe_command,
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name:stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            f"ffprobe executable not found: {ffprobe_command}. Install FFmpeg or set FFPROBE_COMMAND in .env."
        ) from exc
    except subprocess.CalledProcessError as exc:
        ffprobe_message = (exc.stderr or exc.stdout or "").strip()
        detail = f": {ffprobe_message}" if ffprobe_message else ""
        raise ValueError(f"Unable to inspect video file: {path}{detail}") from exc

    payload = json.loads(completed.stdout or "{}")
    streams = payload.get("streams") or []
    # 查找视频流（而非音频流）
    video_stream = None
    for stream in streams:
        if stream.get("width") and stream.get("height"):
            video_stream = stream
            break

    width = video_stream.get("width", 0) if video_stream else 0
    height = video_stream.get("height", 0) if video_stream else 0
    resolution = f"{width}x{height}" if width and height else ""
    duration = float(payload.get("format", {}).get("duration") or 0.0)
    format_name = payload.get("format", {}).get("format_name") or path.suffix.lstrip(".")
    return build_video_record(path, duration=duration, resolution=resolution, format_name=format_name)


def discover_videos(folder_path: str | Path) -> list[Path]:
    folder = validate_folder_path(folder_path)
    return sorted(path for path in folder.rglob("*") if is_supported_video(path))


class VideoImportService:
    def __init__(self, repository, ffprobe_command: str = "ffprobe"):
        self.repository = repository
        self.ffprobe_command = ffprobe_command

    def import_one(self, path: str) -> dict:
        record = probe_video(path, ffprobe_command=self.ffprobe_command)
        return self.repository.create_video_asset(record)

    def import_folder(self, folder_path: str) -> list[dict]:
        return [self.import_one(str(path)) for path in discover_videos(folder_path)]

    @staticmethod
    def estimate_frames(duration: float, interval: int) -> int:
        if duration <= 0:
            return 0
        return max(1, int(duration // interval) + 1)

    @staticmethod
    def estimate_cost(duration: float, interval: int, image_call_unit_cost: float = 0.0) -> dict:
        frames = VideoImportService.estimate_frames(duration, interval)
        return {
            "estimated_frames": frames,
            "estimated_cost": round(frames * image_call_unit_cost, 4),
        }
