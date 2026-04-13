"""Service layer for video visual search."""

from __future__ import annotations

from backend.services.frame_dedup import deduplicate_frames, deduplicate_frames_by_dir
from backend.services.local_ocr import extract_screen_text, check_keywords
