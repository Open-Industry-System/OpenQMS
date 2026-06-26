import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import UserManagementPage from "./UserManagementPage";

vi.mock("../../api/auth", () => ({
  listUsers: vi.fn().mockResolvedValue([
    { user_id: "u1", username: "alice", display_name: "Alice", email: "a@x.com", role_key: "admin", is_active: true, factories: [{ code: "F1" }] },
  ]),
  registerUser: vi.fn().mockResolvedValue({}),
}));
vi.mock("../../api/admin", () => ({
  listRoles: vi.fn().mockResolvedValue([{ id: "r1", role_key: "admin", name_zh: "管理员", name_en: "Admin", is_system: true, is_editable: false }]),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe("UserManagementPage", () => {
  it("lists users and opens create modal", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => expect(screen.getByText("createModalTitle")).toBeInTheDocument());
  });

  it("shows error on duplicate username", async () => {
    const { registerUser } = await import("../../api/auth");
    (registerUser as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ response: { data: { detail: "Username exists" } } });
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => expect(screen.getByText("createModalTitle")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("fields.username"), { target: { value: "dup" } });
    fireEvent.change(screen.getByLabelText("fields.password"), { target: { value: "ValidPass123!" } });
    // select role
    fireEvent.mouseDown(document.querySelector(".ant-select-selector") as HTMLElement);
    fireEvent.click(document.querySelector(".ant-select-item") as HTMLElement);
    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(screen.getByText("Username exists")).toBeInTheDocument());
  });
});
