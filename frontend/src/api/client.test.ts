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

    const request = client.get("/protected");

    await expect(request).rejects.toMatchObject({ response: { status: 401 } });
    expect(tryRefreshToken).toHaveBeenCalledOnce();
    expect(logout).toHaveBeenCalledOnce();
  });

  it("rejects concurrent requests and clears the refresh queue when refresh returns null", async () => {
    const logout = vi.fn();
    let resolveRefresh!: (token: string | null) => void;
    const pendingRefresh = new Promise<string | null>((resolve) => { resolveRefresh = resolve; });
    const tryRefreshToken = vi.fn()
      .mockReturnValueOnce(pendingRefresh)
      .mockResolvedValueOnce("later-token");
    auth.getState.mockReturnValue({ logout, tryRefreshToken });
    const client = await loadClient();
    client.defaults.adapter = (config) => {
      if (config.headers.Authorization === "Bearer later-token") {
        return Promise.resolve({ config, data: { recovered: true }, headers: {}, status: 200, statusText: "OK" });
      }
      const error = { config, response: { status: 401 } };
      return Promise.reject(error);
    };

    const first = client.get("/protected/one");
    const second = client.get("/protected/two");
    await vi.waitFor(() => expect(tryRefreshToken).toHaveBeenCalledOnce());
    resolveRefresh(null);

    await expect(first).rejects.toMatchObject({ response: { status: 401 } });
    await expect(second).rejects.toMatchObject({ response: { status: 401 } });
    expect(logout).toHaveBeenCalledOnce();

    await expect(client.get("/protected/three")).resolves.toMatchObject({ data: { recovered: true } });
    expect(tryRefreshToken).toHaveBeenCalledTimes(2);
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
    client.defaults.adapter = (config) => Promise.reject({ config, response: { status: 401 } });

    await expect(client.post("/auth/login", {})).rejects.toMatchObject({ response: { status: 401 } });
    expect(tryRefreshToken).not.toHaveBeenCalled();
    expect(logout).not.toHaveBeenCalled();
  });
});
