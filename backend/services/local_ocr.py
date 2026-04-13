from __future__ import annotations

from rapidocr_onnxruntime import RapidOCR

ocr_engine = RapidOCR()  # module-level singleton


def extract_screen_text(image_path: str) -> str:
    """
    Extract screen text from an image using RapidOCR.

    Args:
        image_path: Path to the image file.

    Returns:
        Extracted text joined by spaces, or empty string if no text found.
    """
    result, _ = ocr_engine(image_path)
    if not result:
        return ""
    return " ".join([line[1] for line in result])


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
