import { afterEach, beforeEach, describe, expect, it } from "vitest";
import client from "./client";
import { useAuthStore } from "../store/authStore";
import type { User } from "../types";

const alice: User = {
  user_id: "alice", username: "alice", display_name: "Alice", email: null,
  role_key: "quality_engineer", permissions: {}, product_lines: [],
  bypass_row_level_security: false, is_active: true,
};

function jwt(sub: string) {
  return `header.${btoa(JSON.stringify({ sub, exp: Math.floor(Date.now() / 1000) + 3600 }))}.signature`;
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
