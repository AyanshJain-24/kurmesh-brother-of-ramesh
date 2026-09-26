import { describe, expect, it } from "vitest";
import { apiBaseUrl } from "./client";

describe("API deployment configuration", () => {
  it("uses a relative API path by default and never hard-codes localhost", () => {
    expect(apiBaseUrl).toBe("/api/v1");
    expect(apiBaseUrl).not.toContain("localhost");
  });
});
