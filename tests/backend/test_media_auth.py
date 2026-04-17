from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.config import get_settings
from backend.main import app


def _configure_app_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "search.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FRAMES_DIR", str(tmp_path / "data" / "frames"))
    monkeypatch.setenv("VISION_ANALYZER_MODE", "mock")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", str(tmp_path.resolve()))
    get_settings.cache_clear()


def test_media_routes_require_api_key_header(tmp_path, monkeypatch):
    _configure_app_paths(tmp_path, monkeypatch)

    video_path = tmp_path / "demo.mp4"
    video_path.write_bytes(b"fake-video")
    frame_path = tmp_path / "frame_0001.jpg"
    Image.new("RGB", (64, 64), color=(30, 60, 90)).save(frame_path)

    with TestClient(app) as client:
        context = client.app.state.context
        video = context.repository.create_video_asset(
            {
                "filename": "demo.mp4",
                "filepath": str(video_path.resolve()),
                "duration": 12.0,
                "format": "mp4",
                "resolution": "1920x1080",
                "status": "completed",
            }
        )
        frame = context.repository.create_frames(
            video["id"],
            [
                {
                    "frame_index": 0,
                    "timestamp": 0.0,
                    "image_path": str(frame_path.resolve()),
                }
            ],
        )[0]

        unauthorized_image = client.get(f"/api/frames/{frame['id']}/image?api_key=test-api-key")
        unauthorized_video = client.get(f"/api/videos/{video['id']}/file?api_key=test-api-key")
        image_response = client.get(f"/api/frames/{frame['id']}/image", headers={"X-API-Key": "test-api-key"})
        video_response = client.get(f"/api/videos/{video['id']}/file", headers={"X-API-Key": "test-api-key"})

    assert unauthorized_image.status_code == 401
    assert unauthorized_video.status_code == 401
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/")
    assert video_response.status_code == 200
    assert video_response.headers["content-type"].startswith("video/")
