import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MissionWorkspacePage } from "./MissionWorkspacePage";
import type { Mission } from "../../api/types";

vi.mock("../../components/map/OperationalMap", () => ({ OperationalMap: () => <div aria-label="Operational map" /> }));

const vessel = { id: "vessel-1", name: "RV Aurora", vessel_type: "Research vessel", imo_number: null, specifications: { ice_class: "PC5" } };
const mission = { id: "mission-1", name: "Weddell research mission", state: "DRAFT", vessel_id: vessel.id, departure_at: "2026-01-10T09:00:00Z", origin: { latitude: -70, longitude: 10 }, destination: { latitude: -71, longitude: 12 } };
const analyzingMission = { ...mission, state: "ANALYZING" };
const candidate = { id: "candidate-1", mission_id: mission.id, prediction_id: null, version: 1, status: "READY", geometry: { type: "LineString" as const, coordinates: [[10, -70], [12, -71]] as [number, number][] }, distance_nm: 18, estimated_duration_hours: null, risk_score: null, risk_components: {}, environmental_snapshot: {}, algorithm_version: "prototype-risk-routing-v1", metadata: {} };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function renderWorkspace() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MissionWorkspacePage /></QueryClientProvider>);
}

function installApi({ missions = [] as Mission[], vessels = [] as typeof vessel[], onPostMission, onPostVessel, onPatchMission, onGenerate, generatedCandidates = [] as typeof candidate[] }: { missions?: Mission[]; vessels?: typeof vessel[]; onPostMission?: () => Response; onPostVessel?: () => Response; onPatchMission?: () => Response; onGenerate?: () => Promise<Response> | Response; generatedCandidates?: typeof candidate[] } = {}) {
  vi.stubGlobal("fetch", vi.fn((input: string, init?: RequestInit) => {
    if (input.endsWith("/missions") && init?.method === "POST") return Promise.resolve(onPostMission?.() ?? response(mission, 201));
    if (input.endsWith("/vessels") && init?.method === "POST") return Promise.resolve(onPostVessel?.() ?? response(vessel, 201));
    if (input.endsWith(`/missions/${mission.id}`) && init?.method === "PATCH") return Promise.resolve(onPatchMission?.() ?? response(mission));
    if (input.endsWith("/route-candidates/generate") && init?.method === "POST") return Promise.resolve(onGenerate?.() ?? response({ mission_id: mission.id, candidate_count: generatedCandidates.length, candidates: generatedCandidates, algorithm_version: "prototype-risk-routing-v1", environment_status: [], warnings: [] }, 201));
    if (input.endsWith("/missions")) return Promise.resolve(response({ items: missions }));
    if (input.endsWith("/vessels")) return Promise.resolve(response({ items: vessels }));
    if (input.endsWith("/environment/observations") || input.endsWith("/environment/sources")) return Promise.resolve(response({ items: [] }));
    if (input.includes("/route-candidates")) return Promise.resolve(response({ items: generatedCandidates }));
    if (input.includes("/routes") || input.includes("/alerts")) return Promise.resolve(response({ items: [] }));
    return Promise.reject(new Error(`Unexpected request: ${input}`));
  }));
}

beforeEach(() => localStorage.setItem("kurmesh.accessToken", "test-token"));
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });

