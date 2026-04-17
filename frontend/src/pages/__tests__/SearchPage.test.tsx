import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { SearchPage, getAiToolDetectedParam } from "../SearchPage";

function setup() {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <SearchPage />,
      },
    ],
    { initialEntries: ["/"] }
  );
  return render(<RouterProvider router={router} />);
}

describe("SearchPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders search form and submits with correct ai_tool_detected filter", async () => {
    let capturedPayload: Record<string, unknown> | null = null;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string | Request | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();

        if (url.includes("/api/videos")) {
          return new Response(JSON.stringify([{ id: 1, filename: "demo.mp4", filepath: "E:/demo.mp4", duration: 60, format: "mp4", resolution: "1920x1080", status: "completed" }]), { status: 200 });
        }
        if (url.includes("/api/health")) {
          return new Response(JSON.stringify({ status: "ok", vision_analyzer_mode: "live" }), { status: 200 });
        }
        if (url.includes("/api/search")) {
          capturedPayload = JSON.parse(String(init?.body ?? "{}"));
          return new Response(
            JSON.stringify({
              query: "AI",
              count: 1,
              results: [
                {
                  frame_id: 1,
                  video_id: 1,
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
            { status: 200 }
          );
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      })
    );

    setup();

    await waitFor(() => expect(screen.getByText("demo.mp4")).toBeInTheDocument());

    const queryInput = screen.getByPlaceholderText("输入关键词、短语或平台名称；多个词需同时出现");
    fireEvent.change(queryInput, { target: { value: "AI" } });

    const aiFilter = screen.getByLabelText("AI 工具检测");
    fireEvent.change(aiFilter, { target: { value: "no" } });

    const submitButton = screen.getByRole("button", { name: "开始检索" });
    fireEvent.click(submitButton);

    await waitFor(() => expect(capturedPayload).not.toBeNull());
    expect(capturedPayload).toMatchObject({
      query: "AI",
      ai_tool_detected: false,
    });
  });

  it("disables submit button when query is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([]), { status: 200 })
      )
    );

    setup();
    await waitFor(() => {});
    const submitButton = screen.getByRole("button", { name: "开始检索" });
    expect(submitButton).toBeDisabled();
  });

  describe("getAiToolDetectedParam", () => {
    it('returns undefined for "any"', () => {
      expect(getAiToolDetectedParam("any")).toBeUndefined();
    });

    it('returns true for "yes"', () => {
      expect(getAiToolDetectedParam("yes")).toBe(true);
    });

    it('returns false for "no"', () => {
      expect(getAiToolDetectedParam("no")).toBe(false);
    });

    it("returns false for unknown values", () => {
      expect(getAiToolDetectedParam("unknown")).toBe(false);
      expect(getAiToolDetectedParam("")).toBe(false);
    });
  });
});
