import { create } from "zustand";
import { isAuthGenerationChangedError } from "../utils/authGeneration";
import { classifyToken } from "../utils/jwt";
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
  syncStoredAccessToken: () => string | null;
  setCurrentFactoryId: (factoryId: string | null) => void;
  tryRefreshToken: () => Promise<string | null>;
}

export const useAuthStore = create<AuthState>((set, get) => {
  const syncStoredAccessToken = () => {
    const accessToken = localStorage.getItem("access_token");
    if (accessToken === get().token) return accessToken;

    if (accessToken && classifyToken(accessToken) !== "valid") {
      if (localStorage.getItem("access_token") === accessToken) localStorage.removeItem("access_token");
      set({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
      return null;
    }

    set({ user: null, token: accessToken, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
    return accessToken;
  };

  return ({
  user: null,
  token: localStorage.getItem("access_token"),
  loading: false,
  factoryScope: null,
  factories: [],
  currentFactoryId: null,

  login: async (username, password) => {
    const resp = await apiLogin({ username, password });
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
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("current_factory_id");
    set({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
  },

  fetchUser: async () => {
    const previousToken = get().token;
    const accessToken = syncStoredAccessToken();
    if (accessToken !== previousToken || !accessToken) return;

    try {
      set({ loading: true });
      const user = await getMe();
      if (localStorage.getItem("access_token") !== accessToken) {
        syncStoredAccessToken();
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
    } catch (error) {
      if (isAuthGenerationChangedError(error)) {
        syncStoredAccessToken();
        return;
      }
      if (localStorage.getItem("access_token") !== accessToken) {
        syncStoredAccessToken();
        return;
      }
      get().logout();
    }
  },

  syncStoredAccessToken,

  setCurrentFactoryId: (factoryId) => {
    if (factoryId) localStorage.setItem("current_factory_id", factoryId);
    else localStorage.removeItem("current_factory_id");
    set({ currentFactoryId: factoryId });
  },

  tryRefreshToken: async () => {
    const previousToken = get().token;
    const adoptedToken = syncStoredAccessToken();
    if (adoptedToken !== previousToken) return adoptedToken;

    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return null;

    try {
      const resp = await apiRefreshToken(refreshToken);
      if (localStorage.getItem("refresh_token") !== refreshToken) return syncStoredAccessToken();
      if (classifyToken(resp.access_token) !== "valid") {
        get().logout();
        return null;
      }

      localStorage.setItem("access_token", resp.access_token);
      localStorage.setItem("refresh_token", resp.refresh_token);
      set({ token: resp.access_token });
      return resp.access_token;
    } catch (error) {
      if (isAuthGenerationChangedError(error)) return syncStoredAccessToken();
      if (localStorage.getItem("refresh_token") !== refreshToken) return syncStoredAccessToken();
      get().logout();
      return null;
    }
  },
  });
});

const storageListener = (event: StorageEvent) => {
  if (event.key === "access_token" || event.key === null) useAuthStore.getState().syncStoredAccessToken();
};

if (typeof window !== "undefined") {
  window.addEventListener("storage", storageListener);
  if (import.meta.hot) import.meta.hot.dispose(() => window.removeEventListener("storage", storageListener));
}