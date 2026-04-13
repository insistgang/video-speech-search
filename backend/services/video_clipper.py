from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Reuse path validation from frame_extractor (avoids duplication)
from backend.services.frame_extractor import validate_path

# Shell special characters checked by validate_path
MAX_RETRIES = 3
MAX_CRF = 35
DEFAULT_CRF = 28


def _build_clip_command(
    video_path: str,
    output_path: str,
    start_time: float,
    duration: float,
    ffmpeg_command: str = "ffmpeg",
    crf: int = DEFAULT_CRF,
) -> list[str]:
    return [
        ffmpeg_command,
        "-ss",
        str(start_time),
        "-i",
        video_path,
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        str(crf),
        "-an",  # No audio — screen recordings don't need it
        "-y",   # Overwrite output without asking
        output_path,
    ]


def clip_video_segment(
    video_path: str,
    start_time: float,
    duration: float,
    max_size_mb: int = 20,
    crf: int = DEFAULT_CRF,
    ffmpeg_command: str = "ffmpeg",
) -> str:
    """
    Clip a video segment from a video file.

    Args:
        video_path: Path to the source video file.
        start_time: Start time in seconds.
        duration: Duration of the clip in seconds.
        max_size_mb: Maximum file size in MB. If exceeded, CRF is increased
                     (up to MAX_CRF) and the clip is re-generated.
        crf: Initial H.264 CRF value (lower = better quality, larger file).
        ffmpeg_command: Path to the ffmpeg executable.

    Returns:
        Path to the generated clip file (absolute, as a string).

    Raises:
        ValueError: If FFmpeg fails or the output exceeds max_size_mb after
                    all CRF retries.
    """
    validate_path(video_path)

    # Use a temp directory that persists until the caller deletes it.
    # Caller is responsible for cleanup via _cleanup_clip().
    temp_dir = Path(tempfile.mkdtemp(prefix="video_clip_"))
    output_path = str(temp_dir / "clip.mp4")

    current_crf = crf
    last_error: str = ""

    for attempt in range(MAX_RETRIES):
        cmd = _build_clip_command(
            video_path=video_path,
            output_path=output_path,
            start_time=start_time,
            duration=duration,
            ffmpeg_command=ffmpeg_command,
            crf=current_crf,
        )
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                f"FFmpeg executable not found: {ffmpeg_command}. "
                "Install FFmpeg or set FFMPEG_COMMAND in .env."
            ) from exc
        except subprocess.CalledProcessError as exc:
            ffmpeg_message = (exc.stderr or exc.stdout or "").strip()
            last_error = f"FFmpeg failed (attempt {attempt + 1}): {ffmpeg_message}"
            raise ValueError(last_error) from exc

        # Check file size
        clip_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        if clip_size_mb <= max_size_mb:
            return output_path

        # Exceeded size limit — increase CRF (worse quality, smaller file) and retry
        if current_crf >= MAX_CRF:
            raise ValueError(
                f"Clip size ({clip_size_mb:.1f} MB) exceeds limit ({max_size_mb} MB) "
                f"even at maximum CRF ({MAX_CRF})."
            )
        current_crf = min(current_crf + 3, MAX_CRF)

    # Should not reach here, but guard anyway
    raise ValueError(f"Failed to produce a clip within size limit after {MAX_RETRIES} attempts: {last_error}")


def cleanup_clip(clip_path: str) -> None:
    """
    Delete the temporary clip file and its containing directory.

    Safe to call multiple times.
    """
    path = Path(clip_path)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        shutil.rmtree(path.parent, ignore_errors=True)
    except OSError:
        pass
