"""Service layer for video visual search."""

from __future__ import annotations

from backend.services.frame_dedup import deduplicate_frames, deduplicate_frames_by_dir

__all__ = ["deduplicate_frames", "deduplicate_frames_by_dir"]
