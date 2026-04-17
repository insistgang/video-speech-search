from __future__ import annotations

import logging
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class MockOCR:
    """Fallback OCR implementation that never raises and returns empty text."""

    def extract_screen_text(self, image_path: str) -> str:
        return ""


class LocalOCR:
    """Lazy-loaded OCR wrapper with graceful fallback to MockOCR."""

    def __init__(self) -> None:
        self._backend: Any | None = None
        self._fallback = MockOCR()
        self._lock = Lock()
        self._initialized = False

    def _get_backend(self) -> Any | MockOCR:
        if self._initialized:
            return self._backend if self._backend is not None else self._fallback

        with self._lock:
            if self._initialized:
                return self._backend if self._backend is not None else self._fallback

            try:
                from rapidocr_onnxruntime import RapidOCR

                self._backend = RapidOCR()
            except Exception as exc:  # pragma: no cover - depends on local runtime ABI
                self._backend = None
                logger.warning(
                    "RapidOCR initialization failed; falling back to MockOCR. "
                    "OCR will return empty text. Error: %s",
                    exc,
                )
            finally:
                self._initialized = True

        return self._backend if self._backend is not None else self._fallback

    def extract_screen_text(self, image_path: str) -> str:
        backend = self._get_backend()
        if isinstance(backend, MockOCR):
            return backend.extract_screen_text(image_path)

        result, _ = backend(image_path)
        if not result:
            return ""
        return " ".join(str(line[1]) for line in result)


_local_ocr: LocalOCR | None = None
_local_ocr_lock = Lock()


def get_local_ocr() -> LocalOCR:
    global _local_ocr

    if _local_ocr is not None:
        return _local_ocr

    with _local_ocr_lock:
        if _local_ocr is None:
            _local_ocr = LocalOCR()
    return _local_ocr


def extract_screen_text(image_path: str) -> str:
    """
    Extract screen text from an image using a lazily initialized OCR backend.

    Args:
        image_path: Path to the image file.

    Returns:
        Extracted text joined by spaces, or empty string if no text found.
    """
    return get_local_ocr().extract_screen_text(image_path)


def check_keywords(text: str, keywords: list[str]) -> list[str]:
    """
    Check which keywords appear in the given text (case-insensitive).

    Args:
        text: The text to search in.
        keywords: List of keywords to look for.

    Returns:
        List of keywords that were found in the text.
    """
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]
