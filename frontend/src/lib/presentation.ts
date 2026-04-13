const applicationLabelMap: Record<string, string> = {
  Browser: "浏览器",
  "Web Browser": "浏览器",
  "CSDN Blog / Web Browser": "CSDN 博客 / 浏览器",
  "AWS Management Console": "AWS 管理控制台",
  "Mock Review Browser": "模拟审查浏览器",
};

const riskIndicatorLabelMap: Record<string, string> = {
  "ai usage": "检测到 AI 使用行为",
  "ai platform usage": "检测到 AI 平台使用行为",
  "mock-analysis": "模拟分析结果",
  potential_ai_assistance_during_exam: "疑似在考试过程中使用 AI 辅助",
  using_ai_for_exam_task: "疑似使用 AI 完成考试任务",
  credential_placeholder_in_code: "代码中出现凭证占位符",
  tutorial_following_behavior: "存在按教程步骤操作的迹象",
  "AI-assisted code generation for production infrastructure": "疑似使用 AI 生成生产环境基础设施代码",
  "Potential credential exposure in CLI commands": "命令行中可能暴露凭证或敏感参数",
  "AWS account ID visible (3709-2575-1195)": "画面中暴露了 AWS 账号 ID",
  "Username visible (cheat-user)": "画面中暴露了用户名",
  "AI-generated code being used for cloud infrastructure": "疑似将 AI 生成代码用于云基础设施操作",
  "AWS credentials may be involved": "可能涉及 AWS 凭证或敏感云资源访问",
  "AI-generated code being used": "检测到 AI 生成代码被直接使用",
  "AWS cloud service credentials potentially involved": "可能涉及 AWS 云服务凭证或敏感配置",
  "Database access code": "检测到数据库访问相关代码",
};

function translateKnownValue(value: string, dictionary: Record<string, string>): string {
  const normalized = value.trim();
  if (!normalized) {
    return "";
  }
  return dictionary[normalized] ?? normalized;
}

export function formatTaskStatus(status: string | null | undefined): string {
  switch (status) {
    case "pending":
      return "等待中";
    case "running":
      return "处理中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "processing":
      return "处理中";
    default:
      return status || "-";
  }
}

export function formatTaskStage(stage: string | null | undefined): string {
  switch (stage) {
    case "pending":
      return "等待中";
    case "extracting":
      return "正在抽帧";
    case "analyzing":
      return "正在分析画面";
    case "coarse_analyzing":
      return "粗扫中";
    case "coarse_completed":
      return "粗扫完成";
    case "fine_extracting":
      return "精扫抽帧中";
    case "fine_analyzing":
      return "精扫分析中";
    case "fine_completed":
      return "精扫完成";
    case "deep_analyzing":
      return "全帧精扫中";
    case "deep_completed":
      return "全帧精扫完成";
    case "completed":
      return "处理完成";
    case "failed":
      return "处理失败";
    default:
      return stage || "等待中";
  }
}

export function formatAiDetectionLabel(detected: boolean, toolName?: string): string {
  if (detected) {
    return toolName ? `已检测到：${toolName}` : "已检测到 AI 工具";
  }
  return "未检测到 AI 工具";
}

export function formatMatchedSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case "ocr":
      return "OCR命中";
    case "summary":
      return "摘要命中";
    case "ai_tool_name":
      return "工具名命中";
    case "metadata":
      return "元数据命中";
    default:
      return "内容命中";
  }
}

export function formatMatchedSourcesLabel(sources: string[] | null | undefined): string {
  const unique = Array.from(new Set((sources ?? []).filter(Boolean)));
  if (unique.length === 0) {
    return "内容命中";
  }
  if (unique.length === 1) {
    return formatMatchedSourceLabel(unique[0]);
  }
  return "多来源命中";
}

export function formatApplicationLabel(application: string): string {
  if (!application) {
    return "未知应用";
  }
  return translateKnownValue(application, applicationLabelMap);
}

export function formatRiskLabel(riskIndicators: string[]): string {
  if (riskIndicators.length === 0) {
    return "无风险标签";
  }
  return riskIndicators.map((indicator) => translateKnownValue(indicator, riskIndicatorLabelMap)).join("，");
}

export function formatTokenUsage(totalTokens: number, analyzerMode?: string): string {
  if (analyzerMode === "mock") {
    return `${totalTokens}（mock）`;
  }
  return String(totalTokens);
}

export function formatErrorMessage(message: string): string {
  const normalized = message.trim();
  const lowered = normalized.toLowerCase();

  if (!normalized) {
    return "错误：发生未知异常";
  }
  if (normalized === "Failed to fetch" || normalized === "NetworkError when attempting to fetch resource.") {
    return "错误：无法连接后端服务，或请求被跨域/代理配置拦截，请检查后端地址、端口与 CORS 设置";
  }
  if (normalized.startsWith("429") || lowered.includes("error code: 429") || lowered.includes("rate limit") || normalized.includes("速率限制")) {
    return "错误：视觉模型接口已被限流，请降低并发或稍后重试";
  }
  if (lowered.includes("outside allowed directories")) {
    return "错误：导入路径不在允许目录中，请修改 ALLOWED_VIDEO_DIRS 或更换导入路径";
  }
  if (lowered.includes("video file does not exist")) {
    return "错误：视频文件不存在，请检查路径是否正确";
  }
  if (lowered.includes("video path is not a file")) {
    return "错误：导入路径不是文件，请选择具体的视频文件";
  }
  if (lowered.includes("folder does not exist")) {
    return "错误：文件夹不存在，请检查路径是否正确";
  }
  if (lowered.includes("folder path is not a directory")) {
    return "错误：导入路径不是文件夹，请选择目录";
  }
  if (normalized.startsWith("400")) {
    return "错误：请求参数不正确";
  }
  if (normalized.startsWith("401")) {
    return "错误：API Key 无效或缺失，请检查前后端配置";
  }
  if (normalized.startsWith("422")) {
    return "错误：提交内容不符合接口要求，请检查输入项";
  }
  if (normalized.startsWith("404")) {
    return "错误：接口或资源不存在";
  }
  if (normalized.startsWith("500")) {
    return "错误：服务端处理失败，请稍后重试";
  }
  if (normalized.startsWith("502") || normalized.startsWith("503") || normalized.startsWith("504")) {
    return "错误：后端服务暂时不可用";
  }
  return `错误：${normalized}`;
}

export function formatSecondsAsClock(seconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
}

export function formatTimeRange(startSeconds: number, endSeconds: number): string {
  return `${formatSecondsAsClock(startSeconds)} - ${formatSecondsAsClock(endSeconds)}`;
}
