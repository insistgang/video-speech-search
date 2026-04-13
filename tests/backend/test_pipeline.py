from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.config import Settings
from backend.db import initialize_database
from backend.repositories import Repository
from backend.services.pipeline import ProcessingPipeline
from backend.services.searcher import SearchService


def _mock_vision_analyzer() -> MagicMock:
    """Create a mock VisionAnalyzer that returns predictable results."""
    mock = MagicMock()
    mock.analyze_frame = AsyncMock(
        return_value={
            "screen_text": "Test screen",
            "application": "TestApp",
            "url": "",
            "operation": "testing",
            "ai_tool_detected": True,
            "ai_tool_name": "TestAI",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": [],
            "summary": "Test summary",
            "_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
    )
    mock.analyze_video_segment = AsyncMock(
        return_value={
            "screen_text": "Video segment text",
            "application": "TestApp",
            "url": "",
            "operation": "segment testing",
            "ai_tool_detected": True,
            "ai_tool_name": "TestAI",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": ["segment"],
            "operation_sequence": ["打开应用", "执行操作"],
            "summary": "Video segment summary",
            "_usage": {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
            "_segment_start": 0.0,
            "_segment_end": 3.0,
        }
    )
    return mock


def _create_mock_video(tmp_path: Path) -> tuple[Path, dict]:
    """Create a mock video file and return its path and video record."""
    video_path = tmp_path / "test_video.mp4"
    # Create a minimal valid MP4 file (or any file for testing)
    video_path.write_bytes(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41")
    video_record = {
        "id": 1,
        "filename": "test_video.mp4",
        "filepath": str(video_path),
        "duration": 10.0,
        "format": "mp4",
        "resolution": "320x180",
        "status": "pending",
    }
    return video_path, video_record


def test_pipeline_stage_coarse_processes_frames(tmp_path, monkeypatch):
    """Test that stage_coarse extracts frames and performs OCR."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        coarse_interval=10,
        hash_threshold=8,
    )

    # Initialize database schema
    initialize_database(settings.db_path)

    # Create actual image frames for testing
    from PIL import Image
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True)
    frame_paths = []
    for i in range(3):
        img_path = frames_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (64, 64), color=(i * 80, 50, 150))
        img.save(img_path)
        frame_paths.append({
            "frame_index": i,
            "timestamp": float(i * 10),
            "image_path": str(img_path),
        })

    # Mock VisionAnalyzer
    mock_analyzer = _mock_vision_analyzer()

    # Setup repository with a mock video
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    repo.create_video_asset(video_record)

    # Mock extract_frames to return our test frames
    def fake_extract_frames(*args, **kwargs):
        return frame_paths

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        result = __import__("asyncio").run(pipeline.stage_coarse(video_id=1))

    assert result["video_id"] == 1
    assert result["stage"] == "coarse"
    assert result["frames_extracted"] == 3


def test_pipeline_stage_fine_with_no_segments(tmp_path):
    """Test that stage_fine handles empty suspicious segments."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        fine_interval=3,
        hash_threshold=8,
        suspicious_buffer=5.0,
    )

    initialize_database(settings.db_path)
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    repo.create_video_asset(video_record)

    mock_analyzer = _mock_vision_analyzer()
    pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)

    result = __import__("asyncio").run(pipeline.stage_fine(video_id=1))

    assert result["video_id"] == 1
    assert result["stage"] == "fine"
    assert result["segments_processed"] == 0


def test_pipeline_stage_fine_persists_analysis_rows(tmp_path):
    """Test that stage_fine writes analysis rows for extracted frames."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        fine_interval=3,
        hash_threshold=8,
        suspicious_buffer=5.0,
    )

    initialize_database(settings.db_path)
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    video = repo.create_video_asset(video_record)

    with repo.connection() as conn:
        conn.execute(
            """
            INSERT INTO suspicious_segments (video_id, start_timestamp, end_timestamp, severity, reason, frame_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (video["id"], 0.0, 3.0, "medium", "test", "[]"),
        )
        conn.commit()

    from PIL import Image

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True)
    frame_paths = []
    for i in range(2):
        img_path = frames_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (64, 64), color=(i * 80, 50, 150))
        img.save(img_path)
        frame_paths.append({
            "frame_index": i,
            "timestamp": float(i * 3),
            "image_path": str(img_path),
        })

    mock_analyzer = _mock_vision_analyzer()

    def fake_extract_frames(*args, **kwargs):
        return frame_paths

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames), patch(
        "backend.services.pipeline.deduplicate_frames",
        return_value=[frame["image_path"] for frame in frame_paths],
    ):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        result = __import__("asyncio").run(pipeline.stage_fine(video_id=video["id"]))

    assert result["frames_analyzed"] == 2
    saved_frames = repo.get_frames_for_video(video["id"])
    assert len(saved_frames) == 2
    assert all(repo.get_frame_analysis(frame["id"]) is not None for frame in saved_frames)