describe("MissionWorkspacePage", () => {
  it("shows the Antarctic mission empty state and create action", async () => {
    installApi(); renderWorkspace();
    expect(await screen.findByText("No missions available")).toBeInTheDocument();
    expect(screen.getByText("Create an Antarctic research mission to begin environmental analysis and route planning.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create Mission" }).length).toBeGreaterThan(0);
  });

  it("creates a vessel with backend-provided data", async () => {
    let currentVessels: typeof vessel[] = [];
    installApi({ vessels: currentVessels, onPostVessel: () => { currentVessels = [vessel]; return response(vessel, 201); } }); renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Create Mission" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create vessel" }));
    fireEvent.change(screen.getByLabelText("Vessel name"), { target: { value: vessel.name } });
    fireEvent.change(screen.getByLabelText("Vessel type"), { target: { value: vessel.vessel_type } });
    fireEvent.change(screen.getByLabelText("Specifications"), { target: { value: JSON.stringify(vessel.specifications) } });
    fireEvent.click(screen.getByRole("button", { name: "Create vessel" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining("/vessels"), expect.objectContaining({ method: "POST" })));
    expect(await screen.findByRole("option", { name: "RV Aurora · Research vessel" })).toBeInTheDocument();
  });

  it("creates a mission and opens its mission workspace", async () => {
    let currentMissions: typeof mission[] = [];
    installApi({ vessels: [vessel], missions: currentMissions, onPostMission: () => { currentMissions = [mission]; return response(mission, 201); } }); renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Create Mission" }));
    fireEvent.change(screen.getByLabelText("Mission name"), { target: { value: mission.name } });
    fireEvent.change(screen.getByLabelText("Vessel"), { target: { value: vessel.id } });
    fireEvent.change(screen.getByLabelText("Departure date and time"), { target: { value: "2026-01-10T09:00" } });
    fireEvent.change(screen.getByLabelText("Origin latitude"), { target: { value: "-70" } });
    fireEvent.change(screen.getByLabelText("Origin longitude"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Destination latitude"), { target: { value: "-71" } });
    fireEvent.change(screen.getByLabelText("Destination longitude"), { target: { value: "12" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create mission" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining("/missions"), expect.objectContaining({ method: "POST" })));
    expect(await screen.findByText("ACTIVE MISSION")).toBeInTheDocument();
    expect(screen.getAllByText("Weddell research mission").length).toBeGreaterThan(0);
    expect(screen.getByText("Mission ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Mission workflow progress")).toHaveTextContent("Environmental data");
  });

  it("shows existing backend mission details without invented route or approval controls", async () => {
    installApi({ missions: [mission], vessels: [vessel] }); renderWorkspace();
    expect(await screen.findByText("RV Aurora · Research vessel")).toBeInTheDocument();
    expect(screen.getAllByText("Not yet generated").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /approve|reject|review/i })).not.toBeInTheDocument();
  });

  it("shows explicit route generation for an active mission without generating on page load", async () => {
    installApi({ missions: [analyzingMission], vessels: [vessel] }); renderWorkspace();
    expect(await screen.findByRole("button", { name: "Generate Route Options" })).toBeInTheDocument();
    expect(screen.getByLabelText("Mission workflow progress")).toHaveTextContent("Awaiting analysis");
    expect(vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/route-candidates/generate") && (init as RequestInit | undefined)?.method === "POST")).toBe(false);
  });

  it("shows route-generation loading and refetches mission, candidates, and governed routes on success", async () => {
    let resolveGeneration: (value: Response) => void = () => undefined;
    installApi({ missions: [analyzingMission], vessels: [vessel], generatedCandidates: [candidate], onGenerate: () => new Promise<Response>((resolve) => { resolveGeneration = resolve; }) }); renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Generate Route Options" }));
    expect(await screen.findByText("Generating route options...")).toBeInTheDocument();
    resolveGeneration(response({ mission_id: mission.id, candidate_count: 1, candidates: [candidate], algorithm_version: "prototype-risk-routing-v1", environment_status: ["UNAVAILABLE"], warnings: [] }, 201));
    expect(await screen.findByText("1 route option generated.")).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/missions")).length).toBeGreaterThan(1));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/route-candidates")).length).toBeGreaterThan(1));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/routes")).length).toBeGreaterThan(1));
  });

  it("requires bounded coordinates before creating a mission", async () => {
    installApi({ vessels: [vessel] }); renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Create Mission" }));
    expect(screen.getByLabelText("Origin latitude")).toHaveAttribute("min", "-90");
    expect(screen.getByLabelText("Origin latitude")).toHaveAttribute("max", "90");
    expect(screen.getByLabelText("Destination longitude")).toHaveAttribute("min", "-180");
    expect(screen.getByLabelText("Destination longitude")).toHaveAttribute("max", "180");
  });

  it("saves missing coordinates for an existing mission and enables generation", async () => {
    const withoutCoordinates = { ...analyzingMission, origin: null, destination: null };
    installApi({ missions: [withoutCoordinates], vessels: [vessel], onPatchMission: () => response(analyzingMission) }); renderWorkspace();
    const generate = await screen.findByRole("button", { name: "Generate Route Options" }); expect(generate).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Edit coordinates" }));
    fireEvent.change(screen.getByLabelText("Edit origin latitude"), { target: { value: "-70" } }); fireEvent.change(screen.getByLabelText("Edit origin longitude"), { target: { value: "10" } }); fireEvent.change(screen.getByLabelText("Edit destination latitude"), { target: { value: "-71" } }); fireEvent.change(screen.getByLabelText("Edit destination longitude"), { target: { value: "12" } }); fireEvent.click(screen.getByRole("button", { name: "Save coordinates" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining(`/missions/${mission.id}`), expect.objectContaining({ method: "PATCH" })));
    expect(await screen.findByRole("button", { name: "Generate Route Options" })).not.toBeDisabled();
  });

  it("displays a backend route-generation error", async () => {
    installApi({ missions: [analyzingMission], vessels: [vessel], onGenerate: () => response({ error: { code: "INVALID_MISSION_STATE", message: "Mission is not analyzing" } }, 409) }); renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Generate Route Options" }));
    expect(await screen.findByText("Mission is not analyzing")).toBeInTheDocument();
  });

  it("shows a mission API error without rendering fabricated missions", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string) => input.endsWith("/missions") ? Promise.resolve(response({ error: { code: "INTERNAL_ERROR", message: "failed" } }, 500)) : Promise.resolve(response({ items: [] })))); renderWorkspace();
    expect(await screen.findByText("Mission data unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Antarctic Research Mission 01")).not.toBeInTheDocument();
  });
});
