import axios from "axios";
import { useAuthStore } from "../store/authStore";

const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

// Factory ID auto-injection for GET requests on business APIs
// Excluded: auth, group, product-lines, factories (management endpoints)
// NOTE: baseURL is "/api", so config.url is relative (e.g. "/auth/login", "/group/dashboard")
const FACTORY_ID_EXCLUDE_PREFIXES = ["/auth/", "/group/", "/product-lines", "/factories"];

// Guard against concurrent refresh attempts
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function onRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

function addRefreshSubscriber(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Development mode: inject X-Tenant-ID header from localStorage
  if (import.meta.env.DEV) {
    const tenantSlug = localStorage.getItem("tenant_slug");
    if (tenantSlug) {
      config.headers["X-Tenant-ID"] = tenantSlug;
    }
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
    const originalRequest = error.config;

    if (error.response?.status === 503 && error.response?.data?.detail?.tenant_suspended) {
      window.location.href = "/tenant-suspended";
      return;
    }
    if (error.response?.status === 410) {
      window.location.href = "/tenant-deactivated";
      return;
    }

    // 401: attempt token refresh before redirecting to login
    if (error.response?.status === 401) {
      // Login 401 = invalid credentials (not an expired token). Reject
      // immediately so the login form can show the error and stop loading —
      // the refresh flow below would otherwise hang the request forever
      // (no refresh_token exists for an unauthenticated login attempt).
      if (originalRequest.url?.includes("/auth/login")) {
        return Promise.reject(error);
      }
      // Don't retry refresh endpoint or already-retried requests
      if (originalRequest.url?.includes("/auth/refresh") || originalRequest._retry) {
        useAuthStore.getState().logout();
        window.location.href = "/login";
        return Promise.reject(error);
      }

      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const newToken = await useAuthStore.getState().tryRefreshToken();
          isRefreshing = false;
          if (newToken) {
            onRefreshed(newToken);
            // Retry the original request with the new token
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return client(originalRequest);
          }
        } catch {
          isRefreshing = false;
          useAuthStore.getState().logout();
          window.location.href = "/login";
          return Promise.reject(error);
        }
        isRefreshing = false;
      }

      // Queue pending requests while refresh is in flight
      return new Promise((resolve) => {
        addRefreshSubscriber((token: string) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          resolve(client(originalRequest));
        });
      });
    }

    if (error.response?.status === 403) {
      try {
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