import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AxiosRequestConfig } from "axios";

const store = vi.hoisted(() => ({
  logout: vi.fn(),
  tryRefreshToken: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock("../store/authStore", () => ({
  useAuthStore: { getState: () => store },
}));

function unauthorized(config: AxiosRequestConfig) {
  return Promise.reject({ config, response: { status: 401, data: {} } });
}

async function loadClient() {
  vi.resetModules();
  return (await import("./client")).default;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
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
    store.tryRefreshToken.mockResolvedValue("new-access");
    let attempts = 0;
    client.defaults.adapter = (config) => {
      attempts += 1;
      return (config as AxiosRequestConfig & { _retry?: boolean })._retry
        ? Promise.resolve({ config, data: config.headers?.Authorization, status: 200, statusText: "OK", headers: {} })
        : unauthorized(config);
    };

    const responses = await Promise.all([client.get("/fmea"), client.get("/capa")]);
    expect(responses.map((response) => response.data)).toEqual(["Bearer new-access", "Bearer new-access"]);
    expect(store.tryRefreshToken).toHaveBeenCalledOnce();
    expect(attempts).toBe(4);
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
