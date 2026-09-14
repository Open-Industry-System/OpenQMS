import { afterEach, beforeEach, describe, expect, it } from "vitest";
import client from "./client";
import { useAuthStore } from "../store/authStore";
import type { User } from "../types";

const alice: User = {
  user_id: "alice", username: "alice", display_name: "Alice", email: null,
  role_key: "quality_engineer", permissions: {}, product_lines: [],
  bypass_row_level_security: false, is_active: true,
};

function jwt(sub: string, generation?: string) {
  return `header.${btoa(JSON.stringify({ sub, exp: Math.floor(Date.now() / 1000) + 3600, generation }))}.signature`;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function seedAlice() {
  const aliceAccess = jwt("alice");
  localStorage.setItem("access_token", aliceAccess);
  localStorage.setItem("refresh_token", "alice-refresh");
  useAuthStore.setState({
    token: aliceAccess,
    user: alice,
    loading: true,
    factoryScope: { accessible_factory_ids: ["alice-factory"], default_factory_id: "alice-factory" },
    factories: [{ id: "alice-factory", code: "ALICE", name: "Alice", is_active: true }],
    currentFactoryId: "alice-factory",
  });
  return aliceAccess;
}

function expectBobAdopted(bobAccess: string, refreshToken: string) {
  expect({
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
    state: useAuthStore.getState(),
  }).toMatchObject({
    access: bobAccess,
    refresh: refreshToken,
    state: { token: bobAccess, user: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null },
  });
}

describe("auth store and client generation composition", () => {
  let originalAdapter: typeof client.defaults.adapter;
  let adapterCalls = 0;

  beforeEach(() => {
    originalAdapter = client.defaults.adapter;
    adapterCalls = 0;
    localStorage.clear();
    useAuthStore.setState({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
    client.defaults.adapter = async (config) => {
      adapterCalls += 1;
      return { config, data: {}, status: 200, statusText: "OK", headers: {} };
    };
  });

  afterEach(() => {
    client.defaults.adapter = originalAdapter;
    localStorage.clear();
    useAuthStore.setState({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
  });

  it("reconciles Bob before fetchUser dispatch without issuing /auth/me", async () => {
    seedAlice();
    const bobAccess = jwt("bob");
    localStorage.setItem("access_token", bobAccess);
    localStorage.setItem("refresh_token", "bob-refresh");

    await expect(useAuthStore.getState().fetchUser()).resolves.toBeUndefined();

    expect(adapterCalls).toBe(0);
    expectBobAdopted(bobAccess, "bob-refresh");
  });

  it("reconciles Bob before tryRefreshToken dispatch without issuing refresh", async () => {
    seedAlice();
    const bobAccess = jwt("bob");
    localStorage.setItem("access_token", bobAccess);
    localStorage.setItem("refresh_token", "bob-refresh");

    await expect(useAuthStore.getState().tryRefreshToken()).resolves.toBe(bobAccess);

    expect(adapterCalls).toBe(0);
    expectBobAdopted(bobAccess, "bob-refresh");
  });

  it("preserves Bob when access changes after fetchUser captures Alice but before dispatch", async () => {
    seedAlice();
    const bobAccess = jwt("bob");

    const fetching = useAuthStore.getState().fetchUser();
    localStorage.setItem("access_token", bobAccess);

    await expect(fetching).resolves.toBeUndefined();

    expect(adapterCalls).toBe(0);
    expectBobAdopted(bobAccess, "alice-refresh");
  });

  it("hydrates the user after /auth/me refreshes to a same-subject token", async () => {
    const accessA = jwt("alice", "A");
    const accessB = jwt("alice", "B");
    const aliceFactory = { id: "alice-factory", code: "ALICE", name: "Alice", is_active: true };
    const hydratedAlice: User = {
      ...alice,
      factory_scope: { accessible_factory_ids: [aliceFactory.id], default_factory_id: aliceFactory.id },
      factories: [aliceFactory],
    };
    const calls: Array<{ method: string | undefined; url: string | undefined; authorization: unknown }> = [];
    localStorage.setItem("access_token", accessA);
    localStorage.setItem("refresh_token", "refresh-A");
    useAuthStore.setState({ token: accessA, user: null, loading: false });
    client.defaults.adapter = async (config) => {
      adapterCalls += 1;
      calls.push({ method: config.method, url: config.url, authorization: config.headers.Authorization });
      if (adapterCalls === 1) {
        return Promise.reject({ config, response: { status: 401, data: {} } });
      }
      if (adapterCalls === 2) {
        return { config, data: { access_token: accessB, refresh_token: "refresh-B" }, status: 200, statusText: "OK", headers: {} };
      }
      return { config, data: hydratedAlice, status: 200, statusText: "OK", headers: {} };
    };

    const settled = await Promise.allSettled([useAuthStore.getState().fetchUser()]);

    expect(settled).toEqual([{ status: "fulfilled", value: undefined }]);
    expect(calls).toEqual([
      { method: "get", url: "/auth/me", authorization: `Bearer ${accessA}` },
      { method: "post", url: "/auth/refresh", authorization: `Bearer ${accessA}` },
      { method: "get", url: "/auth/me", authorization: `Bearer ${accessB}` },
    ]);
    expect(adapterCalls).toBe(3);
    expect(localStorage.getItem("access_token")).toBe(accessB);
    expect(localStorage.getItem("refresh_token")).toBe("refresh-B");
    expect(localStorage.getItem("current_factory_id")).toBe(aliceFactory.id);
    expect(useAuthStore.getState()).toMatchObject({
      token: accessB,
      user: hydratedAlice,
      loading: false,
      factoryScope: hydratedAlice.factory_scope,
      factories: hydratedAlice.factories,
      currentFactoryId: aliceFactory.id,
    });
  });

  it("discards an older same-subject response without releasing a newer bootstrap", async () => {
    const accessA = jwt("alice", "A");
    const accessB = jwt("alice", "B");
    const requestAStarted = deferred<void>();
    const requestBStarted = deferred<void>();
    const releaseResponseA = deferred<void>();
    const releaseResponseB = deferred<void>();
    const staleFactory = { id: "stale-factory", code: "STALE", name: "Stale", is_active: true };
    const currentFactory = { id: "current-factory", code: "CURRENT", name: "Current", is_active: true };
    const staleAlice: User = {
      ...alice,
      factory_scope: { accessible_factory_ids: [staleFactory.id], default_factory_id: staleFactory.id },
      factories: [staleFactory],
    };
    const currentAlice: User = {
      ...alice,
      factory_scope: { accessible_factory_ids: [currentFactory.id], default_factory_id: currentFactory.id },
      factories: [currentFactory],
    };
    const calls: Array<{ url: string | undefined; authorization: unknown }> = [];
    localStorage.setItem("access_token", accessA);
    localStorage.setItem("refresh_token", "refresh-A");
    useAuthStore.setState({ token: accessA, user: null, loading: false });
    client.defaults.adapter = async (config) => {
      adapterCalls += 1;
      calls.push({ url: config.url, authorization: config.headers.Authorization });
      if (adapterCalls === 1) {
        requestAStarted.resolve();
        await releaseResponseA.promise;
        return { config, data: staleAlice, status: 200, statusText: "OK", headers: {} };
      }
      requestBStarted.resolve();
      await releaseResponseB.promise;
      return { config, data: currentAlice, status: 200, statusText: "OK", headers: {} };
    };

    const fetchingA = useAuthStore.getState().fetchUser();
    await requestAStarted.promise;
    localStorage.setItem("access_token", accessB);
    localStorage.setItem("refresh_token", "refresh-B");
    window.dispatchEvent(new StorageEvent("storage", {
      key: "access_token", oldValue: accessA, newValue: accessB,
    }));
    const fetchingB = useAuthStore.getState().fetchUser();
    await requestBStarted.promise;
    releaseResponseA.resolve();

    await expect(Promise.allSettled([fetchingA])).resolves.toEqual([
      { status: "fulfilled", value: undefined },
    ]);
    expect(useAuthStore.getState()).toMatchObject({ token: accessB, user: null, loading: true });

    releaseResponseB.resolve();
    await expect(Promise.allSettled([fetchingB])).resolves.toEqual([
      { status: "fulfilled", value: undefined },
    ]);
    expect(calls).toEqual([
      { url: "/auth/me", authorization: `Bearer ${accessA}` },
      { url: "/auth/me", authorization: `Bearer ${accessB}` },
    ]);
    expect(adapterCalls).toBe(2);
    expect(localStorage.getItem("access_token")).toBe(accessB);
    expect(localStorage.getItem("refresh_token")).toBe("refresh-B");
    expect(localStorage.getItem("current_factory_id")).toBe(currentFactory.id);
    expect(useAuthStore.getState()).toMatchObject({
      token: accessB,
      user: currentAlice,
      loading: false,
      factoryScope: currentAlice.factory_scope,
      factories: currentAlice.factories,
      currentFactoryId: currentFactory.id,
    });
  });

  it("preserves Bob when access changes after tryRefreshToken captures Alice refresh", async () => {
    seedAlice();
    const bobAccess = jwt("bob");

    const refreshing = useAuthStore.getState().tryRefreshToken();
    localStorage.setItem("access_token", bobAccess);

    await expect(refreshing).resolves.toBe(bobAccess);

    expect(adapterCalls).toBe(0);
    expectBobAdopted(bobAccess, "alice-refresh");
  });
});
