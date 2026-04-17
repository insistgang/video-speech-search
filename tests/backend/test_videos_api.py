import json

from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app


def _configure_app_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "search.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FRAMES_DIR", str(tmp_path / "data" / "frames"))
    monkeypatch.setenv("VISION_ANALYZER_MODE", "mock")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", str(tmp_path.resolve()))
    get_settings.cache_clear()


def test_video_segments_endpoint_returns_parsed_frame_ids(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    with TestClient(app) as client:
        context = client.app.state.context
        video = context.repository.create_video_asset(
            {
                "filename": "demo.mp4",
                "filepath": str((tmp_path / "demo.mp4").resolve()),
                "duration": 12.0,
                "format": "mp4",
                "resolution": "1920x1080",
                "status": "completed",
            }
        )

        with context.repository.connection() as conn:
            conn.execute(
                """
                INSERT INTO suspicious_segments (video_id, start_timestamp, end_timestamp, severity, reason, frame_ids)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (video["id"], 5.0, 9.0, "medium", "keyword hit", json.dumps([3, 4, 5])),
            )
            conn.commit()

        response = client.get(f"/api/videos/{video['id']}/segments", headers=api_headers)

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["video_id"] == video["id"]
        assert payload[0]["start_timestamp"] == 5.0
        assert payload[0]["end_timestamp"] == 9.0
        assert payload[0]["severity"] == "medium"
        assert payload[0]["reason"] == "keyword hit"
        assert payload[0]["frame_ids"] == [3, 4, 5]
        assert payload[0]["created_at"]

    get_settings.cache_clear()


def test_list_videos_requires_api_key(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    with TestClient(app) as client:
        unauthorized = client.get("/api/videos")
        assert unauthorized.status_code == 401

        response = client.get("/api/videos", headers=api_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    get_settings.cache_clear()


def test_process_video_endpoint_queues_task(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    captured: dict[str, object] = {}

    async def fake_schedule(video_id: int, mode: str = "two_stage", *, action: str = "process", target_stage=None):
        captured.update({
            "video_id": video_id,
            "mode": mode,
            "action": action,
            "target_stage": target_stage,
        })
        return {"id": 88, "video_id": video_id, "status": "pending", "progress": 0.0, "details": {"mode": mode}}

    with TestClient(app) as client:
        context = client.app.state.context
        video = context.repository.create_video_asset(
            {
                "filename": "demo.mp4",
                "filepath": str((tmp_path / "demo.mp4").resolve()),
                "duration": 12.0,
                "format": "mp4",
                "resolution": "1920x1080",
                "status": "completed",
            }
        )
        original_schedule = context.processing_service.schedule_video_processing
        context.processing_service.schedule_video_processing = fake_schedule
        try:
            response = client.post(f"/api/videos/{video['id']}/process", json={"mode": "deep"}, headers=api_headers)
        finally:
            context.processing_service.schedule_video_processing = original_schedule

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["task"]["id"] == 88
    assert captured == {
        "video_id": video["id"],
        "mode": "deep",
        "action": "process",
        "target_stage": None,
    }
    get_settings.cache_clear()


def test_rescan_video_endpoint_queues_target_stage(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    captured: dict[str, object] = {}

    async def fake_schedule(video_id: int, mode: str = "two_stage", *, action: str = "process", target_stage=None):
        captured.update({
            "video_id": video_id,
            "mode": mode,
            "action": action,
            "target_stage": target_stage,
        })
        return {"id": 89, "video_id": video_id, "status": "pending", "progress": 0.0, "details": {"mode": mode}}

    with TestClient(app) as client:
        context = client.app.state.context
        video = context.repository.create_video_asset(
            {
                "filename": "demo.mp4",
                "filepath": str((tmp_path / "demo.mp4").resolve()),
                "duration": 12.0,
                "format": "mp4",
                "resolution": "1920x1080",
                "status": "completed",
            }
        )
        original_schedule = context.processing_service.schedule_video_processing
        context.processing_service.schedule_video_processing = fake_schedule
        try:
            response = client.post(f"/api/videos/{video['id']}/rescan", json={"stage": "fine"}, headers=api_headers)
        finally:
            context.processing_service.schedule_video_processing = original_schedule

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["task"]["id"] == 89
    assert captured == {
        "video_id": video["id"],
        "mode": "two_stage",
        "action": "rescan",
        "target_stage": "fine",
    }
    get_settings.cache_clear()
