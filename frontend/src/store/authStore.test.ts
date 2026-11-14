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

function jwt(payload: Record<string, unknown>) {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

const aliceFactory = { id: "alice-factory", code: "ALICE", name: "Alice", is_active: true };
const bobFactory = { id: "bob-factory", code: "BOB", name: "Bob", is_active: true };

function resetStore() {
  localStorage.clear();
  useAuthStore.setState({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
}

beforeEach(() => { vi.clearAllMocks(); resetStore(); });

describe("tryRefreshToken", () => {
  it("rotates both stored tokens and the Zustand access token on success", async () => {
    const oldAccessToken = jwt({ sub: "alice", exp: 9999999999 });
    const newAccessToken = jwt({ sub: "alice", exp: 9999999999 });
    localStorage.setItem("access_token", oldAccessToken);
    localStorage.setItem("refresh_token", "old-refresh");
    useAuthStore.setState({ token: oldAccessToken, user: oldUser });
    api.refreshToken.mockResolvedValue({ access_token: newAccessToken, refresh_token: "new-refresh" });

    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBe(newAccessToken);

    expect(localStorage.getItem("access_token")).toBe(newAccessToken);
    expect(localStorage.getItem("refresh_token")).toBe("new-refresh");
    expect(useAuthStore.getState().token).toBe(newAccessToken);
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
    const winnerAccessToken = jwt({ sub: "bob", exp: 9999999999 });
    api.refreshToken.mockReturnValue(request.promise);

    const losingRefresh = useAuthStore.getState().tryRefreshToken();
    localStorage.setItem("access_token", winnerAccessToken);
    localStorage.setItem("refresh_token", "winner-refresh");
    request.reject(new Error("refresh token already rotated"));

    await expect(losingRefresh).resolves.toBe(winnerAccessToken);
    expect(localStorage.getItem("access_token")).toBe(winnerAccessToken);
    expect(localStorage.getItem("refresh_token")).toBe("winner-refresh");
    expect(useAuthStore.getState()).toMatchObject({
      token: winnerAccessToken, user: null, factoryScope: null, factories: [], currentFactoryId: null,
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
  it("applies a same-account replay over the user present when hydration started", async () => {
    const accessA = jwt({ sub: oldUser.user_id, exp: 9999999999, generation: "A" });
    const accessB = jwt({ sub: oldUser.user_id, exp: 9999999999, generation: "B" });
    const refreshedUser: User = {
      ...oldUser,
      display_name: "Refreshed",
      factory_scope: { accessible_factory_ids: [aliceFactory.id], default_factory_id: aliceFactory.id },
      factories: [aliceFactory],
    };
    const request = deferred<{ user: User; requestAccessToken: string }>();
    localStorage.setItem("access_token", accessA);
    useAuthStore.setState({ token: accessA, user: oldUser, loading: false });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", accessB);
    useAuthStore.setState({ token: accessB });
    request.resolve({ user: refreshedUser, requestAccessToken: accessB });

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({
      token: accessB,
      user: refreshedUser,
      loading: false,
      factoryScope: refreshedUser.factory_scope,
      factories: refreshedUser.factories,
      currentFactoryId: aliceFactory.id,
    });
  });

  it("does not let an older same-token fetch failure log out a newer success", async () => {
    const accessToken = jwt({ sub: oldUser.user_id, exp: 9999999999 });
    const firstRequest = deferred<{ user: User; requestAccessToken: string }>();
    const secondRequest = deferred<{ user: User; requestAccessToken: string }>();
    const refreshedUser = { ...oldUser, display_name: "Refreshed" };
    localStorage.setItem("access_token", accessToken);
    localStorage.setItem("refresh_token", "refresh-token");
    useAuthStore.setState({ token: accessToken, user: null, loading: false });
    api.getMe
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);

    const firstFetch = useAuthStore.getState().fetchUser();
    const secondFetch = useAuthStore.getState().fetchUser();
    secondRequest.resolve({ user: refreshedUser, requestAccessToken: accessToken });
    await expect(secondFetch).resolves.toBeUndefined();
    firstRequest.reject(new Error("older request failed"));
    await expect(firstFetch).resolves.toBeUndefined();

    expect(localStorage.getItem("access_token")).toBe(accessToken);
    expect(localStorage.getItem("refresh_token")).toBe("refresh-token");
    expect(useAuthStore.getState()).toMatchObject({
      token: accessToken,
      user: refreshedUser,
      loading: false,
    });
  });

  it("does not let a stale /auth/me success overwrite a newer same-tab login", async () => {
    const request = deferred<{ user: User; requestAccessToken: string }>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", "bob-access");
    useAuthStore.setState({
      token: "bob-access", user: newUser, loading: false,
      factoryScope: { accessible_factory_ids: [bobFactory.id], default_factory_id: bobFactory.id },
      factories: [bobFactory], currentFactoryId: bobFactory.id,
    });
    request.resolve({ user: oldUser, requestAccessToken: "alice-access" });

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({
      token: "bob-access", user: newUser, loading: false,
      factoryScope: { accessible_factory_ids: [bobFactory.id], default_factory_id: bobFactory.id },
      factories: [bobFactory], currentFactoryId: bobFactory.id,
    });
  });

  it("does not let a stale /auth/me failure clear a newer same-tab login", async () => {
    const request = deferred<{ user: User; requestAccessToken: string }>();
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
    const request = deferred<{ user: User; requestAccessToken: string }>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser, currentFactoryId: "alice-factory" });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    const bobAccessToken = jwt({ sub: "bob", exp: 9999999999 });
    localStorage.setItem("access_token", bobAccessToken);
    request.resolve({ user: oldUser, requestAccessToken: "alice-access" });

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({
      token: bobAccessToken, user: null, factoryScope: null, factories: [], currentFactoryId: null,
    });
  });

  it("adopts a changed cross-tab token after a stale /auth/me failure", async () => {
    const request = deferred<{ user: User; requestAccessToken: string }>();
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({ token: "alice-access", user: oldUser, currentFactoryId: "alice-factory" });
    api.getMe.mockReturnValue(request.promise);

    const fetching = useAuthStore.getState().fetchUser();
    const bobAccessToken = jwt({ sub: "bob", exp: 9999999999 });
    localStorage.setItem("access_token", bobAccessToken);
    request.reject(new Error("old session expired"));

    await expect(fetching).resolves.toBeUndefined();
    expect(useAuthStore.getState()).toMatchObject({
      token: bobAccessToken, user: null, factoryScope: null, factories: [], currentFactoryId: null,
    });
  });
});

describe("idle storage and usable refresh tokens", () => {
  it("adopts an idle cross-tab access-token StorageEvent and clears Alice identity state", () => {
    localStorage.setItem("access_token", "alice-access");
    useAuthStore.setState({
      token: "alice-access", user: oldUser, loading: true,
      factoryScope: { accessible_factory_ids: [aliceFactory.id], default_factory_id: aliceFactory.id },
      factories: [aliceFactory], currentFactoryId: aliceFactory.id,
    });
    const bobAccessToken = jwt({ sub: "bob", exp: 9999999999 });
    localStorage.setItem("access_token", bobAccessToken);

    window.dispatchEvent(new StorageEvent("storage", {
      key: "access_token", oldValue: "alice-access", newValue: bobAccessToken,
    }));

    expect(useAuthStore.getState()).toMatchObject({
      token: bobAccessToken, user: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null,
    });
  });

  it.each([
    jwt({ sub: "alice", exp: 0 }),
    jwt({ sub: "alice" }),
    jwt({ sub: "alice", exp: "not-a-number" }),
  ])("clears a current refresh response with non-valid access token %s", async (accessToken) => {
    localStorage.setItem("access_token", jwt({ sub: "alice", exp: 9999999999 }));
    localStorage.setItem("refresh_token", "current-refresh");
    useAuthStore.setState({ token: localStorage.getItem("access_token"), user: oldUser });
    api.refreshToken.mockResolvedValue({ access_token: accessToken, refresh_token: "rotated-refresh" });

    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBeNull();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState()).toMatchObject({ token: null, user: null, loading: false });
  });

  it("does not delete a newer refresh generation when its stored access token is non-valid", async () => {
    const request = deferred<{ access_token: string; refresh_token: string }>();
    localStorage.setItem("access_token", jwt({ sub: "alice", exp: 9999999999 }));
    localStorage.setItem("refresh_token", "alice-refresh");
    useAuthStore.setState({ token: localStorage.getItem("access_token"), user: oldUser, factories: [aliceFactory], currentFactoryId: aliceFactory.id });
    api.refreshToken.mockReturnValue(request.promise);

    const refreshing = useAuthStore.getState().tryRefreshToken();
    localStorage.setItem("access_token", jwt({ sub: "bob", exp: 0 }));
    localStorage.setItem("refresh_token", "bob-refresh");
    request.reject(new Error("Alice refresh revoked"));

    const result = await refreshing;
    expect({
      result,
      storedAccessToken: localStorage.getItem("access_token"),
      storedRefreshToken: localStorage.getItem("refresh_token"),
      state: useAuthStore.getState(),
    }).toMatchObject({
      result: null,
      storedAccessToken: null,
      storedRefreshToken: "bob-refresh",
      state: { token: null, user: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null },
    });
  });
});
