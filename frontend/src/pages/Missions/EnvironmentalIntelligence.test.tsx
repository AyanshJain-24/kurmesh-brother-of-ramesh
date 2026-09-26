import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EnvironmentalIntelligence } from "./EnvironmentalIntelligence";

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const source = { id: "source-1", provider: "NOAA/NSIDC", source: "G10016 V4", url: "https://example.test/source", metadata: {} };
const observation = (observation_type: string, status: "LIVE" | "STALE" | "DEGRADED" | "UNAVAILABLE" | "ERROR", value: Record<string, unknown> | null, units: string, source_id = source.id) => ({ id: `${observation_type}-${status}`, source_id, observation_type, status, value, units, quality: null, resolution: "25 km", retrieved_at: "2026-01-01T00:00:00Z", valid_from: "2026-01-01T00:00:00Z", valid_to: "2026-01-01T06:00:00Z", location: { longitude: 10, latitude: -70 } });

function renderIntelligence() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><EnvironmentalIntelligence /></QueryClientProvider>); }
function installApi(items: ReturnType<typeof observation>[], sources = [source]) { vi.stubGlobal("fetch", vi.fn((input: string) => { if (input.endsWith("/environment/observations")) return Promise.resolve(response({ items })); if (input.endsWith("/environment/sources")) return Promise.resolve(response({ items: sources })); return Promise.reject(new Error(`Unexpected request: ${input}`)); })); }

beforeEach(() => localStorage.setItem("kurmesh.accessToken", "test-token"));
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });

describe("EnvironmentalIntelligence", () => {
  it("renders actual sea-ice, weather, and ocean values with their provider statuses and provenance", async () => {
    installApi([observation("sea_ice_concentration", "LIVE", { concentration: 0.4 }, "1"), observation("wind", "STALE", { speed: 11.2, direction_degrees: 315 }, "m s-1"), observation("air_temperature", "DEGRADED", { temperature: -8.1 }, "degC"), observation("sea_level_pressure", "LIVE", { pressure: 995 }, "hPa"), observation("ocean_current", "LIVE", { speed: 0.6, direction_degrees: 70 }, "m s-1"), observation("sea_water_temperature", "LIVE", { temperature: -1.2 }, "degC")]);
    renderIntelligence();
    expect(await screen.findByText("0.4 1")).toBeInTheDocument();
    expect(screen.getByText("11.2 m s-1")).toBeInTheDocument();
    expect(screen.getByText("995 hPa")).toBeInTheDocument();
    expect(screen.getAllByText("Source: NOAA/NSIDC · G10016 V4").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("Status: Live").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("Status: Stale").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("Status: Degraded").length).toBeGreaterThan(0);
    expect(screen.getByText("MODEL_UNAVAILABLE")).toBeInTheDocument();
  });

  it("does not display a value from an unavailable provider record or invoke iceberg inference", async () => {
    installApi([observation("sea_ice_concentration", "UNAVAILABLE", { concentration: 0.7 }, "1")]);
    renderIntelligence();
    expect(await screen.findByText("MODEL_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText("0.7 1")).not.toBeInTheDocument();
    expect(screen.getByText("The validated demo model requires a complete frozen trajectory feature vector. That input is not available from this mission workspace.")).toBeInTheDocument();
    expect(vi.mocked(fetch)).not.toHaveBeenCalledWith(expect.stringContaining("/demo/ml/iceberg/predict"), expect.anything());
  });

  it("shows a loading state while authorized environment requests are unresolved", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined))); renderIntelligence();
    expect(screen.getByText("Loading environmental intelligence")).toBeInTheDocument();
  });

  it("uses authenticated API requests and shows an explicit error when a provider record request fails", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string) => input.endsWith("/environment/observations") ? Promise.resolve(response({ error: { code: "PROVIDER_ERROR", message: "unavailable" } }, 503)) : Promise.resolve(response({ items: [source] })))); renderIntelligence();
    expect(await screen.findByText("Environmental intelligence unavailable")).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining("/environment/observations"), expect.objectContaining({ headers: { Authorization: "Bearer test-token" } })));
  });
});
