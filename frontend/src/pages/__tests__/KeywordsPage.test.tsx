import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { KeywordsPage } from "../KeywordsPage";

describe("KeywordsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("updates a keyword set and accepts Chinese punctuation in term input", async () => {
    let updatePayload: Record<string, unknown> | null = null;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string | Request | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();

        if (url.endsWith("/api/keywords") && (!init?.method || init.method === "GET")) {
          return new Response(
            JSON.stringify([
              { id: 1, name: "AI tools", category: "tool", terms: ["ChatGPT", "Copilot"] },
            ]),
            { status: 200 },
          );
        }

        if (url.endsWith("/api/keywords/1") && init?.method === "PUT") {
          updatePayload = JSON.parse(String(init.body ?? "{}"));
          return new Response(
            JSON.stringify({ id: 1, name: "AI tools", category: "tool", terms: ["ChatGPT", "Bedrock", "Claude"] }),
            { status: 200 },
          );
        }

        if (url.endsWith("/api/keywords/1/scan")) {
          return new Response(JSON.stringify({ keyword_set_id: 1, total_terms: 0, total_hits: 0, results: [] }), {
            status: 200,
          });
        }

        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );

    const router = createMemoryRouter([{ path: "/", element: <KeywordsPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);

    await waitFor(() => expect(screen.getByText("AI tools")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("关键词"), {
      target: { value: "ChatGPT，Bedrock；Claude" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存关键词集" }));

    await waitFor(() =>
      expect(updatePayload).toEqual({
        name: "AI tools",
        category: "tool",
        terms: ["ChatGPT", "Bedrock", "Claude"],
      }),
    );
  });
});
