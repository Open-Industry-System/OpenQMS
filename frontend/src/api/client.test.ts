import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getState: vi.fn(),
}));

vi.mock("../store/authStore", () => ({
  useAuthStore: { getState: auth.getState },
}));

async function loadClient() {
  return (await import("./client")).default;
}

function unauthorized(config: any) {
  return Promise.reject({ config, response: { status: 401 } });
}

describe("client 401 refresh handling", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
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
});
