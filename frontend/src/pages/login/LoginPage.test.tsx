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

describe("LoginPage public Viewer demo", () => {
  it("shows no credentials when public demo is disabled", () => {
    renderLogin();
    expect(screen.queryByText("demo-test-password")).not.toBeInTheDocument();
    expect(screen.queryByText(/default account/i)).not.toBeInTheDocument();
  });

  it("fails closed when enabled config is incomplete", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "viewer");
    renderLogin();
    expect(screen.queryByRole("button", { name: /use viewer account/i })).not.toBeInTheDocument();
  });

  it("shows configured Viewer credentials only on the demo route", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");
    renderLogin();
    expect(screen.getByText("readonly-demo")).toBeInTheDocument();
    expect(screen.getByText("public-readonly-password")).toBeInTheDocument();
    expect(screen.getByText(/read-only demo/i)).toBeInTheDocument();
  });

  it("fills but does not submit the Viewer credentials", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /use viewer account/i }));
    expect(screen.getByPlaceholderText("Username")).toHaveValue("readonly-demo");
    expect(screen.getByPlaceholderText("Password")).toHaveValue("public-readonly-password");
    expect(login).not.toHaveBeenCalled();
  });

  it("does not expose demo credentials on a normal login URL", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");
    renderLogin("/login");
    expect(screen.queryByText("public-readonly-password")).not.toBeInTheDocument();
  });
});
