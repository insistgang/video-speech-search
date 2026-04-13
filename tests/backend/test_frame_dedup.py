from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from backend.services.frame_dedup import deduplicate_frames, deduplicate_frames_by_dir


def _create_test_image(tmp_path: Path, name: str, color: tuple[int, int, int]) -> Path:
    img_path = tmp_path / name
    img = Image.new("RGB", (64, 64), color=color)
    img.save(img_path)
    return img_path


def test_deduplicate_frames_empty():
    assert deduplicate_frames([]) == []


def test_deduplicate_frames_single(tmp_path):
    frames = [str(_create_test_image(tmp_path, "frame_0001.jpg", (255, 0, 0)))]
    result = deduplicate_frames(frames)
    assert result == frames


def test_deduplicate_frames_similar_below_threshold(tmp_path):
    """Adjacent frames with very similar colors should be deduplicated."""
    frame1 = _create_test_image(tmp_path, "frame_0001.jpg", (255, 0, 0))
    frame2 = _create_test_image(tmp_path, "frame_0002.jpg", (254, 0, 0))  # nearly identical
    frame3 = _create_test_image(tmp_path, "frame_0003.jpg", (253, 0, 0))  # nearly identical

    frames = [str(frame1), str(frame2), str(frame3)]
    result = deduplicate_frames(frames, hash_threshold=4)

    # All three are similar, only first should be kept
    assert len(result) == 1
    assert result[0] == frames[0]


def test_deduplicate_frames_preserves_first_frame(tmp_path):
    """The first frame should always be preserved."""
    frame1 = _create_test_image(tmp_path, "frame_0001.jpg", (255, 0, 0))
    frame2 = _create_test_image(tmp_path, "frame_0002.jpg", (0, 255, 0))

    frames = [str(frame1), str(frame2)]
    result = deduplicate_frames(frames, hash_threshold=1)

    # First frame should always be in result
    assert frames[0] in result


def test_deduplicate_frames_returns_list_of_strings(tmp_path):
    """deduplicate_frames should return a list of string paths."""
    frame1 = _create_test_image(tmp_path, "frame_0001.jpg", (255, 0, 0))
    frame2 = _create_test_image(tmp_path, "frame_0002.jpg", (0, 255, 0))

    frames = [str(frame1), str(frame2)]
    result = deduplicate_frames(frames, hash_threshold=1)

    assert isinstance(result, list)
    assert all(isinstance(p, str) for p in result)


def test_deduplicate_frames_by_dir(tmp_path):
    """Test deduplication of frames in a directory - returns list."""
    _create_test_image(tmp_path, "frame_0001.jpg", (255, 0, 0))
    _create_test_image(tmp_path, "frame_0002.jpg", (0, 255, 0))

    result = deduplicate_frames_by_dir(tmp_path, hash_threshold=1)

    # Should return a list
    assert isinstance(result, list)
    assert len(result) >= 1


def test_deduplicate_frames_by_dir_empty_dir(tmp_path):
    """Empty directory returns empty list."""
    result = deduplicate_frames_by_dir(tmp_path, hash_threshold=4)
    assert result == []


def test_deduplicate_frames_by_dir_ignores_non_images(tmp_path):
    """Non-image files in directory are ignored."""
    _create_test_image(tmp_path, "frame_0001.jpg", (255, 0, 0))
    _create_test_image(tmp_path, "frame_0002.jpg", (254, 0, 0))
    (tmp_path / "readme.txt").write_text("not an image")

    result = deduplicate_frames_by_dir(tmp_path, hash_threshold=4)

    # Only 1 frame should be kept (images only)
    assert len(result) == 1
