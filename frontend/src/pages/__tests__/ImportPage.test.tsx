import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ImportPage } from "../ImportPage";

describe("ImportPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits single video import with selected process mode", async () => {
    let capturedPath = "";
    let capturedMode = "";

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string | Request | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();

        if (url.includes("/api/videos/import") && !url.includes("import-folder")) {
          const body = JSON.parse(String(init?.body ?? "{}"));
          capturedPath = body.path;
          capturedMode = body.mode;
          return new Response(
            JSON.stringify({
              video: { id: 1, filename: "sample.mp4", filepath: "E:/sample.mp4", duration: 60, format: "mp4", resolution: "1920x1080", status: "pending" },
              task: { id: 10, video_id: 1, task_type: "video_process", status: "pending", progress: 0, details: {} },
              estimate: { estimated_frames: 6, estimated_cost: 0 },
            }),
            { status: 200 }
          );
        }
        if (url.includes("/api/videos/import-folder")) {
          return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
        }
        if (url.includes("/api/videos")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.includes("/api/tasks")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      })
    );

    const router = createMemoryRouter([{ path: "/", element: <ImportPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);

    const videoInput = screen.getByLabelText("视频路径");
    fireEvent.change(videoInput, { target: { value: "E:/sample.mp4" } });

    const modeSelect = screen.getByLabelText("处理模式");
    fireEvent.change(modeSelect, { target: { value: "deep" } });

    const submitButton = screen.getByRole("button", { name: "导入并排队" });
    fireEvent.click(submitButton);

    await waitFor(() => expect(capturedPath).toBe("E:/sample.mp4"));
    expect(capturedMode).toBe("deep");
  });

  it("shows error message when import fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string | Request | URL, _init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();
        if (url.includes("/api/videos/import") && !url.includes("import-folder")) {
          return new Response(JSON.stringify({ detail: "Path 'E:/missing.mp4' does not exist" }), { status: 400 });
        }
        if (url.includes("/api/videos")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.includes("/api/tasks")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      })
    );

    const router = createMemoryRouter([{ path: "/", element: <ImportPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);

    const videoInput = screen.getByLabelText("视频路径");
    fireEvent.change(videoInput, { target: { value: "E:/missing.mp4" } });

    const submitButton = screen.getByRole("button", { name: "导入并排队" });
    fireEvent.click(submitButton);

    await waitFor(() => expect(screen.getByText(/请求参数不正确/)).toBeInTheDocument());
  });

  it("submits folder import", async () => {
    let capturedFolderPath = "";

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string | Request | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();
        if (url.includes("/api/videos") && !url.includes("import")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.includes("/api/tasks")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.includes("/api/videos/import-folder")) {
          const body = JSON.parse(String(init?.body ?? "{}"));
          capturedFolderPath = body.folder_path;
          return new Response(
            JSON.stringify({
              videos: [
                { id: 2, filename: "a.mp4", filepath: "E:/batch/a.mp4", duration: 30, format: "mp4", resolution: "1280x720", status: "pending" },
              ],
              tasks: [{ id: 20, video_id: 2, task_type: "video_process", status: "pending", progress: 0, details: {} }],
              count: 1,
            }),
            { status: 200 }
          );
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      })
    );

    const router = createMemoryRouter([{ path: "/", element: <ImportPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);

    const folderInput = screen.getByLabelText("文件夹路径");
    fireEvent.change(folderInput, { target: { value: "E:/batch-01" } });

    const submitButton = screen.getByRole("button", { name: "批量导入" });
    fireEvent.click(submitButton);

    await waitFor(() => expect(capturedFolderPath).toBe("E:/batch-01"));
  });
});
