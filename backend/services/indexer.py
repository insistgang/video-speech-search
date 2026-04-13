from __future__ import annotations

import re

import jieba


_FTS_TOKEN_RE = re.compile(r"[0-9A-Za-z_]+|[\u4e00-\u9fff]+")


def tokenize_fts_text(text: str) -> list[str]:
    if not text.strip():
        return []

    tokens: list[str] = []
    for segment in jieba.cut(text):
        normalized_segment = segment.strip()
        if not normalized_segment:
            continue
        tokens.extend(_FTS_TOKEN_RE.findall(normalized_segment))
    return tokens


def build_search_content(analysis: dict) -> str:
    raw_json = analysis.get("raw_json", {}) or {}
    operation_sequence = raw_json.get("operation_sequence", [])
    if isinstance(operation_sequence, str):
        operation_sequence_text = operation_sequence.strip()
    elif isinstance(operation_sequence, list):
        operation_sequence_text = " ".join(str(item).strip() for item in operation_sequence if str(item).strip())
    else:
        operation_sequence_text = ""

    parts = [
        analysis.get("screen_text", ""),
        analysis.get("application", ""),
        analysis.get("url", ""),
        analysis.get("operation", ""),
        operation_sequence_text,
        analysis.get("ai_tool_name", ""),
        analysis.get("code_content_summary", ""),
        " ".join(analysis.get("risk_indicators", [])),
        analysis.get("summary", ""),
    ]
    content = " ".join(part.strip() for part in parts if part and part.strip()).strip()
    return " ".join(tokenize_fts_text(content))
