import asyncio
import json
from json import JSONDecodeError
from pathlib import Path

import httpx
from openai import RateLimitError

from backend.services.vision_analyzer import VisionAnalyzer


def test_kimi_cli_mode_parses_json_and_cleans_temp_config(tmp_path, monkeypatch):
    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpg")
    captured = {}

    class Completed:
        stdout = json.dumps(
            {
                "screen_text": "ChatGPT window",
                "application": "ChatGPT",
                "url": "",
                "operation": "asking for help",
                "ai_tool_detected": True,
                "ai_tool_name": "ChatGPT",
                "code_visible": False,
                "code_content_summary": "",
                "risk_indicators": ["ai usage"],
                "summary": "ChatGPT visible",
            }
        )

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        config_path = Path(command[2])
        captured["config_exists_during_run"] = config_path.exists()
        captured["config_payload"] = json.loads(config_path.read_text(encoding="utf-8"))
        return Completed()

    monkeypatch.setattr("backend.services.vision_analyzer.subprocess.run", fake_run)

    analyzer = VisionAnalyzer(
        api_key="test-key",
        base_url="https://api.kimi.com/coding/v1",
        model_name="kimi-for-coding",
        mode="kimi_cli",
        cli_command="kimi",
        concurrency=1,
    )

    result = asyncio.run(analyzer.analyze_frame(str(image_path)))

    assert result["application"] == "ChatGPT"
    assert captured["command"][0] == "kimi"
    assert captured["config_exists_during_run"] is True
    assert captured["config_payload"]["providers"]["kimi-for-coding"]["api_key"] == "test-key"
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["kwargs"]["env"]["PYTHONUTF8"] == "1"


def test_build_cli_prompt_includes_image_path(tmp_path):
    image_path = tmp_path / "frame.jpg"
    prompt = VisionAnalyzer._build_cli_prompt(str(image_path))
    assert str(image_path) in prompt
    assert "只返回严格 JSON" in prompt


def test_kimi_cli_mode_retries_on_invalid_json(tmp_path, monkeypatch):
    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpg")
    attempts = {"count": 0}

    def fake_cli(_image_path: str):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise JSONDecodeError("bad json", '{"x"', 4)
        return {
            "screen_text": "ok",
            "application": "ChatGPT",
            "url": "",
            "operation": "ok",
            "ai_tool_detected": True,
            "ai_tool_name": "ChatGPT",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": [],
            "summary": "ok",
        }

    analyzer = VisionAnalyzer(
        api_key="test-key",
        base_url="https://api.kimi.com/coding/v1",
        model_name="kimi-for-coding",
        mode="kimi_cli",
        cli_command="kimi",
        concurrency=1,
        max_retries=2,
    )
    monkeypatch.setattr(analyzer, "_analyze_frame_with_kimi_cli", fake_cli)

    result = asyncio.run(analyzer.analyze_frame(str(image_path)))

    assert result["summary"] == "ok"
    assert attempts["count"] == 2


def test_parse_payload_raises_readable_error_for_invalid_json():
    payload = '{"summary": "ok", broken: [}'

    try:
        VisionAnalyzer._parse_payload(payload)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid model JSON")

    assert "Model returned invalid JSON after repair attempts" in message
    assert "Around:" in message
    assert "broken" in message


