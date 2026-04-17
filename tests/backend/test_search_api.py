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


def test_search_result_detail_returns_windowed_frames(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    with TestClient(app) as client:
        context = client.app.state.context
        video = context.repository.create_video_asset(
            {
                "filename": "demo.mp4",
                "filepath": str((tmp_path / "demo.mp4").resolve()),
                "duration": 120.0,
                "format": "mp4",
                "resolution": "1920x1080",
                "status": "completed",
            }
        )

        frames = context.repository.create_frames(
            video["id"],
            [
                {
                    "frame_index": index,
                    "timestamp": float(index * 3),
                    "image_path": str((tmp_path / f"frame_{index:04d}.jpg").resolve()),
                }
                for index in range(130)
            ],
        )

        anchor_frame = frames[65]
        response = client.get(f"/api/search/results/{anchor_frame['id']}", headers=api_headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["frame"]["id"] == anchor_frame["id"]
        assert payload["total_frames"] == 130
        assert len(payload["frames"]) == 121
        assert payload["frames"][0]["id"] == frames[5]["id"]
        assert payload["frames"][-1]["id"] == frames[125]["id"]

    get_settings.cache_clear()
