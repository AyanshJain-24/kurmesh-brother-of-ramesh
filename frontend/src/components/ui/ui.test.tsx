import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { MetricCard } from "./MetricCard";
import { Modal } from "./Modal";
import { StatusBadge } from "./StatusBadge";
import { Tabs } from "./Tabs";
afterEach(cleanup);

describe("Button", () => {
  it("supports loading and disabled states", () => { render(<Button loading>Save</Button>); const button = screen.getByRole("button", { name: "Save" }); expect(button).toBeDisabled(); expect(button).toHaveAttribute("aria-busy", "true"); });
});
describe("StatusBadge", () => { it("communicates status with text and semantics", () => { render(<StatusBadge status="DEGRADED" />); expect(screen.getByRole("status", { name: "Status: Degraded" })).toHaveTextContent("Degraded"); }); });
describe("MetricCard", () => { it("renders label, unit, and status", () => { render(<MetricCard label="Wind speed" value="18.4" unit="m/s" status="LIVE" />); expect(screen.getByText("Wind speed")).toBeInTheDocument(); expect(screen.getByText("18.4")).toBeInTheDocument(); expect(screen.getByRole("status")).toHaveTextContent("Live"); }); });
describe("Alert", () => { it("has alert semantics", () => { render(<Alert variant="warning" title="Caution">Review conditions.</Alert>); expect(screen.getByRole("alert")).toHaveTextContent("Review conditions."); }); });
describe("Modal", () => { it("closes with Escape and provides dialog semantics", () => { const close = vi.fn(); render(<Modal open onClose={close} title="Review">Body</Modal>); expect(screen.getByRole("dialog", { name: "Review" })).toBeInTheDocument(); fireEvent.keyDown(document, { key: "Escape" }); expect(close).toHaveBeenCalledOnce(); }); });
describe("Tabs", () => { it("switches tabs with arrow keys", () => { render(<Tabs tabs={[{ id: "one", label: "One", content: "First" }, { id: "two", label: "Two", content: "Second" }]} />); const one = screen.getByRole("tab", { name: "One" }); one.focus(); fireEvent.keyDown(one, { key: "ArrowRight" }); expect(screen.getByRole("tab", { name: "Two" })).toHaveAttribute("aria-selected", "true"); expect(screen.getByRole("tabpanel")).toHaveTextContent("Second"); }); });
