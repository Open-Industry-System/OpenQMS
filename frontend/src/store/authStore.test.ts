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
});
