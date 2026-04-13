from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_INVALID_UNICODE_ESCAPE_RE = re.compile(r'(?<!\\)\\u(?![0-9a-fA-F]{4})')


def parse_model_json(raw_text: str) -> dict[str, Any]:
    cleaned = _strip_non_json_wrappers(raw_text.strip())
    match = _JSON_BLOCK_RE.search(cleaned)
    if match:
        cleaned = match.group(1).strip()
    cleaned = _extract_best_json_object(cleaned)

    candidate = cleaned
    last_error: json.JSONDecodeError | None = None
    for _ in range(3):
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError as exc:
            last_error = exc
            repaired = _repair_common_json_issues(candidate, exc)
            if repaired == candidate:
                raise
            candidate = repaired

    assert last_error is not None
    raise last_error


def _strip_non_json_wrappers(text: str) -> str:
    stripped = _THINK_BLOCK_RE.sub("", text)
    return stripped.strip()


def _extract_best_json_object(text: str) -> str:
    objects = _extract_top_level_json_objects(text)
    if objects:
        return objects[-1].strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end >= start:
            return text[start : end + 1]
    return text


def _repair_common_json_issues(text: str, exc: json.JSONDecodeError) -> str:
    repaired = _TRAILING_COMMA_RE.sub(r"\1", text)
    repaired = _INVALID_UNICODE_ESCAPE_RE.sub(lambda _match: "\\\\u", repaired)

    insert_at = exc.pos
    while insert_at < len(repaired) and repaired[insert_at].isspace():
        insert_at += 1

    prev_index = insert_at - 1
    while prev_index >= 0 and repaired[prev_index].isspace():
        prev_index -= 1

    if prev_index < 0 or insert_at >= len(repaired):
        return repaired

    previous_char = repaired[prev_index]
    current_char = repaired[insert_at]
    value_end_chars = {'"', "}", "]", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "e", "E", "l"}
    value_start_chars = {'"', "{", "[", "-", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "t", "f", "n"}

    if previous_char in value_end_chars and current_char in value_start_chars:
        repaired = repaired[:insert_at] + "," + repaired[insert_at:]

    repaired = _quote_unquoted_object_keys(repaired)

    return repaired


def _quote_unquoted_object_keys(text: str) -> str:
    result: list[str] = []
    stack: list[dict[str, Any]] = []
    in_string = False
    escape = False
    index = 0

    while index < len(text):
        char = text[index]

        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == "{":
            stack.append({"type": "object", "expect_key": True})
            result.append(char)
            index += 1
            continue

        if char == "[":
            stack.append({"type": "array"})
            result.append(char)
            index += 1
            continue

        if char == "}":
            if stack and stack[-1]["type"] == "object":
                stack.pop()
            result.append(char)
            index += 1
            continue

        if char == "]":
            if stack and stack[-1]["type"] == "array":
                stack.pop()
            result.append(char)
            index += 1
            continue

        if char == ":":
            if stack and stack[-1]["type"] == "object":
                stack[-1]["expect_key"] = False
            result.append(char)
            index += 1
            continue

        if char == ",":
            if stack and stack[-1]["type"] == "object":
                stack[-1]["expect_key"] = True
            result.append(char)
            index += 1
            continue

        if (
            stack
            and stack[-1]["type"] == "object"
            and stack[-1]["expect_key"]
            and _is_identifier_start(char)
        ):
            key_end = index + 1
            while key_end < len(text) and _is_identifier_continue(text[key_end]):
                key_end += 1

            colon_index = key_end
            while colon_index < len(text) and text[colon_index].isspace():
                colon_index += 1

            if colon_index < len(text) and text[colon_index] == ":":
                result.append(f'"{text[index:key_end]}"')
                index = key_end
                continue

        result.append(char)
        index += 1

    return "".join(result)


def _extract_top_level_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    in_string = False
    escape = False
    depth = 0
    start_index: int | None = None

    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue

        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start_index is not None:
                objects.append(text[start_index : index + 1])
                start_index = None

    return objects


def _is_identifier_start(char: str) -> bool:
    return char == "_" or char.isalpha()


def _is_identifier_continue(char: str) -> bool:
    return char == "_" or char.isalnum()
