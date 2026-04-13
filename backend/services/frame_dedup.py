from __future__ import annotations

from PIL import Image
from pathlib import Path

import imagehash

from backend.config import get_settings


def deduplicate_frames(frame_paths: list[str], hash_threshold: int | None = None) -> list[str]:
    """
    Remove duplicate frames using pHash.

    Adjacent frames with Hamming distance <= hash_threshold are considered
    duplicates. Only the first frame in each group of duplicates is kept.

    Args:
        frame_paths: List of paths to frame images, in order.
        hash_threshold: Maximum Hamming distance for considering frames
                        duplicates. If None, uses settings.hash_threshold.

    Returns:
        List of paths to keep (deduplicated).
    """
    if hash_threshold is None:
        hash_threshold = get_settings().hash_threshold

    if not frame_paths:
        return []

    kept = [frame_paths[0]]
    with Image.open(frame_paths[0]) as img:
        prev_hash = imagehash.phash(img)

    for path in frame_paths[1:]:
        with Image.open(path) as img:
            curr_hash = imagehash.phash(img)
        if abs(curr_hash - prev_hash) > hash_threshold:
            kept.append(path)
            prev_hash = curr_hash

    return kept


def deduplicate_frames_by_dir(
    frame_dir: str | Path, hash_threshold: int | None = None
) -> list[str]:
    """
    Deduplicate all frames in a directory by sorting them and applying pHash dedup.

    Args:
        frame_dir: Directory containing frame images.
        hash_threshold: Maximum Hamming distance. Uses settings if None.

    Returns:
        List of kept frame paths.
    """
    frame_dir = Path(frame_dir)
    frame_paths = sorted(str(p) for p in frame_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    return deduplicate_frames(frame_paths, hash_threshold)
