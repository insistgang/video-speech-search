from __future__ import annotations

from pathlib import Path
from typing import Any
import unicodedata

from pydantic import BaseModel, Field

from backend.config import get_settings


class ImportVideoRequest(BaseModel):
    path: str
    mode: str = "two_stage"


class ImportFolderRequest(BaseModel):
    folder_path: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    video_id: int | None = None
    time_start: float | None = None
    time_end: float | None = None
    ai_tool_detected: bool | None = None


class KeywordSetCreate(BaseModel):
    name: str
    category: str
    terms: list[str] = Field(default_factory=list)


class KeywordSetUpdate(BaseModel):
    name: str
    category: str
    terms: list[str] = Field(default_factory=list)


class VideoProbeResult(BaseModel):
    filename: str
    filepath: str
    duration: float
    format: str
    resolution: str


class FrameAnalysisRecord(BaseModel):
    frame_id: int
    video_id: int
    raw_json: dict[str, Any]
    screen_text: str = ""
    application: str = ""
    url: str = ""
    operation: str = ""
    ai_tool_detected: bool = False
    ai_tool_name: str = ""
    code_visible: bool = False
    code_content_summary: str = ""
    risk_indicators: list[str] = Field(default_factory=list)
    summary: str = ""
    timestamp: float


def sanitize_path_input(path: str | Path) -> str:
    cleaned = str(path).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _normalize_path_segment(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Cf")
    normalized = " ".join(normalized.split())
    return normalized.casefold()


def _resolve_existing_path_flexibly(path: str | Path) -> Path:
    candidate = Path(sanitize_path_input(path)).expanduser()
    if candidate.exists():
        return candidate.resolve()

    absolute = candidate if candidate.is_absolute() else (Path.cwd() / candidate)
    parts = absolute.parts
    if not parts:
        return absolute.resolve()

    current = Path(parts[0])
    for segment in parts[1:]:
        try:
            children = list(current.iterdir())
        except OSError:
            return absolute.resolve()

        normalized_target = _normalize_path_segment(segment)
        matches = [child for child in children if _normalize_path_segment(child.name) == normalized_target]
        if len(matches) != 1:
            return absolute.resolve()
        current = matches[0]

    return current.resolve()


def resolve_path_input(path: str | Path) -> Path:
    """解析并验证路径，确保在允许的目录范围内。"""
    resolved = _resolve_existing_path_flexibly(path)
    settings = get_settings()
    if settings.allow_any_video_paths:
        return resolved

    allowed_directories = list(settings.allowed_video_directories)

    # 路径遍历验证
    for allowed_dir in allowed_directories:
        try:
            resolved.relative_to(allowed_dir)
            return resolved
        except ValueError:
            continue

    raise ValueError(
        f"Path '{path}' is outside allowed directories: "
        f"{[str(d) for d in allowed_directories]}"
    )


def normalize_path(path: str | Path) -> str:
    return str(resolve_path_input(path))


def get_allowed_video_directories() -> list[Path]:
    return list(get_settings().allowed_video_directories)
