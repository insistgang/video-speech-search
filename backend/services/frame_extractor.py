from __future__ import annotations

import re
import subprocess
from pathlib import Path


# Shell special characters that are dangerous when a path might reach a shell context.
# These are checked in validate_path() below.
_SHELL_SPECIAL_CHARS_RE = re.compile(r'[;&|`$!<>"\']')

def validate_path(path: str) -> None:
    """验证路径不包含 shell 特殊字符，防止命令注入风险。"""
    if _SHELL_SPECIAL_CHARS_RE.search(path):
        raise ValueError(f"Path contains disallowed shell special characters: {path}")


def build_ffmpeg_command(
    video_path: str,
    output_dir: str,
    ffmpeg_command: str = "ffmpeg",
    interval: int = 3,
    max_width: int = 1280,
    jpeg_quality: int = 5,
    start_time: float | None = None,
    duration: float | None = None,
) -> list[str]:
    validate_path(video_path)
    validate_path(output_dir)
    output_pattern = str(Path(output_dir) / "frame_%04d.jpg")
    video_filters = [
        f"fps=1/{interval}",
        f"scale={max_width}:-2:flags=lanczos:force_original_aspect_ratio=decrease",
    ]

    cmd = [ffmpeg_command, "-y"]

    # 添加起始时间（关键帧快速定位）
    if start_time is not None and start_time > 0:
        cmd.extend(["-ss", str(start_time)])

    cmd.extend(["-i", video_path])

    # 添加持续时间
    if duration is not None and duration > 0:
        cmd.extend(["-t", str(duration)])

    cmd.extend([
        "-vf", ",".join(video_filters),
        "-q:v", str(jpeg_quality),
        output_pattern,
    ])

    return cmd


def extract_frames(
    video_path: str,
    output_dir: str,
    ffmpeg_command: str = "ffmpeg",
    interval: int = 3,
    max_width: int = 1280,
    jpeg_quality: int = 5,
    start_time: float | None = None,
    duration: float | None = None,
) -> list[dict[str, float | int | str]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp_offset = float(start_time or 0.0)
    command = build_ffmpeg_command(
        video_path,
        output_dir,
        ffmpeg_command=ffmpeg_command,
        interval=interval,
        max_width=max_width,
        jpeg_quality=jpeg_quality,
        start_time=start_time,
        duration=duration,
    )
    try:
        subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    except FileNotFoundError as exc:
        raise ValueError(
            f"FFmpeg executable not found: {ffmpeg_command}. Install FFmpeg or set FFMPEG_COMMAND in .env."
        ) from exc
    except subprocess.CalledProcessError as exc:
        ffmpeg_message = (exc.stderr or exc.stdout or "").strip()
        detail = f": {ffmpeg_message}" if ffmpeg_message else ""
        raise ValueError(f"FFmpeg failed while extracting frames from {video_path}{detail}") from exc

    frame_files = sorted(output_path.glob("frame_*.jpg"))
    frames: list[dict[str, float | int | str]] = []
    for index, frame_file in enumerate(frame_files):
        frames.append(
            {
                "frame_index": index,
                "timestamp": float(timestamp_offset + index * interval),
                "image_path": str(frame_file.resolve()),
            }
        )
    return frames
