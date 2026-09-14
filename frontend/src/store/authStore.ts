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

export const useAuthStore = create<AuthState>((set, get) => {
  const adoptStoredAccessToken = () => {
    const accessToken = localStorage.getItem("access_token");
    if (accessToken !== get().token) {
      set({ user: null, token: accessToken, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
    }
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
    const accessToken = localStorage.getItem("access_token");
    if (!accessToken) return;

    try {
      set({ loading: true });
      const user = await getMe();
      if (localStorage.getItem("access_token") !== accessToken) {
        adoptStoredAccessToken();
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
      if (localStorage.getItem("access_token") !== accessToken) {
        adoptStoredAccessToken();
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

  tryRefreshToken: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return null;

    try {
      const resp = await apiRefreshToken(refreshToken);
      if (localStorage.getItem("refresh_token") !== refreshToken) return adoptStoredAccessToken();

      localStorage.setItem("access_token", resp.access_token);
      localStorage.setItem("refresh_token", resp.refresh_token);
      set({ token: resp.access_token });
      return resp.access_token;
    } catch {
      if (localStorage.getItem("refresh_token") !== refreshToken) return adoptStoredAccessToken();
      get().logout();
      return null;
    }
  },
  });
});