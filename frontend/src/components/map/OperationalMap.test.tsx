import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OperationalMap } from "./OperationalMap";

const { callbacks, mapConstructor, mapInstance } = vi.hoisted(() => {
  const callbacks: Record<string, () => void> = {};
  const instance = {
    addLayer: vi.fn(),
    addSource: vi.fn(),
    fitBounds: vi.fn(),
    getSource: vi.fn(),
    jumpTo: vi.fn(),
    on: vi.fn((event: string, callback: () => void) => { callbacks[event] = callback; }),
    remove: vi.fn(),
    resize: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
  };
  return { callbacks, mapConstructor: vi.fn(() => instance), mapInstance: instance };
});

vi.mock("maplibre-gl", () => ({ Map: mapConstructor }));

class TestResizeObserver {
  disconnect = vi.fn();
  observe = vi.fn();
}

beforeEach(() => {
  Object.keys(callbacks).forEach((key) => delete callbacks[key]);
  Object.values(mapInstance).forEach((value) => {
    if (typeof value === "function" && "mockClear" in value) value.mockClear();
  });
  vi.stubGlobal("ResizeObserver", TestResizeObserver);
});

afterEach(() => {
  cleanup();
  mapConstructor.mockClear();
  vi.unstubAllGlobals();
});

describe("OperationalMap", () => {
  it("initializes a neutral map without operational layers and exposes map controls", () => {
    render(<OperationalMap />);

    expect(mapConstructor).toHaveBeenCalledWith(expect.objectContaining({
      attributionControl: false,
      center: [0, -82],
      maxBounds: [[-180, -90], [180, -45]],
      zoom: 1.65,
    }));
    expect(screen.getByText("No candidate route geometry is available for the selected mission.")).toBeInTheDocument();
    expect(screen.getByText("Operational layers unavailable")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    fireEvent.click(screen.getByRole("button", { name: "Focus Antarctica" }));

    expect(mapInstance.zoomIn).toHaveBeenCalledOnce();
    expect(mapInstance.zoomOut).toHaveBeenCalledOnce();
    expect(mapInstance.jumpTo).toHaveBeenCalledWith({ center: [0, -82], zoom: 1.65 });
  });

  it("reports initialization failure without rendering operational data", () => {
    mapConstructor.mockImplementationOnce(() => { throw new Error("WebGL unavailable"); });
    render(<OperationalMap />);

    expect(screen.getByText("Operational map unavailable")).toBeInTheDocument();
    expect(screen.getByText("The map foundation could not be initialized. No operational layers are displayed.")).toBeInTheDocument();
  });

  it("adds only returned candidate route GeoJSON and focuses a selected route", () => {
    render(<OperationalMap selectedRouteId="route-1" routes={[{ id: "route-1", mission_id: "mission-1", prediction_id: null, version: 1, status: "READY", geometry: { type: "LineString", coordinates: [[10, -70], [20, -72]] }, distance_nm: null, estimated_duration_hours: null, risk_score: null, risk_components: {}, environmental_snapshot: {}, algorithm_version: "v1", metadata: {} }, { id: "route-2", mission_id: "mission-1", prediction_id: null, version: 2, status: "DRAFT", geometry: null, distance_nm: null, estimated_duration_hours: null, risk_score: null, risk_components: {}, environmental_snapshot: {}, algorithm_version: "v1", metadata: {} }]} />);
    act(() => { callbacks.load(); });
    expect(mapInstance.addSource).toHaveBeenCalledWith("candidate-routes", expect.objectContaining({ data: expect.objectContaining({ features: [expect.objectContaining({ properties: { id: "route-1" } })] }) }));
    expect(mapInstance.fitBounds).toHaveBeenCalledWith([[10, -72], [20, -70]], expect.any(Object));
  });
});
