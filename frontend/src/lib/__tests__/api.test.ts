import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, withMediaApiKey } from "../api";

describe("api.search", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("normalizes legacy search responses without segments", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          query: "AI",
          count: 1,
          results: [
            {
              frame_id: 1,
              video_id: 2,
              video_name: "demo.mp4",
              video_path: "E:/demo.mp4",
              timestamp: 12,
              matched_text: "AI platform",
              analysis_summary: "summary",
              frame_image_path: "frame.jpg",
              application: "Browser",
              ai_tool_detected: true,
              ai_tool_name: "glm",
              risk_indicators: ["ai usage"],
            },
          ],
        }),
      }),
    );

    const response = await api.search({ query: "AI" });

    expect(response.results).toHaveLength(1);
    expect(response.segments).toEqual([]);
    expect(response.segment_count).toBe(0);
  });

  it("appends api_key for protected media urls", () => {
    expect(withMediaApiKey("/api/frames/1/image", "secret key")).toBe("/api/frames/1/image?api_key=secret%20key");
    expect(withMediaApiKey("/api/videos/1/file?download=1", "secret key")).toBe(
      "/api/videos/1/file?download=1&api_key=secret%20key",
    );
  });

  it("surfaces backend detail messages for failed requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        headers: {
          get: () => "application/json",
        },
        json: async () => ({
          detail: "Path 'E:\\视频\\demo.mp4' is outside allowed directories",
        }),
      }),
    );

    await expect(api.importVideo("E:\\视频\\demo.mp4")).rejects.toEqual(
      expect.objectContaining<ApiError>({
        message: "400 Path 'E:\\视频\\demo.mp4' is outside allowed directories",
        statusCode: 400,
      }),
    );
  });
});
