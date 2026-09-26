import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ACCESS_TOKEN_STORAGE_KEY } from "../../api/client";
import { LoginPage } from "./LoginPage";

function response(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } }); }
function renderLogin() { return render(<MemoryRouter initialEntries={["/login"]}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/dashboard" element={<h1>Dashboard destination</h1>} /></Routes></MemoryRouter>); }

afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });

describe("LoginPage", () => {
  it("stores the token and redirects to the dashboard after success", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ access_token: "login-token", token_type: "Bearer", user: { id: "u1", email: "operator@example.test", full_name: "Operator", is_active: true, roles: ["user"] } }))));
    renderLogin(); const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "operator@example.test");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in securely" }));
    expect(await screen.findByRole("heading", { name: "Dashboard destination" })).toBeInTheDocument();
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("login-token");
  });

  it("displays the backend login error", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ error: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" } }, 401))));
    renderLogin(); const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "operator@example.test");
    await user.type(screen.getByLabelText("Password"), "incorrect-password");
    await user.click(screen.getByRole("button", { name: "Sign in securely" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
  });
});
