from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app


def test_stats_endpoint_returns_counts(tmp_path, monkeypatch, api_headers):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "search.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FRAMES_DIR", str(tmp_path / "data" / "frames"))
    monkeypatch.setenv("VISION_ANALYZER_MODE", "mock")
    get_settings.cache_clear()

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
        context.repository.create_task(video["id"], "video_process", status="completed")
        context.repository.create_task(video["id"], "video_process", status="failed")

        response = client.get("/api/stats", headers=api_headers)

        assert response.status_code == 200
        assert response.json() == {
            "total_videos": 1,
            "total_frames": 0,
            "total_tasks": 2,
            "completed_tasks": 1,
            "failed_tasks": 1,
        }

    get_settings.cache_clear()
