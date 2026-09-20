import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getMe: vi.fn(),
  login: vi.fn(),
  refreshToken: vi.fn(),
}));

vi.mock("../api/auth", () => ({
  getMe: auth.getMe,
  login: auth.login,
  refreshToken: auth.refreshToken,
}));

import { useAuthStore } from "./authStore";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function loginResponse(name: string) {
  return {
    access_token: `${name}-access-token`,
    refresh_token: `${name}-refresh-token`,
    user: {
      user_id: `${name}-id`,
      username: name,
      display_name: name,
      email: null,
      role_key: "viewer",
      permissions: {},
      product_lines: [],
      bypass_row_level_security: false,
      is_active: true,
      factory_scope: { accessible_factory_ids: [], default_factory_id: `${name}-factory` },
      factories: [],
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  useAuthStore.setState({
    user: null,
    token: null,
    loading: false,
    factoryScope: null,
    factories: [],
    currentFactoryId: null,
  });
});

describe("authStore refresh coordination", () => {
  it("shares one pending refresh and stores its successful token pair", async () => {
    localStorage.setItem("refresh_token", "old-refresh-token");
    const refresh = deferred<{ access_token: string; refresh_token: string }>();
    auth.refreshToken.mockReturnValue(refresh.promise);

    const first = useAuthStore.getState().tryRefreshToken();
    const second = useAuthStore.getState().tryRefreshToken();

    expect(first).toBe(second);
    expect(auth.refreshToken).toHaveBeenCalledOnce();
    expect(auth.refreshToken).toHaveBeenCalledWith("old-refresh-token");

    refresh.resolve({
      access_token: "new-access-token",
      refresh_token: "new-refresh-token",
    });

    await expect(Promise.all([first, second])).resolves.toEqual([
      "new-access-token",
      "new-access-token",
    ]);
    expect(localStorage.getItem("access_token")).toBe("new-access-token");
    expect(localStorage.getItem("refresh_token")).toBe("new-refresh-token");
    expect(useAuthStore.getState().token).toBe("new-access-token");
  });

  it("shares a rejected refresh, logs out, and permits a later refresh", async () => {
    localStorage.setItem("access_token", "stale-access-token");
    localStorage.setItem("refresh_token", "stale-refresh-token");
    localStorage.setItem("current_factory_id", "stale-factory");
    useAuthStore.setState({ token: "stale-access-token", currentFactoryId: "stale-factory" });
    const refresh = deferred<{ access_token: string; refresh_token: string }>();
    auth.refreshToken.mockReturnValue(refresh.promise);

    const first = useAuthStore.getState().tryRefreshToken();
    const second = useAuthStore.getState().tryRefreshToken();
    refresh.reject(new Error("refresh rejected"));

    await expect(Promise.all([first, second])).resolves.toEqual([null, null]);
    expect(auth.refreshToken).toHaveBeenCalledOnce();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(localStorage.getItem("current_factory_id")).toBeNull();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().currentFactoryId).toBeNull();

    localStorage.setItem("refresh_token", "later-refresh-token");
    auth.refreshToken.mockResolvedValueOnce({
      access_token: "later-access-token",
      refresh_token: "later-rotated-token",
    });

    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBe("later-access-token");
    expect(auth.refreshToken).toHaveBeenCalledTimes(2);
    expect(auth.refreshToken).toHaveBeenLastCalledWith("later-refresh-token");
  });

  it("returns null without calling the API when no refresh token exists", async () => {
    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBeNull();
    expect(auth.refreshToken).not.toHaveBeenCalled();
  });

  it("does not let an older refresh success overwrite a newer login", async () => {
    localStorage.setItem("access_token", "old-access-token");
    localStorage.setItem("refresh_token", "old-refresh-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldRefresh = deferred<{ access_token: string; refresh_token: string }>();
    auth.refreshToken.mockReturnValue(oldRefresh.promise);
    const pending = useAuthStore.getState().tryRefreshToken();

    auth.login.mockResolvedValue(loginResponse("new-user"));
    await useAuthStore.getState().login("new-user", "password");
    oldRefresh.resolve({ access_token: "old-rotated-access", refresh_token: "old-rotated-refresh" });

    await expect(pending).resolves.toBeNull();
    expect(localStorage.getItem("access_token")).toBe("new-user-access-token");
    expect(localStorage.getItem("refresh_token")).toBe("new-user-refresh-token");
    expect(useAuthStore.getState().token).toBe("new-user-access-token");
    expect(useAuthStore.getState().user?.username).toBe("new-user");
  });

  it("does not let an older refresh failure log out a newer login", async () => {
    localStorage.setItem("access_token", "old-access-token");
    localStorage.setItem("refresh_token", "old-refresh-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldRefresh = deferred<{ access_token: string; refresh_token: string }>();
    auth.refreshToken.mockReturnValue(oldRefresh.promise);
    const pending = useAuthStore.getState().tryRefreshToken();

    auth.login.mockResolvedValue(loginResponse("new-user"));
    await useAuthStore.getState().login("new-user", "password");
    oldRefresh.reject(new Error("old refresh failed"));

    await expect(pending).resolves.toBeNull();
    expect(localStorage.getItem("access_token")).toBe("new-user-access-token");
    expect(localStorage.getItem("refresh_token")).toBe("new-user-refresh-token");
    expect(useAuthStore.getState().token).toBe("new-user-access-token");
    expect(useAuthStore.getState().user?.username).toBe("new-user");
  });

  it("does not restore a session when refresh succeeds after logout", async () => {
    localStorage.setItem("access_token", "old-access-token");
    localStorage.setItem("refresh_token", "old-refresh-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldRefresh = deferred<{ access_token: string; refresh_token: string }>();
    auth.refreshToken.mockReturnValue(oldRefresh.promise);
    const pending = useAuthStore.getState().tryRefreshToken();

    useAuthStore.getState().logout();
    oldRefresh.resolve({ access_token: "resurrected-access", refresh_token: "resurrected-refresh" });

    await expect(pending).resolves.toBeNull();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("starts a separate refresh for a newer session and old cleanup cannot clear it", async () => {
    localStorage.setItem("refresh_token", "old-refresh-token");
    const oldRefresh = deferred<{ access_token: string; refresh_token: string }>();
    const newRefresh = deferred<{ access_token: string; refresh_token: string }>();
    auth.refreshToken
      .mockReturnValueOnce(oldRefresh.promise)
      .mockReturnValueOnce(newRefresh.promise);
    const oldPending = useAuthStore.getState().tryRefreshToken();

    auth.login.mockResolvedValue(loginResponse("new-user"));
    await useAuthStore.getState().login("new-user", "password");
    const newPending = useAuthStore.getState().tryRefreshToken();
    expect(newPending).not.toBe(oldPending);
    expect(auth.refreshToken).toHaveBeenCalledTimes(2);
    expect(auth.refreshToken).toHaveBeenLastCalledWith("new-user-refresh-token");

    oldRefresh.resolve({ access_token: "old-rotated-access", refresh_token: "old-rotated-refresh" });
    await expect(oldPending).resolves.toBeNull();
    const sameNewPending = useAuthStore.getState().tryRefreshToken();
    expect(sameNewPending).toBe(newPending);
    expect(auth.refreshToken).toHaveBeenCalledTimes(2);

    newRefresh.resolve({ access_token: "new-rotated-access", refresh_token: "new-rotated-refresh" });
    await expect(Promise.all([newPending, sameNewPending])).resolves.toEqual([
      "new-rotated-access",
      "new-rotated-access",
    ]);
  });

  it("ignores a stale fetchUser success after a newer login", async () => {
    localStorage.setItem("access_token", "old-access-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldMe = deferred<ReturnType<typeof loginResponse>["user"]>();
    auth.getMe.mockReturnValue(oldMe.promise);
    const pending = useAuthStore.getState().fetchUser();

    auth.login.mockResolvedValue(loginResponse("new-user"));
    await useAuthStore.getState().login("new-user", "password");
    oldMe.resolve(loginResponse("old-user").user);
    await pending;

    expect(useAuthStore.getState().user?.username).toBe("new-user");
    expect(useAuthStore.getState().token).toBe("new-user-access-token");
    expect(useAuthStore.getState().loading).toBe(false);
  });

  it("ignores a stale fetchUser failure after a newer login", async () => {
    localStorage.setItem("access_token", "old-access-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldMe = deferred<ReturnType<typeof loginResponse>["user"]>();
    auth.getMe.mockReturnValue(oldMe.promise);
    const pending = useAuthStore.getState().fetchUser();

    auth.login.mockResolvedValue(loginResponse("new-user"));
    await useAuthStore.getState().login("new-user", "password");
    oldMe.reject(new Error("old getMe failed"));
    await pending;

    expect(useAuthStore.getState().user?.username).toBe("new-user");
    expect(useAuthStore.getState().token).toBe("new-user-access-token");
    expect(localStorage.getItem("access_token")).toBe("new-user-access-token");
    expect(useAuthStore.getState().loading).toBe(false);
  });

  it("invalidates an older refresh as soon as a new login starts", async () => {
    localStorage.setItem("access_token", "old-access-token");
    localStorage.setItem("refresh_token", "old-refresh-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldRefresh = deferred<{ access_token: string; refresh_token: string }>();
    const newLogin = deferred<ReturnType<typeof loginResponse>>();
    auth.refreshToken.mockReturnValue(oldRefresh.promise);
    auth.login.mockReturnValue(newLogin.promise);

    const oldPending = useAuthStore.getState().tryRefreshToken();
    const loginPending = useAuthStore.getState().login("new-user", "password");
    await vi.waitFor(() => expect(auth.login).toHaveBeenCalledOnce());

    oldRefresh.resolve({ access_token: "old-rotated-access", refresh_token: "old-rotated-refresh" });
    await expect(oldPending).resolves.toBeNull();
    expect(localStorage.getItem("access_token")).toBe("old-access-token");

    newLogin.resolve(loginResponse("new-user"));
    await loginPending;
    expect(useAuthStore.getState().token).toBe("new-user-access-token");
    expect(localStorage.getItem("refresh_token")).toBe("new-user-refresh-token");
  });

  it("clears loading when fetchUser becomes stale after an external token change", async () => {
    localStorage.setItem("access_token", "old-access-token");
    useAuthStore.setState({ token: "old-access-token" });
    const oldMe = deferred<ReturnType<typeof loginResponse>["user"]>();
    auth.getMe.mockReturnValue(oldMe.promise);

    const pending = useAuthStore.getState().fetchUser();
    expect(useAuthStore.getState().loading).toBe(true);
    localStorage.setItem("access_token", "external-new-access-token");
    oldMe.resolve(loginResponse("old-user").user);
    await pending;

    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().loading).toBe(false);
  });
});
