from pathlib import Path

from backend.config import Settings, get_settings


def test_settings_defaults():
    settings = Settings()
    assert settings.ffmpeg_command == "ffmpeg"
    assert settings.ffprobe_command == "ffprobe"
    assert settings.frame_interval == 3
    assert settings.frame_max_width == 1280
    assert settings.frame_jpeg_quality == 5
    assert settings.api_concurrency == 3
    assert settings.coarse_interval == 10
    assert settings.hash_threshold == 8
    assert settings.suspicious_buffer == 15.0
    assert settings.fine_interval == 3
    assert settings.processing_mode == "two_stage"
    assert settings.api_max_retries == 6
    assert settings.api_min_interval_seconds == 1.5
    assert settings.db_path.endswith("search.db")
    assert settings.model_name == "glm-4.6v-flashx"
    assert settings.fine_scan_mode == "frame"
    assert settings.allow_any_video_paths is False


def test_get_settings_defaults_to_mock_without_api_key(monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VISION_ANALYZER_MODE", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.vision_analyzer_mode == "mock"
    get_settings.cache_clear()


def test_get_settings_preserves_explicit_mode(monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.setenv("VISION_ANALYZER_MODE", "live")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.vision_analyzer_mode == "live"
    get_settings.cache_clear()


def test_get_settings_prefers_generic_vision_env(monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "vision-key")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    monkeypatch.setenv("VISION_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    monkeypatch.setenv("MODEL_NAME", "glm-4.6v-flashx")
    monkeypatch.delenv("VISION_ANALYZER_MODE", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.api_key == "vision-key"
    assert settings.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert settings.model_name == "glm-4.6v-flashx"
    assert settings.vision_analyzer_mode == "live"
    get_settings.cache_clear()


def test_get_settings_reads_custom_ffmpeg_commands(monkeypatch):
    monkeypatch.setenv("FFMPEG_COMMAND", r"D:\tools\ffmpeg\bin\ffmpeg.exe")
    monkeypatch.setenv("FFPROBE_COMMAND", r"D:\tools\ffmpeg\bin\ffprobe.exe")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.ffmpeg_command == r"D:\tools\ffmpeg\bin\ffmpeg.exe"
    assert settings.ffprobe_command == r"D:\tools\ffmpeg\bin\ffprobe.exe"
    get_settings.cache_clear()


def test_get_settings_reads_api_throttle_values(monkeypatch):
    monkeypatch.setenv("API_MAX_RETRIES", "7")
    monkeypatch.setenv("API_MIN_INTERVAL_SECONDS", "2.5")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.api_max_retries == 7
    assert settings.api_min_interval_seconds == 2.5
    get_settings.cache_clear()


def test_get_settings_parses_allowed_video_dirs_with_os_pathsep(monkeypatch):
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "false")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", r"E:\videos;D:\data")
    get_settings.cache_clear()

    settings = get_settings()

    assert [str(path) for path in settings.allowed_video_directories] == [
        str(Path(r"E:\videos").expanduser().resolve()),
        str(Path(r"D:\data").expanduser().resolve()),
    ]
    get_settings.cache_clear()


def test_get_settings_reads_allow_any_video_paths_flag(monkeypatch):
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.allow_any_video_paths is True
    get_settings.cache_clear()


def test_get_settings_accepts_video_fine_scan_mode(monkeypatch):
    monkeypatch.setenv("FINE_SCAN_MODE", "video")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.fine_scan_mode == "video"
    finally:
        monkeypatch.delenv("FINE_SCAN_MODE", raising=False)
        get_settings.cache_clear()
