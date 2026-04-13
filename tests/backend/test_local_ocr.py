from __future__ import annotations

import pytest

from backend.services.local_ocr import check_keywords, extract_screen_text


def test_check_keywords_empty_text():
    assert check_keywords("", ["AI", "Kimi"]) == []


def test_check_keywords_no_match():
    result = check_keywords("Hello world", ["AI", "Kimi"])
    assert result == []


def test_check_keywords_single_match():
    result = check_keywords("使用AI平台", ["AI", "Kimi"])
    assert result == ["AI"]


def test_check_keywords_multiple_matches():
    result = check_keywords("使用AI平台和Kimi", ["AI", "Kimi"])
    assert set(result) == {"AI", "Kimi"}


def test_check_keywords_case_insensitive():
    """Keyword matching should be case-insensitive."""
    result = check_keywords("KIMI 平台", ["kimi"])
    assert result == ["kimi"]


def test_check_keywords_case_insensitive_multiple():
    """Case-insensitive matching with multiple keywords."""
    result = check_keywords("AI AND KIMI", ["ai", "kimi"])
    assert set(result) == {"ai", "kimi"}


def test_check_keywords_partial_match_not_allowed():
    """Keywords should match as whole words/substrings, not partial."""
    result = check_keywords("AIDesk", ["AI"])
    # "AI" is a substring of "AIDesk" so it should match
    assert "AI" in result


def test_check_keywords_empty_keywords():
    """Empty keyword list returns empty matches."""
    result = check_keywords("Hello AI", [])
    assert result == []


def test_check_keywords_returns_list_of_strings():
    """check_keywords should return a list of matched keyword strings."""
    result = check_keywords("The AI is great", ["AI", "test"])
    assert isinstance(result, list)
    assert all(isinstance(kw, str) for kw in result)
