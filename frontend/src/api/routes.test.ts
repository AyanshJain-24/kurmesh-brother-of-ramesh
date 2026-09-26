import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { generateRouteCandidates } from "./routes";

describe("generateRouteCandidates", () => {
  beforeEach(() => localStorage.setItem("kurmesh.accessToken", "test-token"));
  afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

  it("uses the authenticated route-generation endpoint with an empty JSON body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ mission_id: "mission-1", candidate_count: 3, candidates: [], algorithm_version: "prototype-risk-routing-v1", environment_status: [], warnings: [] }), { status: 201, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await generateRouteCandidates("mission-1");

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/missions/mission-1/route-candidates/generate", expect.objectContaining({
      method: "POST", body: "{}", headers: expect.objectContaining({ Authorization: "Bearer test-token" }),
    }));
  });
});
