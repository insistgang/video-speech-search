import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app
from backend.services.video_import import build_video_record, probe_video


def test_build_video_record_uses_original_path(tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake")
    record = build_video_record(video_path, duration=12.5, resolution="1920x1080", format_name="mp4")
    assert record["filepath"] == str(video_path.resolve())
    assert record["duration"] == 12.5


def test_probe_video_uses_utf8_subprocess(tmp_path, monkeypatch):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake")
    captured = {}

    class Completed:
        stdout = json.dumps(
            {
                "streams": [{"width": 1920, "height": 1080}],
                "format": {"duration": "12.5", "format_name": "mp4"},
            }
        )

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("backend.services.video_import.subprocess.run", fake_run)

    record = probe_video(video_path)

    assert record["resolution"] == "1920x1080"
    assert captured["command"][0] == "ffprobe"
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "replace"


def test_probe_video_supports_custom_ffprobe_command(tmp_path, monkeypatch):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake")
    captured = {}

    class Completed:
        stdout = json.dumps({"streams": [], "format": {"duration": "1.0", "format_name": "mp4"}})

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Completed()

    monkeypatch.setattr("backend.services.video_import.subprocess.run", fake_run)

    probe_video(video_path, ffprobe_command=r"D:\tools\ffmpeg\bin\ffprobe.exe")

    assert captured["command"][0] == r"D:\tools\ffmpeg\bin\ffprobe.exe"


def test_probe_video_raises_value_error_when_ffprobe_fails(tmp_path, monkeypatch):
    video_path = tmp_path / "broken.mp4"
    video_path.write_bytes(b"fake")

    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
            stderr="Invalid data found when processing input",
        )

    monkeypatch.setattr("backend.services.video_import.subprocess.run", fake_run)

    try:
        probe_video(video_path)
    except ValueError as exc:
        assert "Unable to inspect video file" in str(exc)
        assert "Invalid data found when processing input" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("probe_video should raise ValueError when ffprobe fails")


def test_probe_video_raises_friendly_error_when_ffprobe_missing(tmp_path, monkeypatch):
    video_path = tmp_path / "broken.mp4"
    video_path.write_bytes(b"fake")

    def fake_run(command, **kwargs):
        raise FileNotFoundError("missing ffprobe")

    monkeypatch.setattr("backend.services.video_import.subprocess.run", fake_run)

    try:
        probe_video(video_path, ffprobe_command="ffprobe.exe")
    except ValueError as exc:
        assert "ffprobe executable not found" in str(exc)
        assert "ffprobe.exe" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("probe_video should raise ValueError when ffprobe is missing")


def _configure_app_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "search.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FRAMES_DIR", str(tmp_path / "data" / "frames"))
    monkeypatch.setenv("VISION_ANALYZER_MODE", "mock")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", str(tmp_path.resolve()))
    get_settings.cache_clear()


def test_import_video_returns_400_for_nonexistent_file(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    with TestClient(app) as client:
        missing_path = tmp_path / "missing.mp4"
        response = client.post("/api/videos/import", json={"path": str(missing_path)}, headers=api_headers)

    assert response.status_code == 400
    assert response.json() == {"detail": f"Video file does not exist: {missing_path.resolve()}"}
    get_settings.cache_clear()


def test_import_video_returns_400_for_path_outside_allowed_directories(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)
    outside_path = Path(r"E:\outside-sample.mp4")

    with TestClient(app) as client:
        response = client.post("/api/videos/import", json={"path": str(outside_path)}, headers=api_headers)

    assert response.status_code == 400
    assert "outside allowed directories" in response.json()["detail"]
    get_settings.cache_clear()


def test_import_video_accepts_wrapping_quotes_for_existing_file(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)
    video_path = tmp_path / "quoted.mp4"
    video_path.write_bytes(b"fake")

    def fake_import_one(path: str) -> dict:
        assert path == str(video_path.resolve())
        return {
            "id": 1,
            "filename": video_path.name,
            "filepath": str(video_path.resolve()),
            "duration": 0.0,
            "format": "mp4",
            "resolution": "",
            "status": "pending",
        }

    async def fake_schedule(video_id: int, mode: str = "two_stage") -> dict:
        return {"id": 99, "video_id": video_id, "status": "pending", "progress": 0.0, "details": {}}

    with TestClient(app) as client:
        context = app.state.context
        original_import_one = context.video_import_service.import_one
        original_schedule = context.processing_service.schedule_video_processing
        context.video_import_service.import_one = fake_import_one
        context.processing_service.schedule_video_processing = fake_schedule
        try:
            response = client.post("/api/videos/import", json={"path": f'  "{video_path}"  '}, headers=api_headers)
        finally:
            context.video_import_service.import_one = original_import_one
            context.processing_service.schedule_video_processing = original_schedule

    assert response.status_code == 200
    assert response.json()["video"]["filepath"] == str(video_path.resolve())
    get_settings.cache_clear()


def test_import_folder_returns_400_for_nonexistent_folder(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)

    with TestClient(app) as client:
        missing_path = tmp_path / "missing-folder"
        response = client.post("/api/videos/import-folder", json={"folder_path": str(missing_path)}, headers=api_headers)

    assert response.status_code == 400
    assert response.json() == {"detail": f"Folder does not exist: {missing_path.resolve()}"}
    get_settings.cache_clear()


def test_import_folder_returns_400_when_path_is_file(tmp_path, monkeypatch, api_headers):
    _configure_app_paths(tmp_path, monkeypatch)
    file_path = tmp_path / "not-a-folder.mp4"
    file_path.write_bytes(b"fake")

    with TestClient(app) as client:
        response = client.post("/api/videos/import-folder", json={"folder_path": str(file_path)}, headers=api_headers)

    assert response.status_code == 400
    assert response.json() == {"detail": f"Folder path is not a directory: {file_path.resolve()}"}
    get_settings.cache_clear()
