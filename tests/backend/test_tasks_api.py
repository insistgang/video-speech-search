from fastapi.testclient import TestClient

from backend.api.tasks import resolve_retry_mode
from backend.config import get_settings
from backend.main import app, merge_task_progress_details


def test_tasks_include_video_metadata(tmp_path, monkeypatch, api_headers):
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
                "status": "pending",
            }
        )
        context.repository.create_task(video["id"], "video_process", details={"frame_count": 2})

        response = client.get("/api/tasks", headers=api_headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["video_filename"] == "demo.mp4"
        assert payload[0]["video_status"] == "pending"

    get_settings.cache_clear()


def test_tasks_support_active_only_and_limit(tmp_path, monkeypatch, api_headers):
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
                "status": "pending",
            }
        )
        context.repository.create_task(video["id"], "video_process", status="completed")
        context.repository.create_task(video["id"], "video_process", status="running")
        context.repository.create_task(video["id"], "video_process", status="pending")

        active_response = client.get("/api/tasks?active_only=true", headers=api_headers)
        limited_response = client.get("/api/tasks?limit=2", headers=api_headers)

        assert active_response.status_code == 200
        assert [task["status"] for task in active_response.json()] == ["pending", "running"]
        assert limited_response.status_code == 200
        assert len(limited_response.json()) == 2

    get_settings.cache_clear()


def test_retry_task_preserves_original_action_and_target_stage(tmp_path, monkeypatch, api_headers):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "search.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FRAMES_DIR", str(tmp_path / "data" / "frames"))
    monkeypatch.setenv("VISION_ANALYZER_MODE", "mock")
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    async def fake_schedule(video_id: int, mode: str = "two_stage", *, action: str = "process", target_stage=None):
        captured.update({
            "video_id": video_id,
            "mode": mode,
            "action": action,
            "target_stage": target_stage,
        })
        return {"id": 99, "video_id": video_id, "status": "pending", "progress": 0.0, "details": {"mode": mode}}

    with TestClient(app) as client:
        context = client.app.state.context
        video = context.repository.create_video_asset(
            {
                "filename": "demo.mp4",
                "filepath": str((tmp_path / "demo.mp4").resolve()),
                "duration": 12.0,
                "format": "mp4",
                "resolution": "1920x1080",
                "status": "pending",
            }
        )
        task = context.repository.create_task(
            video["id"],
            "video_process",
            status="failed",
            details={"action": "rescan", "mode": "two_stage", "target_stage": "fine", "stage": "failed"},
        )
        original_schedule = context.processing_service.schedule_video_processing
        context.processing_service.schedule_video_processing = fake_schedule
        try:
            response = client.post(f"/api/tasks/{task['id']}/retry", headers=api_headers)
        finally:
            context.processing_service.schedule_video_processing = original_schedule

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert captured == {
        "video_id": video["id"],
        "mode": "two_stage",
        "action": "rescan",
        "target_stage": "fine",
    }

    get_settings.cache_clear()


def test_retry_task_recovers_from_legacy_frame_mode_details():
    details = {"action": "process", "mode": "frame", "stage": "failed", "phase": "fine"}

    assert resolve_retry_mode(details) == "two_stage"


def test_merge_task_progress_details_preserves_requested_processing_mode():
    current = {"mode": "two_stage", "requested_mode": "two_stage", "action": "process", "queue_job_id": 7}
    updates = {"mode": "frame", "fine_scan_mode": "frame", "processed_frames": 3}

    merged = merge_task_progress_details(current, updates)

    assert merged["mode"] == "two_stage"
    assert merged["requested_mode"] == "two_stage"
    assert merged["fine_scan_mode"] == "frame"
    assert merged["processed_frames"] == 3
