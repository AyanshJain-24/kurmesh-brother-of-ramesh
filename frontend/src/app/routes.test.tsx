import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { AppRoutes } from "./routes";
vi.mock("../components/map/OperationalMap", () => ({ OperationalMap: () => <div aria-label="Operational map" /> }));
beforeEach(() => {
  localStorage.setItem("kurmesh.accessToken", "test-token");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } })));
});
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });
function renderPath(path: string) { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppShell><AppRoutes /></AppShell></MemoryRouter></QueryClientProvider>); }
describe("application navigation", () => {
  it("redirects the root route to documentation", () => { renderPath("/"); expect(screen.getByRole("heading", { name: "Clear evidence for human route decisions.", level: 1 })).toBeInTheDocument(); });
  it("shows the active dashboard navigation item", () => { renderPath("/dashboard"); expect(screen.getByRole("link", { name: "Overview" })).toHaveClass("border-kurmesh-blue"); });
  it("connects sidebar Routes navigation to route management", async () => { renderPath("/routes"); expect(await screen.findByRole("heading", { name: "Route candidates and human review", level: 2 })).toBeInTheDocument(); });
  it("renders dashboard unavailable states", () => { renderPath("/dashboard"); expect(screen.getByText("No candidate routes")).toBeInTheDocument(); expect(screen.getByLabelText("Operational map")).toBeInTheDocument(); expect(screen.getAllByLabelText("Status: Unavailable").length).toBeGreaterThan(0); });
  it("redirects an unauthenticated operational request to login", () => { localStorage.clear(); renderPath("/dashboard"); expect(screen.getByRole("heading", { name: "Sign in", level: 1 })).toBeInTheDocument(); });
  it("allows an authenticated user to access the dashboard", () => { renderPath("/dashboard"); expect(screen.getByRole("heading", { name: "Operational dashboard", level: 2 })).toBeInTheDocument(); });
});
