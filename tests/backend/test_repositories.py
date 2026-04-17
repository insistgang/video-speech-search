from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import initialize_database
from backend.models import FrameAnalysisRecord
from backend.repositories import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    db_path = tmp_path / "test.db"
    initialize_database(str(db_path))
    return Repository(str(db_path))


class TestCacheFrameOcr:
    def test_cache_and_overwrite(self, repo: Repository) -> None:
        repo.cache_frame_ocr(frame_id=1, video_id=10, ocr_text="Hello")
        row = repo.get_frame(1)
        # frame record does not exist, but ocr cache should
        with repo.connection() as conn:
            cached = conn.execute(
                "SELECT * FROM frame_ocr_cache WHERE frame_id = ?", (1,)
            ).fetchone()
        assert cached is not None
        assert cached["ocr_text"] == "Hello"
        assert cached["hash"] != ""

        # overwrite
        repo.cache_frame_ocr(frame_id=1, video_id=10, ocr_text="World")
        with repo.connection() as conn:
            cached = conn.execute(
                "SELECT * FROM frame_ocr_cache WHERE frame_id = ?", (1,)
            ).fetchone()
        assert cached["ocr_text"] == "World"


class TestSuspiciousSegments:
    def test_create_and_list(self, repo: Repository) -> None:
        repo.create_suspicious_segment(
            video_id=1,
            start_timestamp=1.0,
            end_timestamp=3.0,
            severity="high",
            reason="test reason",
            frame_ids=[10, 11],
        )
        segments = repo.list_suspicious_segments(1)
        assert len(segments) == 1
        assert segments[0]["video_id"] == 1
        assert segments[0]["frame_ids"] == [10, 11]
        assert segments[0]["reason"] == "test reason"

    def test_list_ordered_by_timestamp(self, repo: Repository) -> None:
        repo.create_suspicious_segment(1, 5.0, 6.0, "low", "second", [])
        repo.create_suspicious_segment(1, 1.0, 2.0, "low", "first", [])
        segments = repo.list_suspicious_segments(1)
        assert [s["reason"] for s in segments] == ["first", "second"]


class TestDeleteCoarseArtifacts:
    def test_deletes_segments_and_ocr(self, repo: Repository) -> None:
        repo.create_suspicious_segment(1, 0.0, 1.0, "low", "x", [])
        repo.cache_frame_ocr(1, 1, "text")

        repo.delete_coarse_artifacts(1)

        assert repo.list_suspicious_segments(1) == []
        with repo.connection() as conn:
            row = conn.execute(
                "SELECT * FROM frame_ocr_cache WHERE video_id = ?", (1,)
            ).fetchone()
        assert row is None


class TestInsertAndGetFrames:
    def test_insert_and_returns_inserted_only(self, repo: Repository) -> None:
        # first batch
        result1 = repo.insert_and_get_frames(
            video_id=1,
            frames=[
                {"frame_index": 0, "timestamp": 0.0, "image_path": "/a/1.jpg"},
                {"frame_index": 1, "timestamp": 3.0, "image_path": "/a/2.jpg"},
            ],
        )
        assert len(result1) == 2
        assert result1[0]["timestamp"] == 0.0
        assert result1[1]["timestamp"] == 3.0

        # second batch
        result2 = repo.insert_and_get_frames(
            video_id=1,
            frames=[
                {"frame_index": 2, "timestamp": 6.0, "image_path": "/a/3.jpg"},
            ],
        )
        assert len(result2) == 1
        assert result2[0]["timestamp"] == 6.0

        # total frames for video
        all_frames = repo.get_frames_for_video(1)
        assert len(all_frames) == 3

    def test_empty_frames_returns_empty(self, repo: Repository) -> None:
        assert repo.insert_and_get_frames(1, []) == []


class TestGetMaxFrameIndex:
    def test_returns_negative_one_when_no_frames(self, repo: Repository) -> None:
        assert repo.get_max_frame_index(1) == -1

    def test_returns_max_index(self, repo: Repository) -> None:
        repo.insert_and_get_frames(
            video_id=1,
            frames=[
                {"frame_index": 5, "timestamp": 0.0, "image_path": "/a/1.jpg"},
                {"frame_index": 10, "timestamp": 1.0, "image_path": "/a/2.jpg"},
            ],
        )
        assert repo.get_max_frame_index(1) == 10


class TestSaveFrameAnalysisFtsSync:
    def test_fts_synced_via_upsert_fts(self, repo: Repository) -> None:
        # create a frame first so foreign key holds
        frames = repo.insert_and_get_frames(
            video_id=1,
            frames=[{"frame_index": 0, "timestamp": 0.0, "image_path": "/a/1.jpg"}],
        )
        frame_id = frames[0]["id"]

        record = FrameAnalysisRecord(
            frame_id=frame_id,
            video_id=1,
            raw_json={"screen_text": "AI writing"},
            screen_text="AI writing",
            timestamp=0.0,
        )
        repo.save_frame_analysis(record)
        repo.upsert_fts(
            frame_id=frame_id,
            video_id=1,
            timestamp=0.0,
            content="AI writing",
        )

        with repo.connection() as conn:
            row = conn.execute(
                "SELECT * FROM frame_analysis_fts WHERE frame_id = ?", (frame_id,)
            ).fetchone()
        assert row is not None
        assert "AI writing" in row["content"]
