import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RouteComparison } from "./RouteComparison";

const routes = [{ id: "route-a", mission_id: "mission-1", prediction_id: null, version: 1, status: "READY", geometry: { type: "LineString" as const, coordinates: [[10, -70], [12, -71]] as [number, number][] }, distance_nm: 18, estimated_duration_hours: null, risk_score: null, risk_components: {}, environmental_snapshot: {}, algorithm_version: "v1", metadata: {} }, { id: "route-b", mission_id: "mission-1", prediction_id: null, version: 2, status: "DRAFT", geometry: null, distance_nm: null, estimated_duration_hours: null, risk_score: null, risk_components: {}, environmental_snapshot: {}, algorithm_version: "v1", metadata: {} }];
afterEach(cleanup);
describe("RouteComparison", () => {
  it("renders only returned candidates and selects the requested candidate", () => { const select = vi.fn(); render(<RouteComparison routes={routes} onSelect={select} />); expect(screen.getByText("Route A")).toBeInTheDocument(); expect(screen.getByText("Route B")).toBeInTheDocument(); expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0); fireEvent.click(screen.getAllByRole("button", { name: "View route" })[1]); expect(select).toHaveBeenCalledWith(routes[1]); });
  it("renders no route rows for an empty backend response", () => { render(<RouteComparison routes={[]} onSelect={vi.fn()} />); expect(screen.getByText("No candidate routes")).toBeInTheDocument(); expect(screen.queryByText("Route A")).not.toBeInTheDocument(); });
});
