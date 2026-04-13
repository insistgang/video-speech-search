from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings


@pytest.fixture(autouse=True)
def default_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    temp_root = Path(tempfile.gettempdir()).resolve()
    allowed_dirs = os.pathsep.join(
        [
            str(ROOT),
            str(ROOT / "作弊视频"),
            str(temp_root),
            "/app/videos",
        ]
    )
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("ALLOW_ANY_VIDEO_PATHS", "false")
    monkeypatch.setenv("ALLOWED_VIDEO_DIRS", allowed_dirs)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def api_headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample test image file."""
    img_path = tmp_path / "sample.jpg"
    img = Image.new("RGB", (128, 128), color=(100, 150, 200))
    img.save(img_path)
    return img_path


@pytest.fixture
def sample_images(tmp_path: Path) -> list[Path]:
    """Create multiple sample test images."""
    paths = []
    for i in range(3):
        img_path = tmp_path / f"frame_{i:04d}.jpg"
        img = Image.new("RGB", (64, 64), color=(i * 80, 50, 150))
        img.save(img_path)
        paths.append(img_path)
    return paths
