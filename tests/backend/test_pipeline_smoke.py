from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from backend.config import Settings
from backend.main import build_context


def _create_sample_video(output_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for this smoke test")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:d=2",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def test_pipeline_smoke(tmp_path, monkeypatch):
    video_path = tmp_path / "sample.mp4"
    _create_sample_video(video_path)

    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "search.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        coarse_interval=10,
        fine_interval=3,
    )
    context = build_context(settings)
    video = context.video_import_service.import_one(str(video_path))

    # Create proper JPEG frame files for stage_fine_all (mode=deep uses fine_all dir)
    frames_dir = settings.frames_dir_abs / f"video_{video['id']:04d}_fine_all"
    frames_dir.mkdir(parents=True, exist_ok=True)
    test_frames = []
    for i in range(3):
        frame_file = frames_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (320, 180), color=(i * 50, i * 30, i * 10))
        img.save(frame_file, "JPEG", quality=85)
        test_frames.append({
            "frame_index": i,
            "timestamp": float(i * settings.fine_interval),
            "image_path": str(frame_file.resolve()),
        })

    def fake_extract_frames(*args, **kwargs):
        return test_frames

    monkeypatch.setattr("backend.services.pipeline.extract_frames", fake_extract_frames)

    async def run_pipeline():
        await context.task_queue.start()
        try:
            await context.processing_service.schedule_video_processing(video["id"], mode="deep")
            await context.task_queue.drain()
        finally:
            await context.task_queue.stop()

    asyncio.run(run_pipeline())

    assert context.repository.get_video(video["id"])["status"] == "completed"