def test_live_mode_uses_longer_backoff_for_rate_limit(tmp_path, monkeypatch):
    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpg")
    attempts = {"count": 0}
    sleep_delays: list[float] = []

    def fake_blocking(_image_path: str):
        attempts["count"] += 1
        if attempts["count"] < 3:
            request = httpx.Request("POST", "https://example.com/v1/chat/completions")
            response = httpx.Response(
                429,
                request=request,
                json={"error": {"code": "1302", "message": "rate limited"}},
            )
            raise RateLimitError("rate limited", response=response, body={"error": {"code": "1302"}})
        return {
            "screen_text": "ok",
            "application": "ChatGPT",
            "url": "",
            "operation": "ok",
            "ai_tool_detected": True,
            "ai_tool_name": "ChatGPT",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": [],
            "summary": "ok",
        }

    async def fake_sleep(delay: float):
        sleep_delays.append(delay)

    analyzer = VisionAnalyzer(
        api_key="test-key",
        base_url="https://example.com/v1",
        model_name="vision-model",
        mode="live",
        cli_command="kimi",
        concurrency=1,
        max_retries=3,
        min_interval_seconds=0,
    )
    monkeypatch.setattr(analyzer, "_analyze_frame_blocking", fake_blocking)
    monkeypatch.setattr("backend.services.vision_analyzer.asyncio.sleep", fake_sleep)

    result = asyncio.run(analyzer.analyze_frame(str(image_path)))

    assert result["summary"] == "ok"
    assert attempts["count"] == 3
    assert sleep_delays == [15.0, 30.0]


def test_live_mode_raises_readable_error_after_rate_limit_retries_exhausted(tmp_path, monkeypatch):
    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpg")

    def always_rate_limited(_image_path: str):
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(
            429,
            request=request,
            json={"error": {"code": "1302", "message": "rate limited"}},
        )
        raise RateLimitError("rate limited", response=response, body={"error": {"code": "1302"}})

    async def fake_sleep(_delay: float):
        return None

    analyzer = VisionAnalyzer(
        api_key="test-key",
        base_url="https://example.com/v1",
        model_name="vision-model",
        mode="live",
        cli_command="kimi",
        concurrency=1,
        max_retries=2,
        min_interval_seconds=0,
    )
    monkeypatch.setattr(analyzer, "_analyze_frame_blocking", always_rate_limited)
    monkeypatch.setattr("backend.services.vision_analyzer.asyncio.sleep", fake_sleep)

    try:
        asyncio.run(analyzer.analyze_frame(str(image_path)))
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected RuntimeError after repeated rate limiting")

    assert "视觉模型接口已被限流" in message
    assert "API_MAX_RETRIES=2" in message


def test_live_video_segment_analysis_uses_blocking_worker_and_cleans_up_clip(monkeypatch):
    captured: dict[str, object] = {}

    def fake_clip_video_segment(**kwargs):
        captured["clip_kwargs"] = kwargs
        return "segment.mp4"

    def fake_cleanup_clip(path: str):
        captured["cleaned_clip"] = path

    def fake_blocking(clip_path: str, start_time: float, duration: float):
        captured["blocking_args"] = (clip_path, start_time, duration)
        return {"summary": "ok"}

    analyzer = VisionAnalyzer(
        api_key="test-key",
        base_url="https://example.com/v1",
        model_name="vision-model",
        mode="live",
        cli_command="kimi",
        concurrency=1,
        max_retries=1,
        min_interval_seconds=0,
    )
    monkeypatch.setattr("backend.services.vision_analyzer.clip_video_segment", fake_clip_video_segment)
    monkeypatch.setattr("backend.services.vision_analyzer.cleanup_clip", fake_cleanup_clip)
    monkeypatch.setattr(analyzer, "_analyze_video_segment_blocking", fake_blocking)

    result = asyncio.run(
        analyzer.analyze_video_segment(
            video_path="demo.mp4",
            start_time=12.0,
            duration=4.0,
            max_size_mb=18,
            crf=30,
            ffmpeg_command="ffmpeg",
        )
    )

    assert result["summary"] == "ok"
    assert captured["clip_kwargs"] == {
        "video_path": "demo.mp4",
        "start_time": 12.0,
        "duration": 4.0,
        "max_size_mb": 18,
        "crf": 30,
        "ffmpeg_command": "ffmpeg",
    }
    assert captured["blocking_args"] == ("segment.mp4", 12.0, 4.0)
    assert captured["cleaned_clip"] == "segment.mp4"
