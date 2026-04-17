import { describe, expect, it } from "vitest";

import { parseKeywordTermsInput } from "../keywords";

describe("parseKeywordTermsInput", () => {
  it("supports Chinese commas, semicolons, and new lines", () => {
    expect(parseKeywordTermsInput("ChatGPT，Bedrock；Copilot\nClaude, Gemini"))
      .toEqual(["ChatGPT", "Bedrock", "Copilot", "Claude", "Gemini"]);
  });
});
