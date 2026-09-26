import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EnvironmentOverview } from "./EnvironmentOverview";

function renderOverview() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><EnvironmentOverview /></QueryClientProvider>); }
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }); }
beforeEach(() => { localStorage.setItem("kurmesh.accessToken", "test-token"); });
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });
describe("EnvironmentOverview", () => {
  it("renders real-shaped provider states without inventing values", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ items: [{ id: "ice-1", source_id: "source", observation_type: "sea_ice_concentration", status: "LIVE", value: { concentration: 0.4 }, units: "percent", quality: null, resolution: null, retrieved_at: "2026-01-01T00:00:00Z", valid_from: null, valid_to: null, location: null }, { id: "weather-1", source_id: "source", observation_type: "weather", status: "ERROR", value: null, units: "none", quality: null, resolution: null, retrieved_at: "2026-01-01T00:00:00Z", valid_from: null, valid_to: null, location: null }], page: 1, page_size: 20, total: 2 }))); renderOverview(); expect(await screen.findByText("sea ice concentration")).toBeInTheDocument(); expect(screen.getByLabelText("Status: Live")).toBeInTheDocument(); expect(screen.getByLabelText("Status: Error")).toBeInTheDocument(); expect(screen.queryByText("0.4")).not.toBeInTheDocument(); });
  it("renders explicit unavailable states for an empty backend response", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ items: [], page: 1, page_size: 20, total: 0 }))); renderOverview(); expect(await screen.findAllByText("No current data available.")).toHaveLength(4); });
  it("isolates a backend error to the environmental section", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ error: { code: "INTERNAL_ERROR", message: "failed" } }, 500))); renderOverview(); expect(await screen.findByText("Environmental observations unavailable")).toBeInTheDocument(); });
});
