import { describe, expect, it } from "vitest";
import { API_BASE_URL, apiBaseUrl, buildApiUrl, cleanApiBaseUrl } from "./client";

describe("API deployment configuration", () => {
  it("uses a relative API path by default and never hard-codes localhost", () => {
    expect(apiBaseUrl).toBe("/api/v1");
    expect(API_BASE_URL).toBe("/api/v1");
    expect(apiBaseUrl).not.toContain("localhost");
  });

  it("cleans base URLs with stray parentheses, whitespace, slashes, or markdown syntax", () => {
    expect(cleanApiBaseUrl("https://kurmesh-api.onrender.com/api/v1)")).toBe("https://kurmesh-api.onrender.com/api/v1");
    expect(cleanApiBaseUrl("https://kurmesh-api.onrender.com/api/v1/")).toBe("https://kurmesh-api.onrender.com/api/v1");
    expect(cleanApiBaseUrl("https://kurmesh-api.onrender.com/api/v1/) ")).toBe("https://kurmesh-api.onrender.com/api/v1");
    expect(cleanApiBaseUrl("[https://kurmesh-api.onrender.com/api/v1](https://kurmesh-api.onrender.com/api/v1)")).toBe("https://kurmesh-api.onrender.com/api/v1");
    expect(cleanApiBaseUrl("/api/v1/")).toBe("/api/v1");
    expect(cleanApiBaseUrl(undefined)).toBe("/api/v1");
  });

  it("builds API URLs cleanly without double slashes", () => {
    expect(buildApiUrl("/auth/login")).toBe(`${API_BASE_URL}/auth/login`);
    expect(buildApiUrl("auth/login")).toBe(`${API_BASE_URL}/auth/login`);
    expect(buildApiUrl("//auth/login")).toBe(`${API_BASE_URL}/auth/login`);
  });
});

