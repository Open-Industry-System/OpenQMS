import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
      return Promise.reject(error);
    }
    if (error.response?.status === 403) {
      try {
        const { useAuthStore } = await import("../store/authStore");
        const resp = await client.get("/auth/me");
        useAuthStore.getState().setUser(resp.data);
      } catch {
        // refresh failed — ignore, user stays with stale state
      }
    }
    return Promise.reject(error);
  }
);

export default client;
