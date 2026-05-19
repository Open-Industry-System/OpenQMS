import { create } from "zustand";
import type { User } from "../types";
import { login as apiLogin, getMe } from "../api/auth";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("access_token"),
  loading: false,

  login: async (username, password) => {
    const resp = await apiLogin({ username, password });
    localStorage.setItem("access_token", resp.access_token);
    set({ user: resp.user, token: resp.access_token });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    set({ user: null, token: null });
  },

  fetchUser: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
      set({ loading: true });
      const user = await getMe();
      set({ user, loading: false });
    } catch {
      localStorage.removeItem("access_token");
      set({ user: null, token: null, loading: false });
    }
  },
}));
