from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image

from backend.config import Settings
from backend.main import build_context


class FakeConcurrentAnalyzer:
    def __init__(self, concurrency: int):
        self._semaphore = asyncio.Semaphore(concurrency)
        self._lock = asyncio.Lock()
        self._running = 0
        self.max_running = 0

    async def analyze_video_segment(
        self, video_path: str, start_time: float, duration: float, **kwargs
    ) -> dict:
        """Fake for video segment analysis — used when FINE_SCAN_MODE=video in tests."""
        await asyncio.sleep(0.05)
        return {
            "screen_text": "fake video analysis",
            "application": "mock",
            "url": "",
            "operation": "processed",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": [],
            "operation_sequence": [],
            "summary": "fake video segment analysis",
            "_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "_segment_start": start_time,
            "_segment_end": start_time + duration,
        }

    async def analyze_frame(self, image_path: str) -> dict:
        async with self._semaphore:
            async with self._lock:
                self._running += 1
                self.max_running = max(self.max_running, self._running)
            await asyncio.sleep(0.05)
            async with self._lock:
                self._running -= 1

        frame_name = Path(image_path).stem
        return {
            "screen_text": f"{frame_name} analysis",
            "application": "mock",
            "url": "",
            "operation": "processed",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": [],
            "summary": f"{frame_name} summary",
            "_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def test_processing_service_analyzes_frames_concurrently(tmp_path, monkeypatch):
    """Test that stage_fine uses asyncio.gather for concurrent frame analysis."""
    settings = Settings(
        vision_analyzer_mode="mock",
        api_concurrency=2,
        fine_scan_mode="frame",  # Explicit frame mode to test the concurrent analyze_frame path
        db_path=str(tmp_path / "search.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
    )
    context = build_context(settings)
    fake_analyzer = FakeConcurrentAnalyzer(concurrency=settings.api_concurrency)
    context.processing_pipeline.vision_analyzer = fake_analyzer

    video_id = context.repository.create_video_asset({
        "filename": "demo.mp4",
        "filepath": str((tmp_path / "demo.mp4").resolve()),
        "duration": 9.0,
        "format": "mp4",
        "resolution": "1920x1080",
        "status": "pending",
    })["id"]

    context.repository.upsert_keyword_set(
        name="test-keywords",
        category="default",
        terms=["keyword"],
    )

    # Create coarse frames (used by stage_coarse in two_stage mode)
    coarse_dir = settings.frames_dir_abs / f"video_{video_id:04d}_coarse"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    coarse_frames = []
    for i in range(3):
        frame_file = coarse_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (320, 180), color=(i * 50, i * 30, i * 10))
        img.save(frame_file, "JPEG", quality=85)
        coarse_frames.append({
            "frame_index": i,
            "timestamp": float(i * settings.coarse_interval),
            "image_path": str(frame_file.resolve()),
        })

    # stage_fine uses fine_interval in a separate segment dir
    fine_dir = settings.frames_dir_abs / f"video_{video_id:04d}_fine"
    fine_dir.mkdir(parents=True, exist_ok=True)
    fine_frames = []
    for i in range(3):
        frame_file = fine_dir / f"frame_{i+1:04d}.jpg"
        # Use distinct base colors with per-image noise to guarantee distinct pHash values.
        # Solid PIL images at similar brightness produce identical DCT phashes, so we add
        # i-dependent random noise to ensure each frame's hash is unique after dedup.
        import numpy as np
        base = np.array(Image.new("RGB", (320, 180), color=(i * 80, i * 50, i * 25)), dtype=np.float32)
        noise = np.random.randint(-40 - i * 15, 40 + i * 15, base.shape, dtype=np.int16)
        img = Image.fromarray(np.clip(base + noise * (i + 1) / 3, 0, 255).astype(np.uint8))
        img.save(frame_file, "JPEG", quality=85)
        fine_frames.append({
            "frame_index": i,
            "timestamp": float(i * settings.fine_interval),
            "image_path": str(frame_file.resolve()),
        })

    def fake_extract_frames(*args, **kwargs):
        # stage_fine creates segment-specific subdirs; detect which interval is requested
        if "coarse" in str(args[1]):
            return coarse_frames
        return fine_frames

    monkeypatch.setattr("backend.services.pipeline.extract_frames", fake_extract_frames)
    monkeypatch.setattr("backend.services.pipeline.extract_screen_text", lambda *_args, **_kwargs: "keyword")

    async def run_pipeline() -> dict:
        await context.task_queue.start()
        try:
            # mode="two_stage" calls stage_coarse + stage_fine
            # stage_coarse: coarse frames -> no model calls (OCR only)
            # stage_fine: calls model concurrently via asyncio.gather
            task = await context.processing_service.schedule_video_processing(video_id, mode="two_stage")
            await context.task_queue.drain()
            return task
        finally:
            await context.task_queue.stop()

    task = asyncio.run(run_pipeline())
    stored_task = context.repository.get_task(task["id"])

    # Concurrency should be limited to api_concurrency=2
    assert fake_analyzer.max_running == 2
    assert stored_task is not None
    assert stored_task["status"] == "completed"
    assert stored_task["details"]["queue_job_id"] >= 1
    assert stored_task["details"]["phase"] == "fine"
    assert stored_task["details"]["frames_analyzed"] == 3
    assert stored_task["details"]["token_usage"]["total_tokens"] == 6
    # All 3 fine frames should be analyzed
    frame_analysis = context.repository.get_frames_for_video(video_id)
    fine_frames = [f for f in frame_analysis if "fine" in f["image_path"]]
    assert len(fine_frames) == 3


class FakeStreamingAnalyzer:
    def __init__(self):
        self.release_slow_frames = asyncio.Event()
        self.first_frame_done = asyncio.Event()

    async def analyze_frame(self, image_path: str) -> dict:
        frame_name = Path(image_path).stem
        if frame_name == "frame_0001":
            await asyncio.sleep(0.01)
            self.first_frame_done.set()
        else:
            await self.release_slow_frames.wait()

        return {
            "screen_text": f"{frame_name} analysis",
            "application": "mock",
            "url": "",
            "operation": "processed",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": [],
            "summary": f"{frame_name} summary",
            "_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def test_processing_pipeline_handles_streaming_analyzer_correctly(tmp_path, monkeypatch):
    """Test that stage_fine_all completes all frames even when analyzer signals frame-by-frame."""
    settings = Settings(
        vision_analyzer_mode="mock",
        api_concurrency=2,
        db_path=str(tmp_path / "search.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
    )
    context = build_context(settings)
    fake_analyzer = FakeStreamingAnalyzer()
    context.processing_pipeline.vision_analyzer = fake_analyzer

    video_id = context.repository.create_video_asset({
        "filename": "demo.mp4",
        "filepath": str((tmp_path / "demo.mp4").resolve()),
        "duration": 9.0,
        "format": "mp4",
        "resolution": "1920x1080",
        "status": "pending",
    })["id"]

    frames_dir = settings.frames_dir_abs / f"video_{video_id:04d}_fine_all"
    frames_dir.mkdir(parents=True, exist_ok=True)
    extracted_frames = []
    for i in range(3):
        frame_file = frames_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (320, 180), color=(i * 50, i * 30, i * 10))
        img.save(frame_file, "JPEG", quality=85)
        extracted_frames.append({
            "frame_index": i,
            "timestamp": float(i * settings.fine_interval),
            "image_path": str(frame_file.resolve()),
        })

    def fake_extract_frames(*args, **kwargs):
        return extracted_frames

    monkeypatch.setattr("backend.services.pipeline.extract_frames", fake_extract_frames)
    monkeypatch.setattr(
        "backend.services.pipeline.deduplicate_frames",
        lambda frame_paths, _threshold=None: frame_paths,
    )

    async def run_pipeline() -> tuple[dict, dict | None]:
        await context.task_queue.start()
        try:
            task = await context.processing_service.schedule_video_processing(video_id, mode="deep")
            await fake_analyzer.first_frame_done.wait()

            mid_task = None
            for _ in range(50):
                candidate = context.repository.get_task(task["id"])
                if candidate and int(candidate["details"].get("processed_frames", 0)) >= 1:
                    mid_task = candidate
                    break
                await asyncio.sleep(0.01)

            fake_analyzer.release_slow_frames.set()
            await context.task_queue.drain()
            return task, mid_task
        finally:
            await context.task_queue.stop()

    task, mid_task = asyncio.run(run_pipeline())
    stored_task = context.repository.get_task(task["id"])

    assert mid_task is not None
    assert mid_task["status"] == "running"
    assert 0 < mid_task["progress"] < 1
    assert mid_task["details"]["stage"] == "deep_analyzing"
    assert mid_task["details"]["processed_frames"] == 1
    assert mid_task["details"]["token_usage"]["total_tokens"] == 2

    assert stored_task is not None
    assert stored_task["status"] == "completed"
    assert stored_task["details"]["processed_frames"] == 3
    assert stored_task["details"]["token_usage"]["total_tokens"] == 6
    # Video should be marked as completed
    video_record = context.repository.get_video(video_id)
    assert video_record["status"] == "completed"
