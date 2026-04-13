from backend.services.json_utils import parse_model_json


def test_parse_model_json_strips_markdown_fences():
    payload = "```json\n{\"summary\": \"ok\"}\n```"
    result = parse_model_json(payload)
    assert result["summary"] == "ok"


def test_parse_model_json_allows_control_characters_inside_strings():
    payload = '{"summary": "line1\nline2", "application": "ChatGPT"}'
    result = parse_model_json(payload)
    assert result["summary"] == "line1\nline2"


def test_parse_model_json_repairs_missing_comma_between_fields():
    payload = '{"summary": "ok"\n"application": "ChatGPT"}'
    result = parse_model_json(payload)
    assert result["application"] == "ChatGPT"


def test_parse_model_json_repairs_trailing_commas():
    payload = '{"summary": "ok", "risk_indicators": [],}'
    result = parse_model_json(payload)
    assert result["summary"] == "ok"


def test_parse_model_json_repairs_unquoted_property_names():
    payload = '{screen_text: "hello", application: "ChatGPT", ai_tool_detected: true, summary: "ok"}'
    result = parse_model_json(payload)
    assert result["screen_text"] == "hello"
    assert result["application"] == "ChatGPT"
    assert result["ai_tool_detected"] is True


def test_parse_model_json_repairs_nested_unquoted_property_names():
    payload = '{"summary": "ok", "raw": [{screen_text: "hello", risk_indicators: []}]}'
    result = parse_model_json(payload)
    assert result["raw"][0]["screen_text"] == "hello"


def test_parse_model_json_uses_last_json_object_after_think_block():
    payload = (
        '<think>{"summary":"draft"}</think>\n'
        '{"summary":"final","application":"AWS Console"}'
    )
    result = parse_model_json(payload)
    assert result["summary"] == "final"
    assert result["application"] == "AWS Console"


def test_parse_model_json_uses_last_json_object_when_extra_data_precedes_final_payload():
    payload = (
        '{"summary":"draft"}\n'
        "</think>\n"
        '{screen_text: "Amazon Q", application: "AWS Console", summary: "final"}'
    )
    result = parse_model_json(payload)
    assert result["screen_text"] == "Amazon Q"
    assert result["summary"] == "final"


def test_parse_model_json_repairs_invalid_unicode_escape_sequences():
    payload = '{"summary":"30 \\u2630 \\u26 escape","application":"ChatGPT"}'
    result = parse_model_json(payload)
    assert result["summary"] == "30 \u2630 \\u26 escape"
    assert result["application"] == "ChatGPT"
