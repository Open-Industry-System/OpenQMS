import axios, { type InternalAxiosRequestConfig } from "axios";
import { getAuthSessionGeneration, useAuthStore } from "../store/authStore";

const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

type AuthRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
  _authAccessToken?: string | null;
  _authSessionGeneration?: number;
};

function isAuthUrl(url?: string): boolean {
  return Boolean(url?.startsWith("/auth/"));
}

function isRequestSessionCurrent(config: AuthRequestConfig): boolean {
  return config._authSessionGeneration === getAuthSessionGeneration();
}

function isRequestOwnerCurrent(config: AuthRequestConfig): boolean {
  return isRequestSessionCurrent(config)
    && config._authAccessToken === localStorage.getItem("access_token");
}

function logoutAndRedirectIfCurrent(config: AuthRequestConfig): void {
  if (!isRequestOwnerCurrent(config)) return;
  useAuthStore.getState().logout();
  window.location.href = "/login";
}

// Factory ID auto-injection for GET requests on business APIs
// Excluded: auth, group, product-lines, factories (management endpoints)
// NOTE: baseURL is "/api", so config.url is relative (e.g. "/auth/login", "/group/dashboard")
const FACTORY_ID_EXCLUDE_PREFIXES = ["/auth/", "/group/", "/product-lines", "/factories"];

// Guard against concurrent refresh attempts
let isRefreshing = false;
type RefreshSubscriber = {
  error: unknown;
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
};
let refreshSubscribers: RefreshSubscriber[] = [];

function onRefreshed(token: string) {
  refreshSubscribers.forEach(({ resolve }) => resolve(token));
  refreshSubscribers = [];
}

function onRefreshFailed() {
  refreshSubscribers.forEach(({ error, reject }) => reject(error));
  refreshSubscribers = [];
}

function addRefreshSubscriber(subscriber: RefreshSubscriber) {
  refreshSubscribers.push(subscriber);
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  const authConfig = config as AuthRequestConfig;
  authConfig._authAccessToken = token;
  authConfig._authSessionGeneration = getAuthSessionGeneration();
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
    const originalRequest = error.config as AuthRequestConfig;

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
      // Auth endpoints own their failure handling. Re-entering refresh from the
      // refresh endpoint itself can wait on the same in-flight promise forever.
      if (originalRequest.url?.includes("/auth/login") || originalRequest.url?.includes("/auth/refresh")) {
        return Promise.reject(error);
      }
      if (originalRequest._retry) {
        logoutAndRedirectIfCurrent(originalRequest);
        return Promise.reject(error);
      }
      // A delayed response from a previous login/session must not refresh or
      // log out the session that is current now.
      if (!isRequestOwnerCurrent(originalRequest)) {
        return Promise.reject(error);
      }

      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const newToken = await useAuthStore.getState().tryRefreshToken();
          if (newToken && isRequestSessionCurrent(originalRequest)) {
            onRefreshed(newToken);
            originalRequest._retry = true;
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return client(originalRequest);
          }
          onRefreshFailed();
          logoutAndRedirectIfCurrent(originalRequest);
          return Promise.reject(error);
        } catch {
          onRefreshFailed();
          logoutAndRedirectIfCurrent(originalRequest);
          return Promise.reject(error);
        } finally {
          isRefreshing = false;
        }
      }

      // Queue pending requests while refresh is in flight
      return new Promise((resolve, reject) => {
        addRefreshSubscriber({
          error,
          resolve: (token: string) => {
            originalRequest._retry = true;
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(client(originalRequest));
          },
          reject,
        });
      });
    }

    if (error.response?.status === 403) {
      // Auth endpoints must reject directly. Revalidating /auth/refresh or
      // /auth/me through /auth/me can recurse or self-wait on refreshPromise.
      if (isAuthUrl(originalRequest.url) || !isRequestOwnerCurrent(originalRequest)) {
        return Promise.reject(error);
      }
      const generation = originalRequest._authSessionGeneration;
      try {
        const resp = await client.get("/auth/me");
        if (generation === getAuthSessionGeneration()) {
          useAuthStore.getState().setUser(resp.data);
        }
      } catch {
        // Revalidation failure is handled by the auth request itself.
      }
    }
    return Promise.reject(error);
  }
);

export default client;