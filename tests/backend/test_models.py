import shutil
from uuid import uuid4
from pathlib import Path

from backend.config import get_settings
from backend.models import get_allowed_video_directories, normalize_path, resolve_path_input


def test_models_read_allowed_video_dirs_from_settings(monkeypatch):
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "false")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", r"E:\videos;D:\data")
    get_settings.cache_clear()

    directories = get_allowed_video_directories()

    assert directories == [
        Path(r"E:\videos").expanduser().resolve(),
        Path(r"D:\data").expanduser().resolve(),
    ]
    get_settings.cache_clear()


def test_normalize_path_strips_wrapping_quotes_and_whitespace(monkeypatch):
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "false")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", r"E:\videos")
    get_settings.cache_clear()

    try:
        quoted_path = '  "E:\\videos\\sample.mp4"  '
        assert normalize_path(quoted_path) == str(Path(r"E:\videos\sample.mp4").resolve())
    finally:
        get_settings.cache_clear()


def test_resolve_path_input_allows_any_absolute_path_when_flag_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "true")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", r"E:\videos")
    get_settings.cache_clear()

    try:
        assert resolve_path_input(r"D:\anywhere\sample.mp4") == Path(r"D:\anywhere\sample.mp4").resolve()
    finally:
        get_settings.cache_clear()


def test_resolve_path_input_matches_hidden_unicode_whitespace_segments(monkeypatch):
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "true")
    get_settings.cache_clear()

    root = Path.cwd() / f"codex_path_test_{uuid4().hex[:8]}"
    actual_dir = root / "八段锦详细解说全套教程 \u200b\u200b\u200b"
    actual_dir.mkdir(parents=True, exist_ok=True)
    actual_file = actual_dir / "八段锦.mp4"
    actual_file.write_bytes(b"fake")

    try:
        requested = root / "八段锦详细解说全套教程" / "八段锦.mp4"
        assert resolve_path_input(requested) == actual_file.resolve()
    finally:
        shutil.rmtree(root, ignore_errors=True)
        get_settings.cache_clear()
