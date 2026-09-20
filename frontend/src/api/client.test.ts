import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  generation: 0,
  getState: vi.fn(),
}));

vi.mock("../store/authStore", () => ({
  getAuthSessionGeneration: () => auth.generation,
  useAuthStore: { getState: auth.getState },
}));

async function loadClient() {
  return (await import("./client")).default;
}

function unauthorized(config: any) {
  return Promise.reject({ config, response: { status: 401 } });
}

function forbidden(config: any) {
  return Promise.reject({ config, response: { status: 403 } });
}

function deferredAdapter() {
  let config: any;
  let rejectRequest!: (error: unknown) => void;
  const adapter = vi.fn((requestConfig: any) => {
    config = requestConfig;
    return new Promise<never>((_resolve, reject) => {
      rejectRequest = reject;
    });
  });
  return {
    adapter,
    reject401: () => rejectRequest({ config, response: { status: 401 } }),
  };
}

describe("client 401 refresh handling", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    auth.generation = 0;
    localStorage.clear();
  });

  it("rejects a protected request and logs out when refresh returns null", async () => {
    const logout = vi.fn();
    const tryRefreshToken = vi.fn().mockResolvedValue(null);
    auth.getState.mockReturnValue({ logout, tryRefreshToken });
    const client = await loadClient();
    client.defaults.adapter = (config) => Promise.reject({ config, response: { status: 401 } });

    await expect(client.get("/protected")).rejects.toMatchObject({ response: { status: 401 } });
    expect(tryRefreshToken).toHaveBeenCalledOnce();
    expect(logout).toHaveBeenCalledOnce();
  });

  it("preserves queued errors and does not replay failed non-idempotent work in a later refresh", async () => {
    const logout = vi.fn();
    let resolveRefresh!: (token: string | null) => void;
    const pendingRefresh = new Promise<string | null>((resolve) => { resolveRefresh = resolve; });
    const tryRefreshToken = vi.fn()
      .mockReturnValueOnce(pendingRefresh)
      .mockResolvedValueOnce("later-token");
    auth.getState.mockReturnValue({ logout, tryRefreshToken });
    const client = await loadClient();
    const invocationCount = new Map<string, number>();
    client.defaults.adapter = (config) => {
      const url = String(config.url);
      invocationCount.set(url, (invocationCount.get(url) ?? 0) + 1);
      if (config.headers.Authorization === "Bearer later-token") {
        return Promise.resolve({ config, data: { recovered: true }, headers: {}, status: 200, statusText: "OK" });
      }
      return unauthorized(config);
    };

    const initiatingOrders = client.get("/orders");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledOnce());
    const queuedProfile = client.get("/profile");
    const queuedOrderCreate = client.post("/orders", { quantity: 1 });
    await vi.waitFor(() => expect(invocationCount.get("/profile")).toBe(1));
    await vi.waitFor(() => expect(invocationCount.get("/orders")).toBe(2));
    resolveRefresh(null);

    await expect(initiatingOrders).rejects.toMatchObject({ config: { url: "/orders" }, response: { status: 401 } });
    await expect(queuedProfile).rejects.toMatchObject({ config: { url: "/profile" }, response: { status: 401 } });
    await expect(queuedOrderCreate).rejects.toMatchObject({ config: { url: "/orders" }, response: { status: 401 } });
    expect(logout).toHaveBeenCalledOnce();

    await expect(client.get("/later")).resolves.toMatchObject({ data: { recovered: true } });
    expect(tryRefreshToken).toHaveBeenCalledTimes(2);
    expect(invocationCount.get("/profile")).toBe(1);
    expect(invocationCount.get("/orders")).toBe(2);
  });

  it("starts a separate refresh cycle for a newer session", async () => {
    const logout = vi.fn();
    let resolveOld!: (token: string | null) => void;
    let resolveNew!: (token: string | null) => void;
    const oldRefresh = new Promise<string | null>((resolve) => { resolveOld = resolve; });
    const newRefresh = new Promise<string | null>((resolve) => { resolveNew = resolve; });
    const tryRefreshToken = vi.fn()
      .mockReturnValueOnce(oldRefresh)
      .mockReturnValueOnce(newRefresh);
    auth.getState.mockReturnValue({ logout, tryRefreshToken, setUser: vi.fn() });
    auth.generation = 1;
    localStorage.setItem("access_token", "old-token");
    const client = await loadClient();
    client.defaults.adapter = (config) => {
      if (config.url === "/new" && config.headers.Authorization === "Bearer new-refreshed-token") {
        return Promise.resolve({ config, data: { session: "new" }, headers: {}, status: 200, statusText: "OK" });
      }
      return unauthorized(config);
    };

    const oldRequest = client.get("/old");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledOnce());

    auth.generation = 2;
    localStorage.setItem("access_token", "new-login-token");
    const newRequest = client.get("/new");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledTimes(2));

    localStorage.setItem("access_token", "new-refreshed-token");
    resolveNew("new-refreshed-token");
    await expect(newRequest).resolves.toMatchObject({ data: { session: "new" } });
    resolveOld(null);
    await expect(oldRequest).rejects.toMatchObject({ config: { url: "/old" }, response: { status: 401 } });
    expect(logout).not.toHaveBeenCalled();
  });

  it("rejects every concurrent request with its own error when refresh throws", async () => {
    const logout = vi.fn();
    let rejectRefresh!: (error: Error) => void;
    const pendingRefresh = new Promise<string>((_resolve, reject) => { rejectRefresh = reject; });
    const tryRefreshToken = vi.fn().mockReturnValue(pendingRefresh);
    auth.getState.mockReturnValue({ logout, tryRefreshToken });
    const client = await loadClient();
    const adapter = vi.fn(unauthorized);
    client.defaults.adapter = adapter;

    const orders = client.get("/orders");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledOnce());
    const profile = client.get("/profile");
    await vi.waitFor(() => expect(adapter).toHaveBeenCalledTimes(2));
    rejectRefresh(new Error("refresh failed"));

    await expect(orders).rejects.toMatchObject({ config: { url: "/orders" }, response: { status: 401 } });
    await expect(profile).rejects.toMatchObject({ config: { url: "/profile" }, response: { status: 401 } });
    expect(logout).toHaveBeenCalledOnce();
  });

  it("retries the initiating and queued requests with a refreshed Authorization token", async () => {
    const logout = vi.fn();
    let resolveRefresh!: (token: string) => void;
    const pendingRefresh = new Promise<string>((resolve) => { resolveRefresh = resolve; });
    const tryRefreshToken = vi.fn().mockReturnValue(pendingRefresh);
    auth.getState.mockReturnValue({ logout, tryRefreshToken });
    const client = await loadClient();
    const authorizationValues: string[] = [];
    client.defaults.adapter = (config) => {
      const authorization = config.headers.Authorization;
      if (authorization === "Bearer refreshed-token") {
        authorizationValues.push(authorization);
        return Promise.resolve({ config, data: { ok: true }, headers: {}, status: 200, statusText: "OK" });
      }
      return unauthorized(config);
    };

    const initiating = client.get("/protected/initiating");
    const queued = client.get("/protected/queued");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledOnce());
    resolveRefresh("refreshed-token");

    await expect(initiating).resolves.toMatchObject({ data: { ok: true } });
    await expect(queued).resolves.toMatchObject({ data: { ok: true } });
    expect(authorizationValues).toEqual(["Bearer refreshed-token", "Bearer refreshed-token"]);
    expect(logout).not.toHaveBeenCalled();
  });

  it("rejects a login 401 without attempting refresh", async () => {
    const logout = vi.fn();
    const tryRefreshToken = vi.fn();
    auth.getState.mockReturnValue({ logout, tryRefreshToken });
    const client = await loadClient();
    client.defaults.adapter = unauthorized;

    await expect(client.post("/auth/login", {})).rejects.toMatchObject({ response: { status: 401 } });
    expect(tryRefreshToken).not.toHaveBeenCalled();
    expect(logout).not.toHaveBeenCalled();
  });

  it("rejects refresh 403 without revalidating through auth me", async () => {
    const logout = vi.fn();
    const setUser = vi.fn();
    const tryRefreshToken = vi.fn();
    auth.getState.mockReturnValue({ logout, setUser, tryRefreshToken });
    const client = await loadClient();
    const adapter = vi.fn((config) => {
      if (config.url === "/auth/me") {
        return Promise.resolve({ config, data: { username: "unexpected" }, headers: {}, status: 200, statusText: "OK" });
      }
      return forbidden(config);
    });
    client.defaults.adapter = adapter;

    await expect(client.post("/auth/refresh", {})).rejects.toMatchObject({ response: { status: 403 } });
    expect(adapter).toHaveBeenCalledOnce();
    expect(setUser).not.toHaveBeenCalled();
    expect(tryRefreshToken).not.toHaveBeenCalled();
  });

  it("rejects auth me 403 without recursively requesting auth me", async () => {
    const logout = vi.fn();
    const setUser = vi.fn();
    const tryRefreshToken = vi.fn();
    auth.getState.mockReturnValue({ logout, setUser, tryRefreshToken });
    const client = await loadClient();
    const adapter = vi.fn()
      .mockImplementationOnce(forbidden)
      .mockImplementationOnce((config) => Promise.resolve({
        config,
        data: { username: "unexpected" },
        headers: {},
        status: 200,
        statusText: "OK",
      }));
    client.defaults.adapter = adapter;

    await expect(client.get("/auth/me")).rejects.toMatchObject({ response: { status: 403 } });
    expect(adapter).toHaveBeenCalledOnce();
    expect(setUser).not.toHaveBeenCalled();
  });

  it("still revalidates one business 403 through auth me", async () => {
    const logout = vi.fn();
    const setUser = vi.fn();
    const tryRefreshToken = vi.fn();
    auth.getState.mockReturnValue({ logout, setUser, tryRefreshToken });
    const client = await loadClient();
    const user = { username: "current-user" };
    const adapter = vi.fn((config) => {
      if (config.url === "/auth/me") {
        return Promise.resolve({ config, data: user, headers: {}, status: 200, statusText: "OK" });
      }
      return forbidden(config);
    });
    client.defaults.adapter = adapter;

    await expect(client.get("/business")).rejects.toMatchObject({ response: { status: 403 } });
    expect(adapter).toHaveBeenCalledTimes(2);
    expect(setUser).toHaveBeenCalledWith(user);
  });

  it("settles a protected 401 when refresh returns 403", async () => {
    const logout = vi.fn();
    const setUser = vi.fn();
    const clientPromise = loadClient();
    const tryRefreshToken = vi.fn(async () => {
      const client = await clientPromise;
      try {
        await client.post("/auth/refresh", { refresh_token: "expired" });
        return "unexpected";
      } catch {
        return null;
      }
    });
    auth.getState.mockReturnValue({ logout, setUser, tryRefreshToken });
    const client = await clientPromise;
    client.defaults.adapter = (config) => {
      if (config.url === "/auth/refresh") return forbidden(config);
      if (config.url === "/auth/me") return unauthorized(config);
      return unauthorized(config);
    };

    const outcome = await Promise.race([
      client.get("/protected").then(() => "resolved", () => "rejected"),
      new Promise<string>((resolve) => setTimeout(() => resolve("timeout"), 100)),
    ]);

    expect(outcome).toBe("rejected");
    expect(tryRefreshToken).toHaveBeenCalledOnce();
  });

  it("does not logout a newer session when an older refresh returns null", async () => {
    const logout = vi.fn();
    let resolveRefresh!: (token: string | null) => void;
    const pendingRefresh = new Promise<string | null>((resolve) => { resolveRefresh = resolve; });
    const tryRefreshToken = vi.fn().mockReturnValue(pendingRefresh);
    auth.getState.mockReturnValue({ logout, tryRefreshToken, setUser: vi.fn() });
    auth.generation = 1;
    localStorage.setItem("access_token", "old-token");
    const client = await loadClient();
    client.defaults.adapter = unauthorized;

    const oldRequest = client.get("/protected");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledOnce());
    auth.generation = 2;
    localStorage.setItem("access_token", "new-login-token");
    resolveRefresh(null);

    await expect(oldRequest).rejects.toMatchObject({ response: { status: 401 } });
    expect(logout).not.toHaveBeenCalled();
    expect(localStorage.getItem("access_token")).toBe("new-login-token");
  });

  it("does not refresh a delayed 401 from an older session", async () => {
    const logout = vi.fn();
    const tryRefreshToken = vi.fn();
    auth.getState.mockReturnValue({ logout, tryRefreshToken, setUser: vi.fn() });
    auth.generation = 1;
    localStorage.setItem("access_token", "old-token");
    const delayed = deferredAdapter();
    const client = await loadClient();
    client.defaults.adapter = delayed.adapter;

    const oldRequest = client.get("/slow");
    await vi.waitFor(() => expect(delayed.adapter).toHaveBeenCalledOnce());
    auth.generation = 2;
    localStorage.setItem("access_token", "new-login-token");
    delayed.reject401();

    await expect(oldRequest).rejects.toMatchObject({ response: { status: 401 } });
    expect(tryRefreshToken).not.toHaveBeenCalled();
    expect(logout).not.toHaveBeenCalled();
  });
});
