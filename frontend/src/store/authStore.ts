import { create } from "zustand";
import type { User, FactoryScope, Factory } from "../types";
import { login as apiLogin, getMe } from "../api/auth";

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
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("access_token"),
  loading: false,
  factoryScope: null,
  factories: [],
  currentFactoryId: null,

  login: async (username, password) => {
    const resp = await apiLogin({ username, password });
    localStorage.setItem("access_token", resp.access_token);
    set({
      user: resp.user,
      token: resp.access_token,
      factoryScope: resp.user.factory_scope ?? null,
      factories: resp.user.factories ?? [],
      currentFactoryId: resp.user.factory_scope?.default_factory_id || null,
    });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    set({ user: null, token: null, factoryScope: null, factories: [], currentFactoryId: null });
  },

  fetchUser: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
      set({ loading: true });
      const user = await getMe();
      set({
        user,
        loading: false,
        factoryScope: user.factory_scope ?? null,
        factories: user.factories ?? [],
        currentFactoryId: user.factory_scope?.default_factory_id || null,
      });
    } catch {
      localStorage.removeItem("access_token");
      set({ user: null, token: null, loading: false, factoryScope: null, factories: [], currentFactoryId: null });
    }
  },

  setUser: (user) => {
    set({ user });
  },

  setCurrentFactoryId: (factoryId) => {
    set({ currentFactoryId: factoryId });
  },
}));
