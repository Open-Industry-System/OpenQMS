import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AxiosRequestConfig } from "axios";

const store = vi.hoisted(() => ({
  token: null as string | null,
  user: { user_id: "alice" } as unknown,
  factoryScope: { default_factory_id: "alice-factory" } as unknown,
  factories: [{ id: "alice-factory" }] as unknown[],
  currentFactoryId: "alice-factory" as string | null,
  loading: true,
  logout: vi.fn(),
  tryRefreshToken: vi.fn(),
  fetchUser: vi.fn(),
  syncStoredAccessToken: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock("../store/authStore", () => ({
  useAuthStore: { getState: () => store },
}));

function unauthorized(config: AxiosRequestConfig) {
  return Promise.reject({ config, response: { status: 401, data: {} } });
}

function jwt(sub: string) {
  return jwtPayload({ sub, exp: Math.floor(Date.now() / 1000) + 3600 });
}

function jwtPayload(payload: Record<string, unknown>) {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

async function loadClient() {
  vi.resetModules();
  return (await import("./client")).default;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  store.token = null;
  store.user = { user_id: "alice" };
  store.factoryScope = { default_factory_id: "alice-factory" };
  store.factories = [{ id: "alice-factory" }];
  store.currentFactoryId = "alice-factory";
  store.loading = true;
  store.syncStoredAccessToken.mockImplementation(() => {
    store.token = localStorage.getItem("access_token");
    store.user = null;
    store.factoryScope = null;
    store.factories = [];
    store.currentFactoryId = null;
    store.loading = false;
  });
  window.history.replaceState({}, "", "/");
});

describe("401 recovery", () => {
  it("rejects the initiating request when refresh returns null", async () => {
    const client = await loadClient();
    store.tryRefreshToken.mockResolvedValue(null);
    client.defaults.adapter = unauthorized;

    await expect(client.get("/fmea")).rejects.toMatchObject({ response: { status: 401 } });
    expect(store.logout).toHaveBeenCalledOnce();
  });

  it("shares a failing refresh and settles every concurrent 401 caller", async () => {
    const client = await loadClient();
    let resolveRefresh!: (value: string | null) => void;
    store.tryRefreshToken.mockReturnValue(new Promise((resolve) => { resolveRefresh = resolve; }));
    client.defaults.adapter = unauthorized;

    const first = client.get("/fmea");
    const second = client.get("/capa");
    resolveRefresh(null);

    await expect(Promise.allSettled([first, second])).resolves.toEqual([
      expect.objectContaining({ status: "rejected" }),
      expect.objectContaining({ status: "rejected" }),
    ]);
    expect(store.tryRefreshToken).toHaveBeenCalledOnce();
  });

  it("shares a successful refresh and retries every concurrent request with its token", async () => {
    const client = await loadClient();
    const aliceToken = jwt("alice");
    localStorage.setItem("access_token", aliceToken);
    store.token = aliceToken;
    store.tryRefreshToken.mockResolvedValue(aliceToken);
    let attempts = 0;
    client.defaults.adapter = (config) => {
      attempts += 1;
      return (config as AxiosRequestConfig & { _retry?: boolean })._retry
        ? Promise.resolve({ config, data: config.headers?.Authorization, status: 200, statusText: "OK", headers: {} })
        : unauthorized(config);
    };

    const responses = await Promise.all([client.get("/fmea"), client.get("/capa")]);
    expect(responses.map((response) => response.data)).toEqual([`Bearer ${aliceToken}`, `Bearer ${aliceToken}`]);
    expect(store.tryRefreshToken).toHaveBeenCalledOnce();
    expect(attempts).toBe(4);
  });

  it("rejects a 401 request instead of replaying Alice's mutation as Bob", async () => {
    const client = await loadClient();
    const refresh = deferred<string | null>();
    const aliceToken = jwt("alice");
    const bobToken = jwt("bob");
    localStorage.setItem("access_token", aliceToken);
    store.token = aliceToken;
    store.tryRefreshToken.mockReturnValue(refresh.promise);
    let attempts = 0;
    client.defaults.adapter = (config) => {
      attempts += 1;
      return (config as AxiosRequestConfig & { _retry?: boolean })._retry
        ? Promise.resolve({ config, data: "replayed", status: 200, statusText: "OK", headers: {} })
        : unauthorized(config);
    };

    const request = client.post("/fmea", { name: "Alice mutation" });
    await vi.waitFor(() => expect(store.tryRefreshToken).toHaveBeenCalledOnce());
    localStorage.setItem("access_token", bobToken);
    refresh.resolve(bobToken);

    await expect(request).rejects.toMatchObject({ response: { status: 401 } });
    expect(attempts).toBe(1);
    expect(store.logout).not.toHaveBeenCalled();
  });

  it("preserves an explicitly bound retry authorization instead of replacing it from storage", async () => {
    const client = await loadClient();
    const refreshedAliceToken = jwt("alice");
    const unrelatedToken = jwt("unrelated");
    localStorage.setItem("access_token", unrelatedToken);
    store.token = unrelatedToken;
    store.tryRefreshToken.mockResolvedValue(refreshedAliceToken);
    client.defaults.adapter = (config) => (config as AxiosRequestConfig & { _retry?: boolean })._retry
      ? Promise.resolve({ config, data: config.headers?.Authorization, status: 200, statusText: "OK", headers: {} })
      : unauthorized(config);

    const response = await client.post("/fmea", { name: "bound mutation" }, { headers: { Authorization: `Bearer ${jwt("alice")}` } });

    expect(response.data).toBe(`Bearer ${refreshedAliceToken}`);
  });

  it("fails closed instead of retrying when the refreshed token has no decodable subject", async () => {
    const client = await loadClient();
    const aliceToken = jwt("alice");
    localStorage.setItem("access_token", aliceToken);
    store.token = aliceToken;
    store.tryRefreshToken.mockResolvedValue("not-a-jwt");
    let attempts = 0;
    client.defaults.adapter = (config) => {
      attempts += 1;
      return (config as AxiosRequestConfig & { _retry?: boolean })._retry
        ? Promise.resolve({ config, data: "replayed", status: 200, statusText: "OK", headers: {} })
        : unauthorized(config);
    };

    await expect(client.post("/fmea", { name: "Alice mutation" })).rejects.toMatchObject({ response: { status: 401 } });
    expect(attempts).toBe(1);
  });

  it("does not log out a newer session when an old refresh resolves null", async () => {
    const client = await loadClient();
    const refresh = deferred<string | null>();
    const aliceToken = jwt("alice");
    localStorage.setItem("access_token", aliceToken);
    store.token = aliceToken;
    store.tryRefreshToken.mockReturnValue(refresh.promise);
    client.defaults.adapter = unauthorized;

    const request = client.get("/fmea");
    await vi.waitFor(() => expect(store.tryRefreshToken).toHaveBeenCalledOnce());
    refresh.resolve(null);
    localStorage.setItem("access_token", jwt("bob"));

    await expect(request).rejects.toMatchObject({ response: { status: 401 } });
    expect(store.logout).not.toHaveBeenCalled();
  });

  it("does not log out a newer session for an already-retried request", async () => {
    const client = await loadClient();
    const bobToken = jwt("bob");
    localStorage.setItem("access_token", bobToken);
    store.token = bobToken;
    client.defaults.adapter = unauthorized;

    await expect(client.request({
      url: "/fmea", method: "post", data: { name: "Alice mutation" },
      headers: { Authorization: `Bearer ${jwt("alice")}` }, _retry: true,
    } as AxiosRequestConfig & { _retry: boolean })).rejects.toMatchObject({ response: { status: 401 } });
    expect(store.logout).not.toHaveBeenCalled();
  });

  it("resets shared refresh state after success so a later 401 starts another refresh", async () => {
    const client = await loadClient();
    const aliceToken = jwt("alice");
    localStorage.setItem("access_token", aliceToken);
    store.token = aliceToken;
    store.tryRefreshToken.mockResolvedValueOnce(aliceToken).mockResolvedValueOnce(aliceToken);
    client.defaults.adapter = (config) => (config as AxiosRequestConfig & { _retry?: boolean })._retry
      ? Promise.resolve({ config, data: "ok", status: 200, statusText: "OK", headers: {} })
      : unauthorized(config);

    await expect(client.get("/fmea")).resolves.toMatchObject({ data: "ok" });
    await expect(client.get("/capa")).resolves.toMatchObject({ data: "ok" });
    expect(store.tryRefreshToken).toHaveBeenCalledTimes(2);
  });

  it("rejects before the adapter when stored access belongs to a different idle-tab generation", async () => {
    const client = await loadClient();
    const aliceToken = jwt("alice");
    const bobToken = jwt("bob");
    store.token = aliceToken;
    localStorage.setItem("access_token", bobToken);
    const adapter = vi.fn(() => Promise.resolve({ data: "networked", status: 200, statusText: "OK", headers: {}, config: {} }));
    client.defaults.adapter = adapter as unknown as typeof client.defaults.adapter;

    await expect(client.post("/fmea", { name: "Alice mutation" })).rejects.toBeDefined();
    expect(adapter).not.toHaveBeenCalled();
    expect(store.syncStoredAccessToken).toHaveBeenCalledOnce();
    expect(store).toMatchObject({ token: bobToken, user: null, factoryScope: null, factories: [], currentFactoryId: null, loading: false });
  });

  it.each([
    jwtPayload({ sub: "alice", exp: 0 }),
    jwtPayload({ sub: "alice" }),
    jwtPayload({ sub: "alice", exp: "not-a-number" }),
  ])("does not replay a same-sub refresh token that is not usable: %s", async (returnedToken) => {
    const client = await loadClient();
    const aliceToken = jwt("alice");
    localStorage.setItem("access_token", aliceToken);
    store.token = aliceToken;
    store.tryRefreshToken.mockResolvedValue(returnedToken);
    let attempts = 0;
    client.defaults.adapter = (config) => {
      attempts += 1;
      return (config as AxiosRequestConfig & { _retry?: boolean })._retry
        ? Promise.resolve({ config, data: "replayed", status: 200, statusText: "OK", headers: {} })
        : unauthorized(config);
    };

    await expect(client.post("/fmea", { name: "Alice mutation" })).rejects.toMatchObject({ response: { status: 401 } });
    expect(attempts).toBe(1);
  });

  it("delegates a 403 resync to the guarded full-store user bootstrap", async () => {
    const client = await loadClient();
    store.fetchUser.mockResolvedValue(undefined);
    const adapter = vi.fn((config: AxiosRequestConfig) => config.url === "/fmea"
      ? Promise.reject({ config, response: { status: 403, data: {} } })
      : Promise.resolve({ config, data: { user_id: "alice" }, status: 200, statusText: "OK", headers: {} }));
    client.defaults.adapter = adapter as unknown as typeof client.defaults.adapter;

    await expect(client.get("/fmea")).rejects.toMatchObject({ response: { status: 403 } });
    expect(store.fetchUser).toHaveBeenCalledOnce();
    expect(store.setUser).not.toHaveBeenCalled();
    expect(adapter).toHaveBeenCalledTimes(1);
  });

  it("does not recursively issue /auth/me resyncs for a 403 response", async () => {
    const client = await loadClient();
    store.fetchUser.mockImplementation(async () => {
      await client.get("/auth/me").catch(() => undefined);
    });
    let attempts = 0;
    const adapter = vi.fn((config: AxiosRequestConfig) => {
      attempts += 1;
      return Promise.reject({ config, response: { status: attempts < 3 ? 403 : 500, data: {} } });
    });
    client.defaults.adapter = adapter as unknown as typeof client.defaults.adapter;

    await expect(client.get("/fmea")).rejects.toMatchObject({ response: { status: 403 } });
    expect(store.fetchUser).toHaveBeenCalledOnce();
    expect(adapter).toHaveBeenCalledTimes(2);
  });

  it("rejects a refresh endpoint 401 without recursively refreshing", async () => {
    const client = await loadClient();
    client.defaults.adapter = unauthorized;

    await expect(client.post("/auth/refresh", {})).rejects.toMatchObject({ response: { status: 401 } });
    expect(store.tryRefreshToken).not.toHaveBeenCalled();
    expect(store.logout).not.toHaveBeenCalled();
  });

  it("rejects a login 401 immediately without refresh", async () => {
    const client = await loadClient();
    client.defaults.adapter = unauthorized;

    await expect(client.post("/auth/login", {})).rejects.toMatchObject({ response: { status: 401 } });
    expect(store.tryRefreshToken).not.toHaveBeenCalled();
    expect(store.logout).not.toHaveBeenCalled();
  });

  it("resets refresh state after failure so a later request starts a new refresh", async () => {
    const client = await loadClient();
    client.defaults.adapter = unauthorized;
    store.tryRefreshToken.mockResolvedValueOnce(null).mockResolvedValueOnce(null);

    await expect(client.get("/fmea")).rejects.toMatchObject({ response: { status: 401 } });
    await expect(client.get("/capa")).rejects.toMatchObject({ response: { status: 401 } });

    expect(store.tryRefreshToken).toHaveBeenCalledTimes(2);
  });
});
