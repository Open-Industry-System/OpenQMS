import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import UserManagementPage from "./UserManagementPage";
import {
  listUsers,
  registerUser,
  updateUser,
  deleteUser,
  listAssignableRoles,
  listFactories,
} from "../../api/auth";
import type { User } from "../../types";

const users = [
  {
    user_id: "u1",
    username: "alice",
    display_name: "Alice",
    email: "a@x.com",
    role_key: "admin",
    is_active: true,
    permissions: {},
    product_lines: [],
    bypass_row_level_security: false,
    factories: [{ id: "f1", code: "F1", name: "F1", is_active: true }],
    factory_scope: { accessible_factory_ids: ["f1"], default_factory_id: "f1" },
  },
  {
    user_id: "u2",
    username: "bob",
    display_name: "Bob",
    email: null,
    role_key: "viewer",
    is_active: false,
    permissions: {},
    product_lines: [],
    bypass_row_level_security: false,
    factories: [],
    factory_scope: null,
  },
];

vi.mock("../../api/auth", () => ({
  listUsers: vi.fn(),
  registerUser: vi.fn(),
  updateUser: vi.fn(),
  deleteUser: vi.fn(),
  listAssignableRoles: vi.fn(),
  listFactories: vi.fn(),
}));

vi.mock("../../api/admin", () => ({ listRoles: vi.fn().mockResolvedValue([]) }));
vi.mock("../../store/authStore", () => ({
  useAuthStore: vi.fn((selector: any) =>
    selector ? selector({ user: { user_id: "me" } }) : { user: { user_id: "me" } }
  ),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const mockedListUsers = vi.mocked(listUsers);
const mockedRegisterUser = vi.mocked(registerUser);
const mockedUpdateUser = vi.mocked(updateUser);
const mockedDeleteUser = vi.mocked(deleteUser);
const mockedListAssignableRoles = vi.mocked(listAssignableRoles);
const mockedListFactories = vi.mocked(listFactories);

// helper: find the currently-open dropdown option whose text exactly matches
function optionWithText(text: string): HTMLElement | null {
  return (
    (Array.from(document.querySelectorAll(".ant-select-item-option")) as HTMLElement[]).find(
      (o) => o.textContent === text
    ) || null
  );
}

describe("UserManagementPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListUsers.mockResolvedValue(users);
    mockedRegisterUser.mockResolvedValue({} as User);
    mockedUpdateUser.mockResolvedValue(users[0]);
    mockedDeleteUser.mockResolvedValue(undefined);
    mockedListAssignableRoles.mockResolvedValue([
      { role_key: "admin", name_zh: "管理员", name_en: "Admin" },
      { role_key: "viewer", name_zh: "只读", name_en: "Viewer" },
    ]);
    mockedListFactories.mockResolvedValue([
      { id: "f1", code: "F1", name: "F1", is_active: true },
      { id: "f2", code: "F2", name: "F2", is_active: true },
    ]);
  });

  it("lists users and opens create modal", async () => {
    render(
      <App>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </App>
    );
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => expect(screen.getByText("createModalTitle")).toBeInTheDocument());
  });

  it("opens edit modal prefilled and submits updateUser", async () => {
    render(
      <App>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </App>
    );
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    // click the Edit button on bob's row (viewer row)
    const editButtons = screen.getAllByText("edit");
    fireEvent.click(editButtons[editButtons.length - 1]);
    await waitFor(() => expect(screen.getByText("editModalTitle")).toBeInTheDocument());
    // change display_name
    fireEvent.change(screen.getByLabelText("fields.display_name"), { target: { value: "Bobby" } });
    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(mockedUpdateUser).toHaveBeenCalled());
    const [, payload] = mockedUpdateUser.mock.calls[0];
    expect(payload.display_name).toBe("Bobby");
  });

  it("deactivate button calls updateUser with is_active true (reactivate)", async () => {
    render(
      <App>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </App>
    );
    await waitFor(() => expect(screen.getByText("bob")).toBeInTheDocument());
    fireEvent.click(screen.getByText("activate"));
    await waitFor(() => expect(mockedUpdateUser).toHaveBeenCalledWith("u2", { is_active: true }));
  });

  it("edit submits factory_ids + default_factory_id in a single updateUser", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </App>
    );
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    // open edit for alice (first row)
    fireEvent.click(screen.getAllByText("edit")[0]);
    await waitFor(() => expect(screen.getByText("editModalTitle")).toBeInTheDocument());

    // edit modal selects in DOM order: role_key=0, factory_ids=1, default_factory_id=2
    const selectors = document.querySelectorAll(".ant-select-selector");
    const factoryIdsSel = selectors[1] as HTMLElement;
    const defaultSel = selectors[2] as HTMLElement;

    // add F2 to factory_ids (alice already has F1)
    await user.click(factoryIdsSel);
    await waitFor(() => expect(optionWithText("F2 - F2")).not.toBeNull());
    await user.click(optionWithText("F2 - F2")!);
    // blur the multi-select by clicking a neutral input so its dropdown closes
    await user.click(screen.getByLabelText("fields.display_name"));

    // open default_factory_id (now offers F2 because factory_ids includes f2) and pick F2
    await user.click(defaultSel);
    await waitFor(() => expect(optionWithText("F2 - F2")).not.toBeNull());
    // the multi-select dropdown remains in the DOM portal; pick the F2 option that
    // belongs to the default_factory_id dropdown (the last rendered one).
    const allF2 = Array.from(document.querySelectorAll(".ant-select-item-option")).filter(
      (o) => o.textContent === "F2 - F2"
    ) as HTMLElement[];
    await user.click(allF2[allF2.length - 1]);

    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(mockedUpdateUser).toHaveBeenCalled());
    const [userId, payload] = mockedUpdateUser.mock.calls[0];
    expect(userId).toBe("u1");
    expect(payload.factory_ids).toEqual(["f1", "f2"]);
    expect(payload.default_factory_id).toBe("f2");
  });

  it("delete opens confirm and calls deleteUser on confirm", async () => {
    render(
      <App>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </App>
    );
    await waitFor(() => expect(screen.getByText("bob")).toBeInTheDocument());
    // bob is the 2nd row; both rows have a delete button
    fireEvent.click(screen.getAllByText("delete")[1]);
    await waitFor(() => expect(screen.getByText("OK")).toBeInTheDocument());
    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(mockedDeleteUser).toHaveBeenCalledWith("u2"));
  });

  it("self-row deactivate is disabled", async () => {
    // current user id is "me"; render a row with user_id "me"
    mockedListUsers.mockResolvedValueOnce([
      {
        user_id: "me",
        username: "self",
        display_name: "Self",
        email: null,
        role_key: "admin",
        is_active: true,
        permissions: {},
        product_lines: [],
        bypass_row_level_security: false,
        factories: [],
        factory_scope: null,
      },
    ]);
    render(
      <App>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </App>
    );
    await waitFor(() => expect(screen.getByText("self")).toBeInTheDocument());
    const deactivateBtn = screen.getByText("deactivate").closest("button");
    expect(deactivateBtn).toBeDisabled();
  });
});
