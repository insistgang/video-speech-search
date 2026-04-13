import { expect, test } from "vitest";

import {
  formatApplicationLabel,
  formatErrorMessage,
  formatMatchedSourceLabel,
  formatMatchedSourcesLabel,
  formatRiskLabel,
  formatSecondsAsClock,
  formatTaskStage,
  formatTimeRange
} from "../presentation";

test("formats known application labels in Chinese", () => {
  expect(formatApplicationLabel("AWS Management Console")).toBe("AWS 管理控制台");
});

test("formats known risk indicators in Chinese", () => {
  expect(formatRiskLabel(["potential_ai_assistance_during_exam", "Database access code"])).toBe(
    "疑似在考试过程中使用 AI 辅助，检测到数据库访问相关代码"
  );
});

test("formats common network errors in Chinese", () => {
  expect(formatErrorMessage("Failed to fetch")).toBe(
    "错误：无法连接后端服务，或请求被跨域/代理配置拦截，请检查后端地址、端口与 CORS 设置"
  );
});

test("formats disallowed import path errors in Chinese", () => {
  expect(formatErrorMessage("400 Path 'E:\\视频\\demo.mp4' is outside allowed directories")).toBe(
    "错误：导入路径不在允许目录中，请修改 ALLOWED_VIDEO_DIRS 或更换导入路径"
  );
});

test("formats missing video file errors in Chinese", () => {
  expect(formatErrorMessage("400 Video file does not exist: E:\\视频\\demo.mp4")).toBe(
    "错误：视频文件不存在，请检查路径是否正确"
  );
});

test("formats validation errors in Chinese", () => {
  expect(formatErrorMessage("422 Unprocessable Entity")).toBe("错误：提交内容不符合接口要求，请检查输入项");
});

test("formats rate limit errors in Chinese", () => {
  expect(formatErrorMessage("Error code: 429 - {'error': {'code': '1302', 'message': '您的账户已达到速率限制'}}")).toBe(
    "错误：视觉模型接口已被限流，请降低并发或稍后重试"
  );
});

test("formats media auth errors in Chinese", () => {
  expect(formatErrorMessage("401 Unauthorized")).toBe("错误：API Key 无效或缺失，请检查前后端配置");
});

test("formats seconds as clock", () => {
  expect(formatSecondsAsClock(65)).toBe("01:05");
});

test("formats time ranges", () => {
  expect(formatTimeRange(53, 62)).toBe("00:53 - 01:02");
});

test("formats task stages", () => {
  expect(formatTaskStage("analyzing")).toBe("正在分析画面");
  expect(formatTaskStage("fine_analyzing")).toBe("精扫分析中");
});

test("formats matched sources", () => {
  expect(formatMatchedSourceLabel("ocr")).toBe("OCR命中");
  expect(formatMatchedSourceLabel("metadata")).toBe("元数据命中");
  expect(formatMatchedSourcesLabel(["summary", "metadata"])).toBe("多来源命中");
});