def test_pipeline_stage_fine_video_mode_persists_segment_analysis_with_preview_frame(tmp_path):
    """Test that video-mode fine scan stores one representative frame per segment."""
    settings = Settings(
        vision_analyzer_mode="mock",
        fine_scan_mode="video",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        suspicious_buffer=5.0,
    )

    initialize_database(settings.db_path)
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    video = repo.create_video_asset(video_record)

    with repo.connection() as conn:
        conn.execute(
            """
            INSERT INTO suspicious_segments (video_id, start_timestamp, end_timestamp, severity, reason, frame_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (video["id"], 0.0, 3.0, "medium", "test", "[]"),
        )
        conn.commit()

    from PIL import Image

    preview_dir = tmp_path / "preview"
    preview_dir.mkdir(parents=True)
    preview_path = preview_dir / "frame_0001.jpg"
    Image.new("RGB", (64, 64), color=(80, 50, 150)).save(preview_path)

    mock_analyzer = _mock_vision_analyzer()

    def fake_extract_frames(*args, **kwargs):
        return [{
            "frame_index": 0,
            "timestamp": float(kwargs.get("start_time") or 0.0),
            "image_path": str(preview_path.resolve()),
        }]

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        result = __import__("asyncio").run(pipeline.stage_fine(video_id=video["id"]))

    assert result["video_id"] == video["id"]
    assert result["mode"] == "video"
    assert result["frames_analyzed"] == 1

    saved_frames = repo.get_frames_for_video(video["id"])
    assert len(saved_frames) == 1
    analysis = repo.get_frame_analysis(saved_frames[0]["id"])
    assert analysis is not None
    assert analysis["summary"] == "Video segment summary"
    assert analysis["raw_json"]["_fine_scan_mode"] == "video"
    assert analysis["raw_json"]["operation_sequence"] == ["打开应用", "执行操作"]

    results = SearchService(repo).search("打开应用")
    assert len(results) == 1
    assert results[0]["frame_id"] == saved_frames[0]["id"]


def test_pipeline_stage_fine_preserves_absolute_timestamps_with_start_offset(monkeypatch):
    """Test that stage_fine stores absolute timestamps when FFmpeg extracts from a segment offset."""
    work_dir = Path(".tmp/test_pipeline_stage_fine_preserves_absolute_timestamps_with_start_offset").resolve()
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(work_dir / "test.db"),
        data_dir=str(work_dir / "data"),
        frames_dir=str(work_dir / "data" / "frames"),
        fine_interval=3,
        hash_threshold=8,
        suspicious_buffer=5.0,
    )

    initialize_database(settings.db_path)
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(work_dir)
    video = repo.create_video_asset(video_record)

    with repo.connection() as conn:
        conn.execute(
            """
            INSERT INTO suspicious_segments (video_id, start_timestamp, end_timestamp, severity, reason, frame_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (video["id"], 8.0, 11.0, "medium", "test", "[]"),
        )
        conn.commit()

    mock_analyzer = _mock_vision_analyzer()

    def fake_run(command, **kwargs):
        output_pattern = Path(command[-1])
        output_dir = output_pattern.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        from PIL import Image

        for i in range(2):
            img_path = output_dir / f"frame_{i+1:04d}.jpg"
            Image.new("RGB", (64, 64), color=(i * 80, 50, 150)).save(img_path)
        return None

    monkeypatch.setattr("backend.services.frame_extractor.subprocess.run", fake_run)

    with patch("backend.services.pipeline.deduplicate_frames", side_effect=lambda frame_paths, _threshold=None: frame_paths):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        result = __import__("asyncio").run(pipeline.stage_fine(video_id=video["id"]))

    assert result["frames_analyzed"] == 2
    saved_frames = repo.get_frames_for_video(video["id"])
    assert [frame["timestamp"] for frame in saved_frames] == [3.0, 6.0]


def test_pipeline_stage_coarse_results_are_searchable(tmp_path):
    """Test that coarse-only processing still produces searchable frame records."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        coarse_interval=10,
        hash_threshold=8,
    )

    initialize_database(settings.db_path)
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    video = repo.create_video_asset(video_record)

    from PIL import Image

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True)
    img_path = frames_dir / "frame_0001.jpg"
    Image.new("RGB", (64, 64), color=(40, 60, 80)).save(img_path)
    frame_paths = [{
        "frame_index": 0,
        "timestamp": 0.0,
        "image_path": str(img_path),
    }]

    mock_analyzer = _mock_vision_analyzer()

    def fake_extract_frames(*args, **kwargs):
        return frame_paths

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames), patch(
        "backend.services.pipeline.extract_screen_text", return_value="ChatGPT terminal"
    ):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        __import__("asyncio").run(pipeline.stage_coarse(video_id=video["id"]))

    results = SearchService(repo).search("ChatGPT")

    assert len(results) == 1
    assert results[0]["frame_id"] == 1
    assert results[0]["matched_text"] == "ChatGPT terminal"


def test_pipeline_stage_coarse_resets_previous_rows(tmp_path):
    """Test that rerunning coarse processing does not duplicate frame rows."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        coarse_interval=10,
        hash_threshold=8,
    )

    initialize_database(settings.db_path)
    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    video = repo.create_video_asset(video_record)

    mock_analyzer = _mock_vision_analyzer()

    def fake_extract_frames(*args, **kwargs):
        output_dir = Path(args[1])
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_frames = []
        from PIL import Image

        for i in range(2):
            img_path = output_dir / f"frame_{i+1:04d}.jpg"
            Image.new("RGB", (64, 64), color=(i * 90, 40, 80)).save(img_path)
            generated_frames.append({
                "frame_index": i,
                "timestamp": float(i * 10),
                "image_path": str(img_path.resolve()),
            })
        return generated_frames

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames), patch(
        "backend.services.pipeline.extract_screen_text", return_value="screen text"
    ):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        __import__("asyncio").run(pipeline.stage_coarse(video_id=video["id"]))
        __import__("asyncio").run(pipeline.stage_coarse(video_id=video["id"]))

    frames = repo.get_frames_for_video(video["id"])
    assert len(frames) == 2


