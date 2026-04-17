from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from backend.config import Settings
from backend.models import FrameAnalysisRecord
from backend.repositories import Repository
from backend.services.frame_dedup import deduplicate_frames
from backend.services.frame_extractor import extract_frames
from backend.services.indexer import build_search_content
from backend.services.local_ocr import (
    check_keywords,
    extract_screen_text as local_extract_screen_text,
)
from backend.services.vision_analyzer import VisionAnalyzer

ProgressCallback = Callable[[float | None, str | None, dict[str, Any] | None], Awaitable[None]]


def extract_screen_text(image_path: str) -> str:
    """Compatibility wrapper for OCR extraction used by tests and older callsites."""
    return local_extract_screen_text(image_path)


class ProcessingPipeline:
    """
    Two-stage video processing pipeline:
    - stage_coarse: Fast frame extraction + local OCR + keyword matching
    - stage_fine: Detailed vision analysis on suspicious segments
    - stage_fine_all: Full-frame vision analysis (V1 behavior)
    """

    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        vision_analyzer: VisionAnalyzer,
    ):
        self.settings = settings
        self.repository = repository
        self.vision_analyzer = vision_analyzer

    async def process_video(
        self,
        video_id: int,
        mode: str = "two_stage",
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        Main entry point for video processing.
        mode: "quick" = coarse only, "two_stage" = coarse + fine, "deep" = full fine scan
        """
        video = await asyncio.to_thread(self.repository.get_video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")

        await asyncio.to_thread(self.repository.update_video_status, video_id, "processing")

        if mode == "quick":
            await self.stage_coarse(video_id, progress_callback=progress_callback)
        elif mode == "two_stage":
            await self.stage_coarse(
                video_id,
                progress_callback=self._scale_progress_callback(progress_callback, 0.0, 0.45),
            )
            await self.stage_fine(
                video_id,
                progress_callback=self._scale_progress_callback(progress_callback, 0.45, 1.0),
            )
        elif mode == "deep":
            await self.stage_fine_all(video_id, progress_callback=progress_callback)
        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'quick', 'two_stage', or 'deep'")

        await asyncio.to_thread(self.repository.update_video_status, video_id, "completed")
        return {"video_id": video_id, "mode": mode, "status": "completed"}

    async def stage_coarse(
        self,
        video_id: int,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        Coarse scan stage:
        1. Extract frames at coarse_interval (default 10s)
        2. pHash deduplication
        3. Local OCR text extraction
        4. Keyword hit detection
        5. Mark suspicious_segments on hit
        6. Index results to FTS
        """
        video = await asyncio.to_thread(self.repository.get_video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")

        await asyncio.to_thread(self._reset_coarse_stage_data, video_id)

        frames_dir = self.settings.frames_dir_abs / f"video_{video_id:04d}_coarse"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Extract frames at coarse interval
        frames = await asyncio.to_thread(
            extract_frames,
            video["filepath"],
            str(frames_dir),
            ffmpeg_command=self.settings.ffmpeg_command,
            interval=self.settings.coarse_interval,
            max_width=self.settings.frame_max_width,
            jpeg_quality=self.settings.frame_jpeg_quality,
        )

        if not frames:
            await self._emit_progress(
                progress_callback,
                1.0,
                "coarse_completed",
                {
                    "phase": "coarse",
                    "frame_count": 0,
                    "processed_frames": 0,
                    "frames_deduped": 0,
                    "suspicious_segments": 0,
                },
            )
            return {"video_id": video_id, "stage": "coarse", "frames_extracted": 0}

        # Save frames to DB
        saved_frames = await asyncio.to_thread(self.repository.create_frames, video_id, frames)

        # pHash deduplication
        frame_paths = [f["image_path"] for f in saved_frames]
        deduped_paths = await asyncio.to_thread(
            deduplicate_frames,
            frame_paths,
            self.settings.hash_threshold,
        )
        deduped_set = set(deduped_paths)
        total_frames = max(1, len(deduped_set))

        # Get keyword sets from DB
        keyword_sets = await asyncio.to_thread(self.repository.list_keyword_sets)
        all_keywords: list[str] = []
        for ks in keyword_sets:
            all_keywords.extend(ks.get("terms", []))
        all_keywords = list(set(all_keywords))

        suspicious_count = 0
        processed_frames = 0
        await self._emit_progress(
            progress_callback,
            0.1,
            "coarse_analyzing",
            {
                "phase": "coarse",
                "frame_count": len(saved_frames),
                "processed_frames": 0,
                "frames_deduped": len(deduped_set),
                "suspicious_segments": 0,
            },
        )
        for frame in saved_frames:
            if frame["image_path"] not in deduped_set:
                continue

            # Local OCR
            ocr_text = await asyncio.to_thread(extract_screen_text, frame["image_path"])

            # Cache OCR result
            await asyncio.to_thread(self.repository.cache_frame_ocr, frame["id"], video_id, ocr_text)

            record = FrameAnalysisRecord(
                frame_id=frame["id"],
                video_id=video_id,
                raw_json={
                    "screen_text": ocr_text,
                    "application": "",
                    "url": "",
                    "operation": "",
                    "ai_tool_detected": False,
                    "ai_tool_name": "",
                    "code_visible": False,
                    "code_content_summary": "",
                    "risk_indicators": [],
                    "summary": "",
                },
                screen_text=ocr_text,
                timestamp=frame["timestamp"],
            )
            await asyncio.to_thread(self.repository.save_frame_analysis, record)
            await asyncio.to_thread(
                self.repository.upsert_fts,
                frame_id=frame["id"],
                video_id=video_id,
                timestamp=frame["timestamp"],
                content=build_search_content(record.model_dump()),
            )

            # Keyword matching
            if all_keywords:
                matched = check_keywords(ocr_text, all_keywords)
                if matched:
                    # Create suspicious segment (single frame as segment)
                    await asyncio.to_thread(
                        self.repository.create_suspicious_segment,
                        video_id,
                        frame["timestamp"],
                        frame["timestamp"],
                        "medium",
                        f"关键词命中: {', '.join(matched)}",
                        [frame["id"]],
                    )
                    suspicious_count += 1
            processed_frames += 1
            await self._emit_progress(
                progress_callback,
                0.1 + 0.9 * (processed_frames / total_frames),
                "coarse_analyzing",
                {
                    "phase": "coarse",
                    "frame_count": len(saved_frames),
                    "processed_frames": processed_frames,
                    "frames_deduped": len(deduped_set),
                    "suspicious_segments": suspicious_count,
                },
            )

        result = {
            "video_id": video_id,
            "stage": "coarse",
            "frames_extracted": len(saved_frames),
            "frames_deduped": len(deduped_set),
            "suspicious_segments": suspicious_count,
        }
        await self._emit_progress(
            progress_callback,
            1.0,
            "coarse_completed",
            {
                "phase": "coarse",
                "frame_count": len(saved_frames),
                "processed_frames": processed_frames,
                "frames_deduped": len(deduped_set),
                "suspicious_segments": suspicious_count,
            },
        )
        return result

    async def stage_fine(
        self,
        video_id: int,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        Fine scan stage.

        Supports either frame-by-frame analysis or segment-level video analysis,
        depending on Settings.fine_scan_mode.
        """
        video = await asyncio.to_thread(self.repository.get_video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")

        segments = await asyncio.to_thread(self._get_suspicious_segments, video_id)
        if not segments:
            coarse_frames = await asyncio.to_thread(self._get_coarse_frames, video_id)
            if coarse_frames:
                return await self._stage_fine_existing_frames(
                    video_id,
                    coarse_frames,
                    progress_callback,
                )
            await self._emit_progress(
                progress_callback,
                1.0,
                "fine_completed",
                {
                    "phase": "fine",
                    "fine_scan_mode": self.settings.fine_scan_mode,
                    "segments_processed": 0,
                    "frames_analyzed": 0,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            )
            return {"video_id": video_id, "stage": "fine", "segments_processed": 0}

        if self.settings.fine_scan_mode == "video":
            return await self._stage_fine_video(video, segments, video_id, progress_callback)

        return await self._stage_fine_frame(video, segments, video_id, progress_callback)

    async def _stage_fine_video(
        self,
        video: dict[str, Any],
        segments: list[dict[str, Any]],
        video_id: int,
        progress_callback: ProgressCallback | None,
    ) -> dict[str, Any]:
        """Analyze suspicious segments as short video clips and persist a preview frame per segment."""
        frames_dir = self.settings.frames_dir_abs / f"video_{video_id:04d}_video_segments"
        frames_dir.mkdir(parents=True, exist_ok=True)

        total_segments = len(segments)
        total_analyzed = 0
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        await self._emit_progress(
            progress_callback,
            0.0,
            "fine_clipping",
                {
                    "phase": "fine",
                    "fine_scan_mode": "video",
                    "segments_processed": 0,
                    "total_segments": total_segments,
                    "frames_analyzed": 0,
                    "token_usage": token_usage.copy(),
            },
        )

        for seg_idx, segment in enumerate(segments):
            start_ts = max(0.0, segment["start_timestamp"] - self.settings.suspicious_buffer)
            end_ts = segment["end_timestamp"] + self.settings.suspicious_buffer
            duration = max(1.0, end_ts - start_ts)
            mid_timestamp = (start_ts + end_ts) / 2.0

            try:
                analysis = await self.vision_analyzer.analyze_video_segment(
                    video_path=video["filepath"],
                    start_time=start_ts,
                    duration=duration,
                    max_size_mb=self.settings.video_clip_max_size_mb,
                    crf=self.settings.video_clip_crf,
                    ffmpeg_command=self.settings.ffmpeg_command,
                )
            except Exception as exc:
                # Fallback to frame mode for this segment
                await self._emit_progress(
                    progress_callback,
                    None,
                    "fine_video_fallback",
                    {
                        "phase": "fine",
                        "fine_scan_mode": "video→frame_fallback",
                        "segment_id": segment["id"],
                        "error": str(exc),
                    },
                )
                fallback_result = await self._analyze_segment_frames(video, segment, video_id)
                for key in token_usage:
                    token_usage[key] += int(fallback_result["token_usage"].get(key, 0))
                total_analyzed += fallback_result["frames_analyzed"]
                await self._emit_progress(
                    progress_callback,
                    (seg_idx + 1) / total_segments,
                    "fine_analyzing",
                    {
                        "phase": "fine",
                        "fine_scan_mode": "video→frame_fallback",
                        "segments_processed": seg_idx + 1,
                        "total_segments": total_segments,
                        "frames_analyzed": total_analyzed,
                        "token_usage": token_usage.copy(),
                    },
                )
                continue

            usage = analysis.pop("_usage", {})
            seg_start = analysis.pop("_segment_start", start_ts)
            seg_end = analysis.pop("_segment_end", end_ts)
            operation_sequence = self._normalize_operation_sequence(analysis.get("operation_sequence"))
            if operation_sequence or "operation_sequence" in analysis:
                analysis["operation_sequence"] = operation_sequence

            preview_frame = await asyncio.to_thread(
                self._extract_segment_preview_frame,
                video=video,
                video_id=video_id,
                segment_id=int(segment["id"]),
                timestamp=mid_timestamp,
                frames_dir=frames_dir,
            )
            if preview_frame is None:
                preview_frame = await asyncio.to_thread(self._get_segment_reference_frame, segment)

            if preview_frame is None:
                await self._emit_progress(
                    progress_callback,
                    None,
                    "fine_video_preview_fallback",
                    {
                        "phase": "fine",
                        "fine_scan_mode": "video→frame_fallback",
                        "segment_id": segment["id"],
                        "error": "Unable to create or reuse a representative frame for the segment.",
                    },
                )
                fallback_result = await self._analyze_segment_frames(video, segment, video_id)
                for key in token_usage:
                    token_usage[key] += int(fallback_result["token_usage"].get(key, 0))
                total_analyzed += fallback_result["frames_analyzed"]
                await self._emit_progress(
                    progress_callback,
                    (seg_idx + 1) / total_segments,
                    "fine_analyzing",
                    {
                        "phase": "fine",
                        "fine_scan_mode": "video→frame_fallback",
                        "segments_processed": seg_idx + 1,
                        "total_segments": total_segments,
                        "frames_analyzed": total_analyzed,
                        "token_usage": token_usage.copy(),
                    },
                )
                continue

            record = FrameAnalysisRecord(
                frame_id=int(preview_frame["id"]),
                video_id=video_id,
                raw_json={
                    **analysis,
                    "_fine_scan_mode": "video",
                    "_segment_start": seg_start,
                    "_segment_end": seg_end,
                },
                screen_text=analysis.get("screen_text", ""),
                application=analysis.get("application", ""),
                url=analysis.get("url", ""),
                operation=analysis.get("operation", ""),
                ai_tool_detected=bool(analysis.get("ai_tool_detected", False)),
                ai_tool_name=analysis.get("ai_tool_name", ""),
                code_visible=bool(analysis.get("code_visible", False)),
                code_content_summary=analysis.get("code_content_summary", ""),
                risk_indicators=analysis.get("risk_indicators", []),
                summary=analysis.get("summary", ""),
                timestamp=float(preview_frame["timestamp"]),
            )
            await asyncio.to_thread(self.repository.save_frame_analysis, record)
            await asyncio.to_thread(
                self.repository.upsert_fts,
                frame_id=int(preview_frame["id"]),
                video_id=video_id,
                timestamp=float(preview_frame["timestamp"]),
                content=build_search_content(record.model_dump()),
            )

            for key in token_usage:
                token_usage[key] += int(usage.get(key, 0))
            total_analyzed += 1
            await self._emit_progress(
                progress_callback,
                (seg_idx + 1) / total_segments,
                "fine_analyzing",
                {
                    "phase": "fine",
                    "fine_scan_mode": "video",
                    "segments_processed": seg_idx + 1,
                    "total_segments": total_segments,
                    "frames_analyzed": total_analyzed,
                    "token_usage": token_usage.copy(),
                },
            )

        result = {
            "video_id": video_id,
            "stage": "fine",
            "mode": "video",
            "segments_processed": total_segments,
            "frames_analyzed": total_analyzed,
            "token_usage": token_usage,
        }
        await self._emit_progress(
            progress_callback,
            1.0,
            "fine_completed",
            {
                "phase": "fine",
                "fine_scan_mode": "video",
                "segments_processed": total_segments,
                "total_segments": total_segments,
                "frames_analyzed": total_analyzed,
                "token_usage": token_usage.copy(),
            },
        )
        return result

    async def _stage_fine_frame(
        self,
        video: dict[str, Any],
        segments: list[dict[str, Any]],
        video_id: int,
        progress_callback: ProgressCallback | None,
    ) -> dict[str, Any]:
        """Frame-by-frame analysis path (original V1 behavior, FINE_SCAN_MODE=frame)."""
        frames_dir = self.settings.frames_dir_abs / f"video_{video_id:04d}_fine"
        frames_dir.mkdir(parents=True, exist_ok=True)

        total_segments = len(segments)
        total_analyzed = 0
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        await self._emit_progress(
            progress_callback,
            0.0,
            "fine_extracting",
            {
                "phase": "fine",
                "fine_scan_mode": "frame",
                "segments_processed": 0,
                "total_segments": total_segments,
                "frames_analyzed": 0,
                "token_usage": token_usage.copy(),
            },
        )

        for segment_index, segment in enumerate(segments):
            start_ts = max(0.0, segment["start_timestamp"] - self.settings.suspicious_buffer)
            end_ts = segment["end_timestamp"] + self.settings.suspicious_buffer

            temp_dir = frames_dir / f"segment_{segment['id']}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            segment_duration = end_ts - start_ts

            try:
                frames = await asyncio.to_thread(
                    extract_frames,
                    video["filepath"],
                    str(temp_dir),
                    ffmpeg_command=self.settings.ffmpeg_command,
                    interval=self.settings.fine_interval,
                    max_width=self.settings.frame_max_width,
                    jpeg_quality=self.settings.frame_jpeg_quality,
                    start_time=start_ts,
                    duration=segment_duration,
                )
            except ValueError:
                continue

            if not frames:
                continue

            saved_frames = await asyncio.to_thread(self._create_frames_in_range, video_id, frames, temp_dir)
            frame_paths = [f["image_path"] for f in saved_frames]
            deduped_paths = await asyncio.to_thread(
                deduplicate_frames,
                frame_paths,
                self.settings.hash_threshold,
            )
            deduped_set = set(deduped_paths)
            frames_to_analyze = [f for f in saved_frames if f["image_path"] in deduped_set]

            async def analyze_one(frame: dict[str, Any]) -> dict[str, Any]:
                analysis = await self.vision_analyzer.analyze_frame(frame["image_path"])
                usage = analysis.pop("_usage", {})
                record = FrameAnalysisRecord(
                    frame_id=frame["id"],
                    video_id=video_id,
                    raw_json=analysis,
                    screen_text=analysis.get("screen_text", ""),
                    application=analysis.get("application", ""),
                    url=analysis.get("url", ""),
                    operation=analysis.get("operation", ""),
                    ai_tool_detected=bool(analysis.get("ai_tool_detected", False)),
                    ai_tool_name=analysis.get("ai_tool_name", ""),
                    code_visible=bool(analysis.get("code_visible", False)),
                    code_content_summary=analysis.get("code_content_summary", ""),
                    risk_indicators=analysis.get("risk_indicators", []),
                    summary=analysis.get("summary", ""),
                    timestamp=frame["timestamp"],
                )
                await asyncio.to_thread(self.repository.save_frame_analysis, record)
                await asyncio.to_thread(
                    self.repository.upsert_fts,
                    frame_id=frame["id"],
                    video_id=video_id,
                    timestamp=frame["timestamp"],
                    content=build_search_content(record.model_dump()),
                )
                return usage

            analysis_tasks = [asyncio.create_task(analyze_one(frame)) for frame in frames_to_analyze]
            segment_total = max(1, len(frames_to_analyze))
            segment_analyzed = 0
            try:
                for completed_task in asyncio.as_completed(analysis_tasks):
                    usage = await completed_task
                    for key in token_usage:
                        token_usage[key] += int(usage.get(key, 0))
                    segment_analyzed += 1
                    total_analyzed += 1
                    await self._emit_progress(
                        progress_callback,
                        (segment_index + (segment_analyzed / segment_total)) / total_segments,
                        "fine_analyzing",
                        {
                            "phase": "fine",
                            "fine_scan_mode": "frame",
                            "segments_processed": segment_index,
                            "total_segments": total_segments,
                            "frames_analyzed": total_analyzed,
                            "token_usage": token_usage.copy(),
                        },
                    )
            except Exception:
                for task in analysis_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*analysis_tasks, return_exceptions=True)
                raise

        result = {
            "video_id": video_id,
            "stage": "fine",
            "mode": "frame",
            "segments_processed": len(segments),
            "frames_analyzed": total_analyzed,
            "token_usage": token_usage,
        }
        await self._emit_progress(
            progress_callback,
            1.0,
            "fine_completed",
            {
                "phase": "fine",
                "fine_scan_mode": "frame",
                "segments_processed": len(segments),
                "total_segments": total_segments,
                "frames_analyzed": total_analyzed,
                "token_usage": token_usage.copy(),
            },
        )
        return result

    async def _analyze_segment_frames(
        self,
        video: dict[str, Any],
        segment: dict[str, Any],
        video_id: int,
    ) -> dict[str, Any]:
        """
        Fallback: analyze a suspicious segment frame-by-frame.
        Returns token usage and frames_analyzed count.
        """
        frames_dir = self.settings.frames_dir_abs / f"video_{video_id:04d}_fine_fallback"
        frames_dir.mkdir(parents=True, exist_ok=True)

        start_ts = max(0.0, segment["start_timestamp"] - self.settings.suspicious_buffer)
        end_ts = segment["end_timestamp"] + self.settings.suspicious_buffer
        duration = end_ts - start_ts

        try:
            frames = await asyncio.to_thread(
                extract_frames,
                video["filepath"],
                str(frames_dir),
                ffmpeg_command=self.settings.ffmpeg_command,
                interval=self.settings.fine_interval,
                max_width=self.settings.frame_max_width,
                jpeg_quality=self.settings.frame_jpeg_quality,
                start_time=start_ts,
                duration=duration,
            )
        except ValueError:
            return {"frames_analyzed": 0, "token_usage": {}}

        if not frames:
            return {"frames_analyzed": 0, "token_usage": {}}

        saved_frames = await asyncio.to_thread(self._create_frames_in_range, video_id, frames, frames_dir)
        frame_paths = [f["image_path"] for f in saved_frames]
        deduped_paths = await asyncio.to_thread(
            deduplicate_frames,
            frame_paths,
            self.settings.hash_threshold,
        )
        deduped_set = set(deduped_paths)
        frames_to_analyze = [f for f in saved_frames if f["image_path"] in deduped_set]

        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for frame in frames_to_analyze:
            analysis = await self.vision_analyzer.analyze_frame(frame["image_path"])
            usage = analysis.pop("_usage", {})
            record = FrameAnalysisRecord(
                frame_id=frame["id"],
                video_id=video_id,
                raw_json=analysis,
                screen_text=analysis.get("screen_text", ""),
                application=analysis.get("application", ""),
                url=analysis.get("url", ""),
                operation=analysis.get("operation", ""),
                ai_tool_detected=bool(analysis.get("ai_tool_detected", False)),
                ai_tool_name=analysis.get("ai_tool_name", ""),
                code_visible=bool(analysis.get("code_visible", False)),
                code_content_summary=analysis.get("code_content_summary", ""),
                risk_indicators=analysis.get("risk_indicators", []),
                summary=analysis.get("summary", ""),
                timestamp=frame["timestamp"],
            )
            await asyncio.to_thread(self.repository.save_frame_analysis, record)
            await asyncio.to_thread(
                self.repository.upsert_fts,
                frame_id=frame["id"],
                video_id=video_id,
                timestamp=frame["timestamp"],
                content=build_search_content(record.model_dump()),
            )
            for key in token_usage:
                token_usage[key] += int(usage.get(key, 0))

        return {"frames_analyzed": len(frames_to_analyze), "token_usage": token_usage}

    async def _stage_fine_existing_frames(
        self,
        video_id: int,
        frames: list[dict[str, Any]],
        progress_callback: ProgressCallback | None,
    ) -> dict[str, Any]:
        """Fallback fine scan for default two_stage runs without suspicious segments."""
        if not frames:
            await self._emit_progress(
                progress_callback,
                1.0,
                "fine_completed",
                {
                    "phase": "fine",
                    "fine_scan_mode": "coarse_frame_fallback",
                    "segments_processed": 0,
                    "frames_analyzed": 0,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            )
            return {"video_id": video_id, "stage": "fine", "segments_processed": 0}

        frame_paths = [frame["image_path"] for frame in frames]
        deduped_paths = await asyncio.to_thread(
            deduplicate_frames,
            frame_paths,
            self.settings.hash_threshold,
        )
        deduped_set = set(deduped_paths)
        frames_to_analyze = [frame for frame in frames if frame["image_path"] in deduped_set]
        total_frames = max(1, len(frames_to_analyze))
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        await self._emit_progress(
            progress_callback,
            0.0,
            "fine_analyzing",
            {
                "phase": "fine",
                "fine_scan_mode": "coarse_frame_fallback",
                "segments_processed": 0,
                "total_segments": 0,
                "frames_analyzed": 0,
                "token_usage": token_usage.copy(),
            },
        )

        for index, frame in enumerate(frames_to_analyze, start=1):
            analysis = await self.vision_analyzer.analyze_frame(frame["image_path"])
            usage = analysis.pop("_usage", {})
            record = FrameAnalysisRecord(
                frame_id=frame["id"],
                video_id=video_id,
                raw_json={**analysis, "_fine_scan_mode": "coarse_frame_fallback"},
                screen_text=analysis.get("screen_text", ""),
                application=analysis.get("application", ""),
                url=analysis.get("url", ""),
                operation=analysis.get("operation", ""),
                ai_tool_detected=bool(analysis.get("ai_tool_detected", False)),
                ai_tool_name=analysis.get("ai_tool_name", ""),
                code_visible=bool(analysis.get("code_visible", False)),
                code_content_summary=analysis.get("code_content_summary", ""),
                risk_indicators=analysis.get("risk_indicators", []),
                summary=analysis.get("summary", ""),
                timestamp=frame["timestamp"],
            )
            await asyncio.to_thread(self.repository.save_frame_analysis, record)
            await asyncio.to_thread(
                self.repository.upsert_fts,
                frame_id=frame["id"],
                video_id=video_id,
                timestamp=frame["timestamp"],
                content=build_search_content(record.model_dump()),
            )
            for key in token_usage:
                token_usage[key] += int(usage.get(key, 0))
            await self._emit_progress(
                progress_callback,
                index / total_frames,
                "fine_analyzing",
                {
                    "phase": "fine",
                    "fine_scan_mode": "coarse_frame_fallback",
                    "segments_processed": 0,
                    "total_segments": 0,
                    "frames_analyzed": index,
                    "token_usage": token_usage.copy(),
                },
            )

        result = {
            "video_id": video_id,
            "stage": "fine",
            "mode": "coarse_frame_fallback",
            "segments_processed": 0,
            "frames_analyzed": len(frames_to_analyze),
            "token_usage": token_usage,
        }
        await self._emit_progress(
            progress_callback,
            1.0,
            "fine_completed",
            {
                "phase": "fine",
                "fine_scan_mode": "coarse_frame_fallback",
                "segments_processed": 0,
                "total_segments": 0,
                "frames_analyzed": len(frames_to_analyze),
                "token_usage": token_usage.copy(),
            },
        )
        return result

    async def stage_fine_all(
        self,
        video_id: int,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        Full-frame fine scan - V1 behavior.
        Extract all frames at fine_interval and run vision analysis on all.
        """
        video = await asyncio.to_thread(self.repository.get_video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")

        frames_dir = self.settings.frames_dir_abs / f"video_{video_id:04d}_fine_all"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Delete existing frames for clean slate
        await asyncio.to_thread(self.repository.delete_frames_for_video, video_id)

        # Extract frames at fine interval
        frames = await asyncio.to_thread(
            extract_frames,
            video["filepath"],
            str(frames_dir),
            ffmpeg_command=self.settings.ffmpeg_command,
            interval=self.settings.fine_interval,
            max_width=self.settings.frame_max_width,
            jpeg_quality=self.settings.frame_jpeg_quality,
        )

        if not frames:
            await self._emit_progress(
                progress_callback,
                1.0,
                "deep_completed",
                {
                    "phase": "deep",
                    "frame_count": 0,
                    "processed_frames": 0,
                    "frames_analyzed": 0,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            )
            return {"video_id": video_id, "stage": "fine_all", "frames_extracted": 0}

        saved_frames = await asyncio.to_thread(self.repository.create_frames, video_id, frames)

        # pHash deduplication
        frame_paths = [f["image_path"] for f in saved_frames]
        deduped_paths = await asyncio.to_thread(
            deduplicate_frames,
            frame_paths,
            self.settings.hash_threshold,
        )
        deduped_set = set(deduped_paths)
        total_frames = max(1, len(deduped_set))

        total_analyzed = 0
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        await self._emit_progress(
            progress_callback,
            0.1,
            "deep_analyzing",
            {
                "phase": "deep",
                "frame_count": len(saved_frames),
                "processed_frames": 0,
                "frames_analyzed": 0,
                "token_usage": token_usage.copy(),
            },
        )

        for frame in saved_frames:
            if frame["image_path"] not in deduped_set:
                continue

            analysis = await self.vision_analyzer.analyze_frame(frame["image_path"])
            usage = analysis.pop("_usage", {})
            for key in token_usage:
                token_usage[key] += int(usage.get(key, 0))

            record = FrameAnalysisRecord(
                frame_id=frame["id"],
                video_id=video_id,
                raw_json=analysis,
                screen_text=analysis.get("screen_text", ""),
                application=analysis.get("application", ""),
                url=analysis.get("url", ""),
                operation=analysis.get("operation", ""),
                ai_tool_detected=bool(analysis.get("ai_tool_detected", False)),
                ai_tool_name=analysis.get("ai_tool_name", ""),
                code_visible=bool(analysis.get("code_visible", False)),
                code_content_summary=analysis.get("code_content_summary", ""),
                risk_indicators=analysis.get("risk_indicators", []),
                summary=analysis.get("summary", ""),
                timestamp=frame["timestamp"],
            )
            await asyncio.to_thread(self.repository.save_frame_analysis, record)
            await asyncio.to_thread(
                self.repository.upsert_fts,
                frame_id=frame["id"],
                video_id=video_id,
                timestamp=frame["timestamp"],
                content=build_search_content(record.model_dump()),
            )
            total_analyzed += 1
            await self._emit_progress(
                progress_callback,
                0.1 + 0.9 * (total_analyzed / total_frames),
                "deep_analyzing",
                {
                    "phase": "deep",
                    "frame_count": len(saved_frames),
                    "processed_frames": total_analyzed,
                    "frames_analyzed": total_analyzed,
                    "token_usage": token_usage.copy(),
                },
            )

        result = {
            "video_id": video_id,
            "stage": "fine_all",
            "frames_extracted": len(saved_frames),
            "frames_analyzed": total_analyzed,
            "token_usage": token_usage,
        }
        await self._emit_progress(
            progress_callback,
            1.0,
            "deep_completed",
            {
                "phase": "deep",
                "frame_count": len(saved_frames),
                "processed_frames": total_analyzed,
                "frames_analyzed": total_analyzed,
                "token_usage": token_usage.copy(),
            },
        )
        return result

    def _cache_frame_ocr(self, frame_id: int, video_id: int, ocr_text: str) -> None:
        """Cache OCR result in frame_ocr_cache table."""
        self.repository.cache_frame_ocr(frame_id, video_id, ocr_text)

    def _upsert_suspicious_segment(
        self,
        video_id: int,
        start_timestamp: float,
        end_timestamp: float,
        severity: str,
        reason: str,
        frame_ids: list[int],
    ) -> None:
        """Insert or update a suspicious segment."""
        self.repository.create_suspicious_segment(
            video_id, start_timestamp, end_timestamp, severity, reason, frame_ids
        )

    def _get_suspicious_segments(self, video_id: int) -> list[dict[str, Any]]:
        """Get all suspicious segments for a video."""
        return self.repository.list_suspicious_segments(video_id)

    def _get_coarse_frames(self, video_id: int) -> list[dict[str, Any]]:
        coarse_dir_name = f"video_{video_id:04d}_coarse"
        frames = self.repository.get_frames_for_video(video_id)
        coarse_frames = [frame for frame in frames if coarse_dir_name in str(frame.get("image_path", ""))]
        return coarse_frames or frames

    def _reset_coarse_stage_data(self, video_id: int) -> None:
        """Clear coarse-stage artifacts so reruns do not duplicate rows or reuse stale segments."""
        self.repository.delete_frames_for_video(video_id)
        self.repository.delete_coarse_artifacts(video_id)

    def _create_frames_in_range(
        self, video_id: int, frames: list[dict[str, Any]], frame_dir: Path
    ) -> list[dict[str, Any]]:
        """Create frame records for frames extracted in a temp directory."""
        if not frames:
            return []
        return self.repository.insert_and_get_frames(video_id, frames)

    @staticmethod
    def _normalize_operation_sequence(value: Any) -> list[str]:
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _parse_segment_frame_ids(segment: dict[str, Any]) -> list[int]:
        frame_ids = segment.get("frame_ids", [])
        if isinstance(frame_ids, str):
            try:
                frame_ids = json.loads(frame_ids)
            except json.JSONDecodeError:
                return []
        if not isinstance(frame_ids, list):
            return []
        parsed: list[int] = []
        for value in frame_ids:
            try:
                parsed.append(int(value))
            except (TypeError, ValueError):
                continue
        return parsed

    def _get_segment_reference_frame(self, segment: dict[str, Any]) -> dict[str, Any] | None:
        frame_ids = self._parse_segment_frame_ids(segment)
        if not frame_ids:
            return None

        midpoint = (float(segment["start_timestamp"]) + float(segment["end_timestamp"])) / 2.0
        candidates = [self.repository.get_frame(frame_id) for frame_id in frame_ids]
        frames = [frame for frame in candidates if frame is not None]
        if not frames:
            return None
        return min(frames, key=lambda frame: abs(float(frame["timestamp"]) - midpoint))

    def _extract_segment_preview_frame(
        self,
        *,
        video: dict[str, Any],
        video_id: int,
        segment_id: int,
        timestamp: float,
        frames_dir: Path,
    ) -> dict[str, Any] | None:
        preview_dir = frames_dir / f"segment_{segment_id}"
        preview_dir.mkdir(parents=True, exist_ok=True)

        try:
            extracted = extract_frames(
                video["filepath"],
                str(preview_dir),
                ffmpeg_command=self.settings.ffmpeg_command,
                interval=1,
                max_width=self.settings.frame_max_width,
                jpeg_quality=self.settings.frame_jpeg_quality,
                start_time=max(0.0, timestamp),
                duration=1.0,
            )
        except ValueError:
            return None

        if not extracted:
            return None

        preview_frame = dict(extracted[0])
        preview_frame["timestamp"] = float(timestamp)
        preview_frame["frame_index"] = self._get_preview_frame_index(video_id, timestamp, segment_id)
        saved_frames = self._create_frames_in_range(video_id, [preview_frame], preview_dir)
        return saved_frames[0] if saved_frames else None

    def _get_preview_frame_index(self, video_id: int, timestamp: float, segment_id: int) -> int:
        max_frame_index = self.repository.get_max_frame_index(video_id)
        timestamp_index = int(round(timestamp * 1000))
        segment_index = max(0, segment_id)
        return max(max_frame_index + 1, timestamp_index, segment_index)

    @staticmethod
    def _scale_progress_callback(
        progress_callback: ProgressCallback | None,
        start: float,
        end: float,
    ) -> ProgressCallback | None:
        if progress_callback is None:
            return None

        span = max(0.0, end - start)

        async def scaled(
            progress: float | None,
            stage: str | None,
            details: dict[str, Any] | None,
        ) -> None:
            scaled_progress = None if progress is None else round(start + span * min(max(progress, 0.0), 1.0), 4)
            await progress_callback(scaled_progress, stage, details)

        return scaled

    @staticmethod
    async def _emit_progress(
        progress_callback: ProgressCallback | None,
        progress: float | None,
        stage: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if progress_callback is None:
            return
        await progress_callback(progress, stage, details)
