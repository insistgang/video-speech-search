from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app
from backend.models import FrameAnalysisRecord


def test_keyword_scan_dedupes_results(tmp_path, monkeypatch, api_headers):
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
        frames = context.repository.create_frames(
            video["id"],
            [
                {
                    "frame_index": 0,
                    "timestamp": 0.0,
                    "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
                }
            ],
        )
        context.repository.save_frame_analysis(
            FrameAnalysisRecord(
                frame_id=frames[0]["id"],
                video_id=video["id"],
                raw_json={"summary": "ChatGPT and Bedrock visible"},
                screen_text="ChatGPT and AWS Bedrock visible",
                application="Browser",
                url="",
                operation="testing multiple tools",
                ai_tool_detected=True,
                ai_tool_name="ChatGPT",
                code_visible=False,
                code_content_summary="",
                risk_indicators=["ai platform usage"],
                summary="ChatGPT and Bedrock in one frame",
                timestamp=0.0,
            )
        )
        context.repository.upsert_fts(
            frame_id=frames[0]["id"],
            video_id=video["id"],
            timestamp=0.0,
            content="ChatGPT AWS Bedrock visible in the same frame",
        )
        keyword_set = context.repository.upsert_keyword_set(
            name="AI tools",
            category="tool",
            terms=["ChatGPT", "Bedrock"],
        )

        response = client.post(f"/api/keywords/{keyword_set['id']}/scan", headers=api_headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_hits"] == 1
        assert sorted(payload["results"][0]["matched_terms"]) == ["Bedrock", "ChatGPT"]

    get_settings.cache_clear()
