import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import App from "./App";
import i18n from "./i18n";
import { useAuthStore } from "./store/authStore";

vi.mock("./hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, isAdmin: false }),
}));

function jwt(payload: unknown) {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

function rawJwt(payload: string) {
  return `header.${btoa(payload)}.signature`;
}

function renderAt(path: string, strict = false) {
  const app = (
    <MemoryRouter initialEntries={[path]}>
      <AntdApp><App /></AntdApp>
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{app}</StrictMode> : app);
}

beforeEach(async () => {
  localStorage.clear();
  vi.clearAllMocks();
  const logout = vi.fn(() => {
    useAuthStore.setState({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
  });
  useAuthStore.setState({
    user: null,
    token: null,
    loading: false,
    factoryScope: null,
    factories: [],
    currentFactoryId: null,
    fetchUser: vi.fn(),
    tryRefreshToken: vi.fn(),
    logout,
  });
  await i18n.changeLanguage("en-US");
});

describe("protected route bootstrap", () => {
  it("shows loading and refreshes an expired token before fetching the user", async () => {
    const refresh = vi.fn(() => new Promise<string | null>(() => {}));
    const fetchUser = vi.fn();
    useAuthStore.setState({ token: jwt({ exp: 0 }), tryRefreshToken: refresh, fetchUser });

    renderAt("/dashboard");

    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(fetchUser).not.toHaveBeenCalled();
  });

  it("redirects to login after an expired token cannot refresh", async () => {
    const refresh = vi.fn().mockResolvedValue(null);
    const logout = useAuthStore.getState().logout;
    useAuthStore.setState({ token: jwt({ exp: 0 }), tryRefreshToken: refresh });

    renderAt("/dashboard");

    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
  });

  it("refreshes one expired token only once under StrictMode", async () => {
    const refresh = vi.fn(() => new Promise<string | null>(() => {}));
    useAuthStore.setState({ token: jwt({ exp: 0 }), tryRefreshToken: refresh });

    renderAt("/dashboard", true);

    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  });

  it.each(["not-a-jwt", jwt([]), jwt({}), rawJwt('{"exp":1e9999}')])("fails closed for malformed token %s", async (token) => {
    const logout = useAuthStore.getState().logout;
    const refresh = useAuthStore.getState().tryRefreshToken;
    useAuthStore.setState({ token });

    renderAt("/dashboard");

    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("fetches the user while a valid token has no user", async () => {
    const fetchUser = vi.fn();
    useAuthStore.setState({ token: jwt({ exp: Math.floor(Date.now() / 1000) + 3600 }), fetchUser });

    renderAt("/dashboard");

    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    await waitFor(() => expect(fetchUser).toHaveBeenCalledOnce());
  });
});

describe("public route boundary", () => {
  it("renders the public home at root without authentication", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: /turn quality data into actionable intelligence/i })).toBeInTheDocument();
    expect(useAuthStore.getState().fetchUser).not.toHaveBeenCalled();
  });

  it("keeps the public home available to authenticated users", async () => {
    useAuthStore.setState({ token: "present" });
    renderAt("/");
    expect(await screen.findByRole("heading", { name: /turn quality data into actionable intelligence/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Enter system" })[0]).toHaveAttribute("href", "/dashboard");
    expect(useAuthStore.getState().fetchUser).not.toHaveBeenCalled();
  });

  it("still redirects an unauthenticated dashboard request to login", async () => {
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
  });
});
