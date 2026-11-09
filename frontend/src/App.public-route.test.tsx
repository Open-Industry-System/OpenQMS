import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import App from "./App";
import i18n from "./i18n";

const state = vi.hoisted(() => ({
  token: null as string | null,
  user: null as { username: string } | null,
  loading: false,
  login: vi.fn(),
  fetchUser: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("./store/authStore", () => ({
  useAuthStore: (selector: (value: typeof state) => unknown) => selector(state),
}));

vi.mock("./hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, isAdmin: false }),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AntdApp><App /></AntdApp>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  state.token = null;
  state.user = null;
  state.loading = false;
  vi.clearAllMocks();
  await i18n.changeLanguage("en-US");
});

describe("public route boundary", () => {
  it("renders the public home at root without authentication", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", {
      name: /turn quality data into actionable intelligence/i,
    })).toBeInTheDocument();
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("still redirects an unauthenticated dashboard request to login", async () => {
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
  });
});