def test_pipeline_process_video_quick_mode(tmp_path, monkeypatch):
    """Test that process_video quick mode only runs coarse stage."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        coarse_interval=10,
        hash_threshold=8,
    )

    initialize_database(settings.db_path)

    # Create actual image frames for testing
    from PIL import Image
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True)
    frame_paths = []
    for i in range(3):
        img_path = frames_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (64, 64), color=(i * 80, 50, 150))
        img.save(img_path)
        frame_paths.append({
            "frame_index": i,
            "timestamp": float(i * 10),
            "image_path": str(img_path),
        })

    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    repo.create_video_asset(video_record)

    mock_analyzer = _mock_vision_analyzer()

    def fake_extract_frames(*args, **kwargs):
        return frame_paths

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        result = __import__("asyncio").run(pipeline.process_video(video_id=1, mode="quick"))

    assert result["video_id"] == 1
    assert result["mode"] == "quick"
    assert result["status"] == "completed"


def test_pipeline_process_video_invalid_mode():
    """Test that process_video raises error for unknown mode."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path="test.db",
        data_dir="data",
        frames_dir="data/frames",
    )

    repo = MagicMock(spec=Repository)
    repo.get_video.return_value = {"id": 1}

    mock_analyzer = _mock_vision_analyzer()
    pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)

    with pytest.raises(ValueError, match="Unknown mode"):
        __import__("asyncio").run(pipeline.process_video(video_id=1, mode="invalid"))


def test_pipeline_process_video_not_found():
    """Test that process_video raises error for non-existent video."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path="test.db",
        data_dir="data",
        frames_dir="data/frames",
    )

    repo = MagicMock(spec=Repository)
    repo.get_video.return_value = None

    mock_analyzer = _mock_vision_analyzer()
    pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)

    with pytest.raises(ValueError, match="not found"):
        __import__("asyncio").run(pipeline.process_video(video_id=999))


def test_pipeline_stage_fine_all_returns_token_usage(tmp_path):
    """Test that stage_fine_all returns token usage statistics."""
    settings = Settings(
        vision_analyzer_mode="mock",
        db_path=str(tmp_path / "test.db"),
        data_dir=str(tmp_path / "data"),
        frames_dir=str(tmp_path / "data" / "frames"),
        fine_interval=3,
        hash_threshold=8,
    )

    initialize_database(settings.db_path)

    # Create actual image frames for testing
    from PIL import Image
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True)
    frame_paths = []
    for i in range(3):
        img_path = frames_dir / f"frame_{i+1:04d}.jpg"
        img = Image.new("RGB", (64, 64), color=(i * 80, 50, 150))
        img.save(img_path)
        frame_paths.append({
            "frame_index": i,
            "timestamp": float(i * 3),
            "image_path": str(img_path),
        })

    repo = Repository(settings.db_path)
    video_path, video_record = _create_mock_video(tmp_path)
    repo.create_video_asset(video_record)

    mock_analyzer = _mock_vision_analyzer()

    def fake_extract_frames(*args, **kwargs):
        return frame_paths

    with patch("backend.services.pipeline.extract_frames", fake_extract_frames):
        pipeline = ProcessingPipeline(settings=settings, repository=repo, vision_analyzer=mock_analyzer)
        result = __import__("asyncio").run(pipeline.stage_fine_all(video_id=1))

    assert result["video_id"] == 1
    assert result["stage"] == "fine_all"
    assert "token_usage" in result
