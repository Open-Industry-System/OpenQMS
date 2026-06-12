import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

// Factory ID auto-injection for GET requests on business APIs
// Excluded: auth, group, product-lines, factories (management endpoints)
// NOTE: baseURL is "/api", so config.url is relative (e.g. "/auth/login", "/group/dashboard")
const FACTORY_ID_EXCLUDE_PREFIXES = ["/auth/", "/group/", "/product-lines", "/factories"];

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Auto-inject factory_id on GET requests for business APIs
  const currentFactoryId = localStorage.getItem("current_factory_id");
  const isGetRequest = config.method === "get";
  const isExcluded = FACTORY_ID_EXCLUDE_PREFIXES.some(
    (prefix) => config.url?.startsWith(prefix)
  );
  if (currentFactoryId && isGetRequest && !isExcluded) {
    config.params = config.params || {};
    config.params.factory_id = currentFactoryId;
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
