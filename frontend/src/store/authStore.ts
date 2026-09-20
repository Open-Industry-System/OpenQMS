import { create } from "zustand";
import type { User, FactoryScope, Factory } from "../types";
import { login as apiLogin, getMe, refreshToken as apiRefreshToken } from "../api/auth";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  factoryScope: FactoryScope | null;
  factories: Factory[];
  currentFactoryId: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  setUser: (user: User | null) => void;
  setCurrentFactoryId: (factoryId: string | null) => void;
  tryRefreshToken: () => Promise<string | null>;
}

let sessionGeneration = 0;
let fetchRequestId = 0;
let refreshPromise: Promise<string | null> | null = null;
let refreshOwner: { generation: number; refreshToken: string } | null = null;

export function getAuthSessionGeneration(): number {
  return sessionGeneration;
}

function invalidateSessionWork(): void {
  sessionGeneration += 1;
  fetchRequestId += 1;
  refreshPromise = null;
  refreshOwner = null;
}

function ownsSession(generation: number, refreshToken?: string): boolean {
  if (generation !== sessionGeneration) return false;
  return refreshToken === undefined || localStorage.getItem("refresh_token") === refreshToken;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem("access_token"),
  loading: false,
  factoryScope: null,
  factories: [],
  currentFactoryId: null,

  login: async (username, password) => {
    invalidateSessionWork();
    const generation = sessionGeneration;
    set({ loading: false });
    const resp = await apiLogin({ username, password });
    if (generation !== sessionGeneration) {
      throw new Error("Authentication session changed");
    }
    localStorage.setItem("access_token", resp.access_token);
    localStorage.setItem("refresh_token", resp.refresh_token);
    const factoryId = resp.user.factory_scope?.default_factory_id || null;
    if (factoryId) localStorage.setItem("current_factory_id", factoryId);
    else localStorage.removeItem("current_factory_id");
    set({
      user: resp.user,
      token: resp.access_token,
      loading: false,
      factoryScope: resp.user.factory_scope ?? null,
      factories: resp.user.factories ?? [],
      currentFactoryId: factoryId,
    });
  },

  logout: () => {
    invalidateSessionWork();
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("current_factory_id");
    set({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
  },

  fetchUser: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    const generation = sessionGeneration;
    const requestId = ++fetchRequestId;
    const isCurrentRequest = () => (
      requestId === fetchRequestId
      && ownsSession(generation)
      && localStorage.getItem("access_token") === token
    );
    const finishStaleRequest = () => {
      if (requestId === fetchRequestId) set({ loading: false });
    };
    try {
      set({ loading: true });
      const user = await getMe();
      if (!isCurrentRequest()) {
        finishStaleRequest();
        return;
      }
      const factoryId = user.factory_scope?.default_factory_id || null;
      if (factoryId) localStorage.setItem("current_factory_id", factoryId);
      else localStorage.removeItem("current_factory_id");
      set({
        user,
        loading: false,
        factoryScope: user.factory_scope ?? null,
        factories: user.factories ?? [],
        currentFactoryId: factoryId,
      });
    } catch {
      if (!isCurrentRequest()) {
        finishStaleRequest();
        return;
      }
      get().logout();
    }
  },

  setUser: (user) => {
    set({ user });
  },

  setCurrentFactoryId: (factoryId) => {
    if (factoryId) localStorage.setItem("current_factory_id", factoryId);
    else localStorage.removeItem("current_factory_id");
    set({ currentFactoryId: factoryId });
  },

  tryRefreshToken: () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return Promise.resolve(null);

    const generation = sessionGeneration;
    if (
      refreshPromise
      && refreshOwner?.generation === generation
      && refreshOwner.refreshToken === refreshToken
    ) {
      return refreshPromise;
    }

    const owner = { generation, refreshToken };
    const pending = (async () => {
      try {
        const resp = await apiRefreshToken(refreshToken);
        if (!ownsSession(generation, refreshToken)) return null;
        localStorage.setItem("access_token", resp.access_token);
        localStorage.setItem("refresh_token", resp.refresh_token);
        set({ token: resp.access_token, loading: false });
        return resp.access_token;
      } catch {
        if (ownsSession(generation, refreshToken)) get().logout();
        return null;
      }
    })().finally(() => {
      if (refreshPromise === pending) {
        refreshPromise = null;
        refreshOwner = null;
      }
    });

    refreshOwner = owner;
    refreshPromise = pending;
    return pending;
  },
}));