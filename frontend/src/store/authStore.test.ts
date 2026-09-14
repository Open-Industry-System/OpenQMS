import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "../types";

const api = vi.hoisted(() => ({ login: vi.fn(), getMe: vi.fn(), refreshToken: vi.fn() }));
vi.mock("../api/auth", () => api);
const { useAuthStore } = await import("./authStore");

const oldUser: User = {
  user_id: "old-user", username: "old", display_name: "Old", email: null,
  role_key: "quality_engineer", permissions: {}, product_lines: [],
  bypass_row_level_security: false, is_active: true,
};
const newUser: User = {
  user_id: "new-user", username: "new", display_name: "New", email: null,
  role_key: "quality_engineer", permissions: {}, product_lines: [],
  bypass_row_level_security: false, is_active: true,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function resetStore() {
  localStorage.clear();
  useAuthStore.setState({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
}

beforeEach(() => { vi.clearAllMocks(); resetStore(); });

describe("tryRefreshToken", () => {
  it("rotates both stored tokens and the Zustand access token on success", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    useAuthStore.setState({ token: "old-access", user: oldUser });
    api.refreshToken.mockResolvedValue({ access_token: "new-access", refresh_token: "new-refresh" });

    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBe("new-access");

    expect(localStorage.getItem("access_token")).toBe("new-access");
    expect(localStorage.getItem("refresh_token")).toBe("new-refresh");
    expect(useAuthStore.getState().token).toBe("new-access");
    expect(useAuthStore.getState().user).toBe(oldUser);
  });

  it("clears all authentication state after a real refresh failure", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    localStorage.setItem("current_factory_id", "factory-1");
    useAuthStore.setState({ token: "old-access", user: oldUser, currentFactoryId: "factory-1" });
    api.refreshToken.mockRejectedValue(new Error("revoked"));

    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBeNull();

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(localStorage.getItem("current_factory_id")).toBeNull();
    expect(useAuthStore.getState()).toMatchObject({ token: null, user: null, loading: false, currentFactoryId: null, factories: [] });
  });

  it("does not let a stale refresh success overwrite a newer login", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    useAuthStore.setState({ token: "old-access", user: oldUser });
    const request = deferred<{ access_token: string; refresh_token: string }>();
    api.refreshToken.mockReturnValue(request.promise);

    const refreshing = useAuthStore.getState().tryRefreshToken();
    localStorage.setItem("access_token", "login-access");
    localStorage.setItem("refresh_token", "login-refresh");
    useAuthStore.setState({ token: "login-access", user: newUser });
    request.resolve({ access_token: "stale-access", refresh_token: "stale-refresh" });

    await expect(refreshing).resolves.toBe("login-access");
    expect(localStorage.getItem("access_token")).toBe("login-access");
    expect(localStorage.getItem("refresh_token")).toBe("login-refresh");
    expect(useAuthStore.getState()).toMatchObject({ token: "login-access", user: newUser });
  });

  it("does not let a stale refresh failure clear a newer login", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    useAuthStore.setState({ token: "old-access", user: oldUser });
    const request = deferred<{ access_token: string; refresh_token: string }>();
    api.refreshToken.mockReturnValue(request.promise);

    const refreshing = useAuthStore.getState().tryRefreshToken();
    localStorage.setItem("access_token", "login-access");
    localStorage.setItem("refresh_token", "login-refresh");
    useAuthStore.setState({ token: "login-access", user: newUser });
    request.reject(new Error("revoked"));

    await expect(refreshing).resolves.toBe("login-access");
    expect(localStorage.getItem("access_token")).toBe("login-access");
    expect(localStorage.getItem("refresh_token")).toBe("login-refresh");
    expect(useAuthStore.getState()).toMatchObject({ token: "login-access", user: newUser });
  });

  it("clears identity-derived state when adopting the winning tab's access token", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    localStorage.setItem("current_factory_id", "old-factory");
    useAuthStore.setState({
      token: "old-access", user: oldUser,
      factoryScope: { accessible_factory_ids: ["old-factory"], default_factory_id: "old-factory" },
      factories: [{ id: "old-factory", code: "OLD", name: "Old", is_active: true }],
      currentFactoryId: "old-factory",
    });
    const request = deferred<{ access_token: string; refresh_token: string }>();
    api.refreshToken.mockReturnValue(request.promise);

    const losingRefresh = useAuthStore.getState().tryRefreshToken();
    localStorage.setItem("access_token", "winner-access");
    localStorage.setItem("refresh_token", "winner-refresh");
    request.reject(new Error("refresh token already rotated"));

    await expect(losingRefresh).resolves.toBe("winner-access");
    expect(localStorage.getItem("access_token")).toBe("winner-access");
    expect(localStorage.getItem("refresh_token")).toBe("winner-refresh");
    expect(useAuthStore.getState()).toMatchObject({
      token: "winner-access", user: null, factoryScope: null, factories: [], currentFactoryId: null,
    });
  });

  it("does not resurrect tokens after logout during a refresh", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    useAuthStore.setState({ token: "old-access", user: oldUser });
    const request = deferred<{ access_token: string; refresh_token: string }>();
    api.refreshToken.mockReturnValue(request.promise);

    const refreshing = useAuthStore.getState().tryRefreshToken();
    useAuthStore.getState().logout();
    request.resolve({ access_token: "stale-access", refresh_token: "stale-refresh" });

    await expect(refreshing).resolves.toBeNull();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState()).toMatchObject({ token: null, user: null });
  });
});

describe("fetchUser generation guard", () => {
  it("does not let a stale /auth/me success overwrite a newer same-tab login", async () => {
    const request = deferred<User>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", "bob-access");
    useAuthStore.setState({ token: "bob-access", user: newUser });
    request.resolve(oldUser);

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({ token: "bob-access", user: newUser });
  });

  it("does not let a stale /auth/me failure clear a newer same-tab login", async () => {
    const request = deferred<User>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", "bob-access");
    useAuthStore.setState({ token: "bob-access", user: newUser });
    request.reject(new Error("old session expired"));

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({ token: "bob-access", user: newUser });
  });

  it("adopts a changed cross-tab token after a stale /auth/me success", async () => {
    const request = deferred<User>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser, currentFactoryId: "alice-factory" });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", "bob-access");
    request.resolve(oldUser);

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({
      token: "bob-access", user: null, factoryScope: null, factories: [], currentFactoryId: null,
    });
  });

  it("adopts a changed cross-tab token after a stale /auth/me failure", async () => {
    const request = deferred<User>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser, currentFactoryId: "alice-factory" });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", "bob-access");
    request.reject(new Error("old session expired"));

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({
      token: "bob-access", user: null, factoryScope: null, factories: [], currentFactoryId: null,
    });
  });
});
