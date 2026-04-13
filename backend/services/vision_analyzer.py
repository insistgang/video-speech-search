from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import email.utils
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openai import OpenAI, RateLimitError

from backend.prompts.screen_analysis import get_screen_analysis_prompt, get_video_analysis_prompt
from backend.services.video_clipper import clip_video_segment, cleanup_clip
from backend.services.json_utils import parse_model_json


class VisionAnalyzer:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        mode: str,
        cli_command: str,
        concurrency: int,
        max_retries: int = 6,
        min_interval_seconds: float = 1.5,
    ):
        self.mode = mode
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
        self.model_name = model_name
        self.cli_command = cli_command
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.max_retries = max_retries
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_started_at = 0.0

    async def analyze_frame(self, image_path: str) -> dict[str, Any]:
        if self.mode == "mock":
            return await asyncio.to_thread(self._mock_analysis, image_path)

        if self.mode == "kimi_cli":
            analyzer = self._analyze_frame_with_kimi_cli
        else:
            if self.client is None:
                raise RuntimeError("VISION_API_KEY is not configured")
            analyzer = self._analyze_frame_blocking

        async with self.semaphore:
            last_error: Exception | None = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    await self._wait_for_request_slot()
                    return await asyncio.to_thread(analyzer, image_path)
                except Exception as exc:  # pragma: no cover
                    last_error = exc
                    if attempt >= self.max_retries:
                        break
                    await asyncio.sleep(self._get_retry_delay_seconds(exc, attempt))
            assert last_error is not None
            if isinstance(last_error, RateLimitError):
                raise RuntimeError(
                    "视觉模型接口已被限流，自动重试后仍未恢复。"
                    f" 当前设置为 API_CONCURRENCY={self.concurrency}、"
                    f"API_MAX_RETRIES={self.max_retries}、"
                    f"API_MIN_INTERVAL_SECONDS={self.min_interval_seconds:g}。"
                    " 建议稍后重试，或进一步增大 FRAME_INTERVAL。"
                ) from last_error
            raise last_error

    def _analyze_frame_blocking(self, image_path: str) -> dict[str, Any]:
        image_bytes = Path(image_path).read_bytes()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                        {"type": "text", "text": get_screen_analysis_prompt()},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = completion.choices[0].message.content or "{}"
        payload = self._parse_payload(content)
        usage = getattr(completion, "usage", None)
        if usage is not None:
            payload["_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            }
        return payload

    def _analyze_frame_with_kimi_cli(self, image_path: str) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("VISION_API_KEY is required for kimi_cli mode")

        config = {
            "default_model": self.model_name,
            "providers": {
                self.model_name: {
                    "type": "kimi",
                    "base_url": self.base_url,
                    "api_key": self.api_key,
                }
            },
            "models": {
                self.model_name: {
                    "provider": self.model_name,
                    "model": self.model_name,
                    "max_context_size": 262144,
                    "capabilities": ["thinking", "image_in", "video_in"],
                }
            },
        }
        prompt = self._build_cli_prompt(image_path)
        config_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                delete=False,
            ) as handle:
                json.dump(config, handle, ensure_ascii=False)
                config_path = handle.name

            completed = subprocess.run(
                [
                    self.cli_command,
                    "--config-file",
                    config_path,
                    "--quiet",
                    "-p",
                    prompt,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={
                    **os.environ,
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1",
                },
                check=True,
            )
        finally:
            if config_path:
                try:
                    Path(config_path).unlink(missing_ok=True)
                except OSError:
                    pass

        payload = self._parse_payload(completed.stdout or "{}")
        return payload

    async def _wait_for_request_slot(self) -> None:
        if self.min_interval_seconds <= 0:
            return

        async with self._rate_limit_lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_seconds = self.min_interval_seconds - (now - self._last_request_started_at)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_started_at = loop.time()

    @staticmethod
    def _get_retry_delay_seconds(exc: Exception, attempt: int) -> float:
        if isinstance(exc, RateLimitError):
            retry_after = VisionAnalyzer._extract_retry_after_seconds(exc)
            if retry_after is not None:
                return min(300.0, max(1.0, retry_after))
            return min(120.0, 15.0 * (2 ** (attempt - 1)))
        return min(8.0, 0.5 * (2 ** (attempt - 1)))

    @staticmethod
    def _extract_retry_after_seconds(exc: RateLimitError) -> float | None:
        response = getattr(exc, "response", None)
        if response is None:
            return None

        retry_after_value = response.headers.get("retry-after")
        if not retry_after_value:
            return None

        try:
            return float(retry_after_value)
        except ValueError:
            try:
                retry_at = email.utils.parsedate_to_datetime(retry_after_value)
            except (TypeError, ValueError, IndexError):
                return None

        now = datetime.now(timezone.utc)
        return max(0.0, (retry_at - now).total_seconds())

    @staticmethod
    def _build_cli_prompt(image_path: str) -> str:
        return f"""请读取本地图片文件：{image_path}
把它当作一段无声屏幕录制视频中的单帧画面来分析。

{get_screen_analysis_prompt()}

额外要求：
1. 只返回严格 JSON，对象外不要有任何解释或 markdown 代码块。
2. `summary`、`operation`、`code_content_summary`、`risk_indicators` 尽量使用中文表述。
3. `risk_indicators` 返回中文短语数组，不要使用英文代码、snake_case 或占位词。
4. 产品名、网站名、模型名、IDE 名称可以保留原文。
5. 如果未发现 AI 工具，`ai_tool_detected` 返回 false，`ai_tool_name` 返回空字符串。"""

    @staticmethod
    def _parse_payload(content: str) -> dict[str, Any]:
        try:
            return parse_model_json(content)
        except json.JSONDecodeError as exc:
            snippet = VisionAnalyzer._build_invalid_json_snippet(content, exc.pos)
            raise ValueError(
                f"Model returned invalid JSON after repair attempts: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno}). Around: {snippet}"
            ) from exc

    @staticmethod
    def _build_invalid_json_snippet(content: str, position: int, radius: int = 80) -> str:
        start = max(0, position - radius)
        end = min(len(content), position + radius)
        snippet = content[start:end].replace("\r", "\\r").replace("\n", "\\n")
        return snippet

    @staticmethod
    def _mock_analysis(image_path: str) -> dict[str, Any]:
        frame_name = Path(image_path).stem.replace("_", " ")
        return {
            "screen_text": f"{frame_name} 的模拟 OCR 内容",
            "application": "模拟审查界面",
            "url": "",
            "operation": "用于本地流程验证的模拟分析结果",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": ["模拟分析结果"],
            "summary": f"{frame_name} 的模拟分析结果",
            "_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    # -------------------------------------------------------------------------
    # Video segment analysis (new in V2)
    # -------------------------------------------------------------------------

    async def analyze_video_segment(
        self,
        video_path: str,
        start_time: float,
        duration: float,
        max_size_mb: int = 20,
        crf: int = 28,
        ffmpeg_command: str = "ffmpeg",
    ) -> dict[str, Any]:
        """
        Analyze a video segment in a single API call using video_url.

        Args:
            video_path: Path to the source video file.
            start_time: Start time in seconds for the segment to analyze.
            duration: Duration of the segment in seconds.
            max_size_mb: Maximum clip file size before re-encoding at higher CRF.
            crf: Initial H.264 CRF (lower = better quality, larger file).

        Returns:
            Parsed JSON analysis result dict.

        Raises:
            RuntimeError: When no API key is configured or mode is unsupported.
            ValueError: When video clipping fails.
        """
        if self.mode == "mock":
            return await asyncio.to_thread(
                self._mock_video_segment_analysis,
                video_path,
                start_time,
                duration,
            )

        if self.mode != "live":
            raise RuntimeError(
                f"Video segment analysis is only supported in 'live' mode "
                f"(current mode: '{self.mode}'). Use FINE_SCAN_MODE=frame for CLI-based modes."
            )

        if self.client is None:
            raise RuntimeError("VISION_API_KEY is not configured")

        async with self.semaphore:
            last_error: Exception | None = None
            for attempt in range(1, self.max_retries + 1):
                clip_path = ""
                try:
                    clip_path = await asyncio.to_thread(
                        clip_video_segment,
                        video_path=video_path,
                        start_time=start_time,
                        duration=duration,
                        max_size_mb=max_size_mb,
                        crf=crf,
                        ffmpeg_command=ffmpeg_command,
                    )
                    await self._wait_for_request_slot()
                    return await asyncio.to_thread(
                        self._analyze_video_segment_blocking,
                        clip_path,
                        start_time,
                        duration,
                    )
                except Exception as exc:  # pragma: no cover
                    last_error = exc
                    if attempt >= self.max_retries:
                        break
                    await asyncio.sleep(self._get_retry_delay_seconds(exc, attempt))
                finally:
                    if clip_path:
                        cleanup_clip(clip_path)

        assert last_error is not None
        if isinstance(last_error, RateLimitError):
            raise RuntimeError(
                "视觉模型接口已被限流，自动重试后仍未恢复。"
                f" 当前设置为 API_CONCURRENCY={self.concurrency}、"
                f"API_MAX_RETRIES={self.max_retries}、"
                f"API_MIN_INTERVAL_SECONDS={self.min_interval_seconds:g}。"
                " 建议稍后重试，或缩短单次视频片段时长。"
            ) from last_error
        raise last_error

    def _analyze_video_segment_blocking(
        self, clip_path: str, start_time: float, duration: float
    ) -> dict[str, Any]:
        """Send a video clip to the vision API (blocking, to be run in a thread pool)."""
        video_bytes = Path(clip_path).read_bytes()
        video_base64 = base64.b64encode(video_bytes).decode("utf-8")

        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": f"data:video/mp4;base64,{video_base64}"},
                        },
                        {"type": "text", "text": get_video_analysis_prompt()},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = completion.choices[0].message.content or "{}"
        payload = self._parse_payload(content)
        usage = getattr(completion, "usage", None)
        if usage is not None:
            payload["_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            }
        # Attach segment metadata so the caller knows what time range this covers
        payload["_segment_start"] = start_time
        payload["_segment_end"] = start_time + duration
        return payload

    async def analyze_video_segment_batch(
        self,
        segments: list[dict[str, Any]],
        concurrency: int = 3,
        max_size_mb: int = 20,
        crf: int = 28,
    ) -> list[dict[str, Any]]:
        """
        Analyze multiple video segments concurrently.

        Args:
            segments: List of dicts, each with:
                - video_path (str): Source video path
                - start_time (float): Segment start in seconds
                - end_time (float): Segment end in seconds
                - segment_id (str | None): Optional identifier
            concurrency: Max concurrent API calls (semaphore limit).
            max_size_mb: Passed through to clip_video_segment.
            crf: Passed through to clip_video_segment.

        Returns:
            List of analysis result dicts, in the same order as input segments.
        """
        sem = asyncio.Semaphore(concurrency)

        async def analyze_one(seg: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                try:
                    return await self.analyze_video_segment(
                        video_path=seg["video_path"],
                        start_time=seg["start_time"],
                        duration=seg["end_time"] - seg["start_time"],
                        max_size_mb=max_size_mb,
                        crf=crf,
                    )
                except Exception as exc:
                    # Fallback: return an error payload so the batch doesn't crash
                    return {
                        "error": str(exc),
                        "segment_id": seg.get("segment_id"),
                        "start_time": seg["start_time"],
                        "end_time": seg["end_time"],
                    }

        return await asyncio.gather(*[analyze_one(seg) for seg in segments])

    @staticmethod
    def _mock_video_segment_analysis(
        video_path: str,
        start_time: float,
        duration: float,
    ) -> dict[str, Any]:
        """Mock analysis for a video segment (used when mode='mock')."""
        video_name = Path(video_path).stem.replace("_", " ")
        return {
            "screen_text": f"{video_name} 在 t={start_time:.1f}s 的模拟视频内容",
            "application": "模拟视频审查",
            "url": "",
            "operation": "用于本地流程验证的模拟视频分析",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "code_visible": False,
            "code_content_summary": "",
            "risk_indicators": ["模拟分析结果"],
            "operation_sequence": ["步骤1：打开应用", "步骤2：执行操作", "步骤3：验证结果"],
            "summary": f"{video_name} 的模拟视频分析结果",
            "_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "_segment_start": start_time,
            "_segment_end": start_time + duration,
        }
