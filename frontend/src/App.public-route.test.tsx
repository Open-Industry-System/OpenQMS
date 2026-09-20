import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import App from "./App";
import i18n from "./i18n";

const state = vi.hoisted(() => ({
  generation: 0,
  token: null as string | null,
  user: null as any,
  loading: false,
  login: vi.fn(),
  fetchUser: vi.fn(),
  tryRefreshToken: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("./store/authStore", () => ({
  getAuthSessionGeneration: () => state.generation,
  useAuthStore: (selector: (value: typeof state) => unknown) => selector(state),
}));

vi.mock("./hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, isAdmin: false }),
}));

function jwt(payload: Record<string, unknown>) {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function routeAt(path: string) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <AntdApp><App /></AntdApp>
    </MemoryRouter>
  );
}

function renderAt(path: string, strict = false) {
  const route = routeAt(path);
  return render(strict ? <StrictMode>{route}</StrictMode> : route);
}

beforeEach(async () => {
  localStorage.clear();
  state.generation = 0;
  state.token = null;
  state.user = null;
  state.loading = false;
  vi.clearAllMocks();
  state.tryRefreshToken.mockReset();
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

  it("refreshes an expired structurally valid token before fetching the user", async () => {
    state.tryRefreshToken.mockResolvedValue(jwt({ exp: Math.floor(Date.now() / 1000) + 3600 }));
    state.token = "header.eyJleHAiOjB9.signature";
    renderAt("/dashboard");
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /login/i })).not.toBeInTheDocument();
    await waitFor(() => expect(state.tryRefreshToken).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();
    expect(state.logout).not.toHaveBeenCalled();
  });

  it("logs out when a successful refresh returns an invalid token after rotation", async () => {
    localStorage.setItem("refresh_token", "old-refresh-token");
    state.tryRefreshToken.mockImplementation(async () => {
      localStorage.setItem("refresh_token", "rotated-refresh-token");
      return "not-a-valid-jwt";
    });
    state.token = "header.eyJleHAiOjB9.signature";
    renderAt("/dashboard");

    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
  });

  it("refetches an existing user after refreshing an expired token", async () => {
    const refreshedToken = jwt({ exp: Math.floor(Date.now() / 1000) + 3600 });
    state.user = { username: "existing-user" };
    state.token = "header.eyJleHAiOjB9.signature";
    state.tryRefreshToken.mockImplementation(async () => {
      state.token = refreshedToken;
      return refreshedToken;
    });
    renderAt("/dashboard");

    await waitFor(() => expect(state.fetchUser).toHaveBeenCalledOnce());
    expect(state.logout).not.toHaveBeenCalled();
  });

  it("logs out when an expired token cannot be refreshed", async () => {
    state.tryRefreshToken.mockResolvedValue(null);
    state.token = "header.eyJleHAiOjB9.signature";
    const view = renderAt("/dashboard");
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();

    state.token = null;
    view.rerender(routeAt("/dashboard"));
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
  });

  it("ignores a stale null refresh result after the session changes", async () => {
    const refresh = deferred<string | null>();
    state.tryRefreshToken.mockReturnValue(refresh.promise);
    state.token = "header.eyJleHAiOjB9.signature";
    renderAt("/dashboard");
    await waitFor(() => expect(state.tryRefreshToken).toHaveBeenCalledOnce());

    state.generation = 1;
    state.token = jwt({ exp: Math.floor(Date.now() / 1000) + 3600 });
    refresh.resolve(null);
    await refresh.promise;
    await Promise.resolve();

    expect(state.logout).not.toHaveBeenCalled();
  });

  it("ignores a stale refresh rejection after the session changes", async () => {
    const refresh = deferred<string | null>();
    state.tryRefreshToken.mockReturnValue(refresh.promise);
    state.token = "header.eyJleHAiOjB9.signature";
    renderAt("/dashboard");
    await waitFor(() => expect(state.tryRefreshToken).toHaveBeenCalledOnce());

    state.generation = 1;
    state.token = jwt({ exp: Math.floor(Date.now() / 1000) + 3600 });
    refresh.reject(new Error("old refresh failed"));
    await expect(refresh.promise).rejects.toThrow("old refresh failed");
    await Promise.resolve();

    expect(state.logout).not.toHaveBeenCalled();
  });

  it("does not refresh the same expired token twice under StrictMode", async () => {
    state.tryRefreshToken.mockReturnValue(new Promise<string | null>(() => undefined));
    state.token = "header.eyJleHAiOjB9.signature";
    renderAt("/dashboard", true);
    await waitFor(() => expect(state.tryRefreshToken).toHaveBeenCalled());
    expect(state.tryRefreshToken).toHaveBeenCalledOnce();
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("redirects a malformed token to login without fetching the user", async () => {
    state.token = "not-a-jwt";
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("redirects a token with a non-object payload to login without fetching the user", async () => {
    state.token = `header.${btoa("null")}.signature`;
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("redirects a token without an expiry claim to login without fetching the user", async () => {
    state.token = jwt({});
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("redirects a token with a nonnumeric expiry claim to login without fetching the user", async () => {
    state.token = jwt({ exp: "tomorrow" });
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("redirects a token with a non-finite expiry claim to login without fetching the user", async () => {
    state.token = `header.${btoa('{"exp":1e400}')}.signature`;
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("fetches the user and shows loading for a valid token without a user", async () => {
    state.token = jwt({ exp: Math.floor(Date.now() / 1000) + 3600 });
    renderAt("/dashboard");
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    await waitFor(() => expect(state.fetchUser).toHaveBeenCalledOnce());
    expect(state.logout).not.toHaveBeenCalled();
  });
});
