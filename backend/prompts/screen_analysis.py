import os
from pathlib import Path

_DEFAULT_PROMPT = """你是一个屏幕录制视频内容分析专家。请分析这个屏幕截图，严格返回 JSON，不要返回 markdown 代码块，也不要返回其他解释。

{
  "screen_text": "画面中可见的所有文字内容（尽可能完整）",
  "application": "当前使用的应用程序或网站名称",
  "url": "如果可见，当前浏览器地址栏的 URL，否则为空字符串",
  "operation": "用户正在执行的操作描述",
  "ai_tool_detected": true,
  "ai_tool_name": "如检测到 AI 工具，给出工具名称，否则为空字符串",
  "code_visible": false,
  "code_content_summary": "如可见代码，给出代码片段摘要，否则为空字符串",
  "risk_indicators": ["检测到的可疑行为列表，如果没有则为空数组"],
  "summary": "一句话总结画面内容"
}

重点关注：
1. 使用 AI 对话平台，如 ChatGPT、Claude、Kimi、文心一言、通义千问
2. 使用云平台 AI 服务，如 AWS Bedrock、Azure OpenAI、Google Vertex AI
3. 通过 CLI、终端、SDK 或 API 调用 AI 服务
4. 在 IDE 中使用 AI 编码助手，如 Copilot、Cursor、Codeium
5. 打开预先准备好的文件、步骤、答案或代码
6. 从网页、文档、聊天窗口复制粘贴内容
7. 打开题库、答案网站或相关作弊工具
"""

_DEFAULT_VIDEO_PROMPT = """你是一个屏幕录制视频内容分析专家。请分析这段屏幕录制视频，严格返回 JSON，不要返回 markdown 代码块，也不要返回其他解释。

请关注视频中的操作序列和时间变化，不仅描述单帧内容，还要描述操作流程。

{
  "screen_text": "视频中可见的所有文字内容（尽可能完整）",
  "application": "当前使用的应用程序或网站名称",
  "url": "如果可见，当前浏览器地址栏的 URL，否则为空字符串",
  "operation": "用户正在执行的操作描述",
  "ai_tool_detected": true,
  "ai_tool_name": "如检测到 AI 工具，给出工具名称，否则为空字符串",
  "code_visible": false,
  "code_content_summary": "如可见代码，给出代码片段摘要，否则为空字符串",
  "risk_indicators": ["检测到的可疑行为列表，如果没有则为空数组"],
  "operation_sequence": ["按时间顺序描述的操作步骤列表"],
  "summary": "一句话总结视频内容"
}

重点关注：
1. 使用 AI 对话平台，如 ChatGPT、Claude、Kimi、文心一言、通义千问
2. 使用云平台 AI 服务，如 AWS Bedrock、Azure OpenAI、Google Vertex AI
3. 通过 CLI、终端、SDK 或 API 调用 AI 服务
4. 在 IDE 中使用 AI 编码助手，如 Copilot、Cursor、Codeium
5. 打开预先准备好的文件、步骤、答案或代码
6. 从网页、文档、聊天窗口复制粘贴内容
7. 打开题库、答案网站或相关作弊工具
"""


def get_screen_analysis_prompt() -> str:
    """
    返回画面分析 Prompt（图片模式）。

    优先级：
    1. 环境变量 SCREEN_ANALYSIS_PROMPT_FILE 指定的外部文件内容
    2. 否则返回内置默认 Prompt
    """
    prompt_file = os.getenv("SCREEN_ANALYSIS_PROMPT_FILE")
    if prompt_file:
        path = Path(prompt_file)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return _DEFAULT_PROMPT


def get_video_analysis_prompt() -> str:
    """
    返回视频分析 Prompt（视频片段模式）。

    优先级：
    1. 环境变量 VIDEO_ANALYSIS_PROMPT_FILE 指定的外部文件内容
    2. 否则返回内置默认视频分析 Prompt
    """
    prompt_file = os.getenv("VIDEO_ANALYSIS_PROMPT_FILE")
    if prompt_file:
        path = Path(prompt_file)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return _DEFAULT_VIDEO_PROMPT


# 向后兼容：直接导入 SCREEN_ANALYSIS_PROMPT 的代码继续正常工作
SCREEN_ANALYSIS_PROMPT = get_screen_analysis_prompt()
