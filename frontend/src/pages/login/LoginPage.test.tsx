import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import LoginPage from "./LoginPage";
import i18n from "../../i18n";

const login = vi.hoisted(() => vi.fn());
vi.mock("../../store/authStore", () => ({
  useAuthStore: (selector: (state: { login: typeof login }) => unknown) => selector({ login }),
}));

const accounts = [
  { role: "Viewer", username: "viewer", password: "viewer-sentinel" },
  { role: "Quality engineer", username: "engineer", password: "engineer-sentinel" },
  { role: "Manager", username: "manager", password: "manager-sentinel" },
];

function configureMultiRoleDemo() {
  vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
  vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", accounts[0].username);
  vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", accounts[0].password);
  vi.stubEnv("VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS", JSON.stringify(accounts.slice(1).reverse().map(({ username, password }) => ({ username, password }))));
}

function renderLogin(path = "/login?demo=viewer") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AntdApp><LoginPage /></AntdApp>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  await i18n.changeLanguage("en-US");
});

describe("LoginPage public demo", () => {
  it("shows no credentials when public demo is disabled", () => {
    renderLogin();
    expect(screen.queryByText("viewer-sentinel")).not.toBeInTheDocument();
    expect(screen.queryByText("admin-sentinel")).not.toBeInTheDocument();
  });

  it("fails closed when enabled Viewer config is incomplete", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "viewer");
    renderLogin();
    expect(screen.queryByRole("button", { name: /use viewer account/i })).not.toBeInTheDocument();
  });

  it("keeps Viewer-only credentials limited to the demo URL", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");

    const { unmount } = renderLogin("/login");
    expect(screen.queryByText("readonly-demo")).not.toBeInTheDocument();
    unmount();

    renderLogin("/login?demo=viewer");
    expect(screen.getByText("readonly-demo")).toBeInTheDocument();
    expect(screen.getByText("public-readonly-password")).toBeInTheDocument();
    expect(screen.getByText(/viewer read-only demo/i)).toBeInTheDocument();
  });

  it.each(["/login", "/login?demo=viewer"])("shows only the three approved public accounts on %s when fully configured", (path) => {
    configureMultiRoleDemo();
    renderLogin(path);

    expect(screen.getByText("Shared writable demo")).toBeInTheDocument();
    for (const account of accounts) {
      expect(screen.getByText(account.role)).toBeInTheDocument();
      expect(screen.getByText(account.username)).toBeInTheDocument();
      expect(screen.getByText(account.password)).toBeInTheDocument();
    }
    expect(screen.queryByText("admin")).not.toBeInTheDocument();
    expect(screen.queryByText("groupadmin")).not.toBeInTheDocument();
  });

  it("prefills every multi-role account without invoking login", () => {
    configureMultiRoleDemo();
    renderLogin("/login");

    for (const account of accounts) {
      fireEvent.click(screen.getByRole("button", { name: `Use ${account.role} account` }));
      expect(screen.getByPlaceholderText("Username")).toHaveValue(account.username);
      expect(screen.getByPlaceholderText("Password")).toHaveValue(account.password);
    }
    expect(login).not.toHaveBeenCalled();
  });

  it("localizes the shared writable-demo warning", async () => {
    configureMultiRoleDemo();
    await i18n.changeLanguage("zh-CN");
    renderLogin("/login");

    expect(screen.getByText("其他访问者可以修改共享演示数据。请勿输入真实或个人数据。")).toBeInTheDocument();
  });
});
