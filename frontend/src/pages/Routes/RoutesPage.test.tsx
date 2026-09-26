import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RoutesPage } from "./RoutesPage";

vi.mock("../../components/map/OperationalMap", () => ({ OperationalMap: () => <div aria-label="Operational map" /> }));
const mission = { id: "mission-1", name: "Weddell mission", state: "ROUTES_AVAILABLE", vessel_id: null, departure_at: null, origin: { latitude: -70, longitude: 10 }, destination: { latitude: -71, longitude: 12 } };
const candidate = { id: "candidate-1", mission_id: mission.id, prediction_id: null, version: 1, status: "READY", geometry: { type: "LineString" as const, coordinates: [[10, -70], [12, -71]] as [number, number][] }, distance_nm: 18, estimated_duration_hours: null, risk_score: null, risk_components: {}, environmental_snapshot: {}, algorithm_version: "prototype-risk-routing-v1", metadata: {} };
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
function renderPage() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RoutesPage /></QueryClientProvider>); }
beforeEach(() => localStorage.setItem("kurmesh.accessToken", "token")); afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });

describe("RoutesPage", () => {
  it("asks the operator to select a mission before querying routes", async () => { vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ items: [mission] })))); renderPage(); expect(await screen.findByRole("heading", { name: "Select a mission" })).toBeInTheDocument(); expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("route-candidates"))).toBe(false); });
  it("renders only backend route candidates after mission selection", async () => { vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(response(url.endsWith("/missions") ? { items: [mission] } : url.includes("route-candidates") ? { items: [candidate] } : { items: [] })))); renderPage(); fireEvent.change(await screen.findByLabelText("Route management mission"), { target: { value: mission.id } }); expect(await screen.findByText("Route A")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "View route" })); expect(await screen.findByText("Selected route")).toBeInTheDocument(); });
});
