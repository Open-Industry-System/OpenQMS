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

type RefreshSubscriber = {
  config: AuthRequestConfig;
  error: unknown;
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
};

type RefreshCycle = {
  key: string;
  owner: AuthRequestConfig;
  subscribers: RefreshSubscriber[];
};

const refreshCycles = new Map<string, RefreshCycle>();

function refreshCycleKey(config: AuthRequestConfig): string {
  return `${config._authSessionGeneration ?? -1}:${config._authAccessToken ?? ""}`;
}

function settleRefreshSuccess(cycle: RefreshCycle, token: string): void {
  const subscribers = cycle.subscribers.splice(0);
  subscribers.forEach(({ resolve }) => resolve(token));
}

function settleRefreshFailure(cycle: RefreshCycle): void {
  const subscribers = cycle.subscribers.splice(0);
  subscribers.forEach(({ error, reject }) => reject(error));
}

async function runRefreshCycle(cycle: RefreshCycle): Promise<void> {
  try {
    const newToken = await useAuthStore.getState().tryRefreshToken();
    if (newToken && cycle.owner._authSessionGeneration === getAuthSessionGeneration()) {
      settleRefreshSuccess(cycle, newToken);
      return;
    }
    settleRefreshFailure(cycle);
    logoutAndRedirectIfCurrent(cycle.owner);
  } catch {
    settleRefreshFailure(cycle);
    logoutAndRedirectIfCurrent(cycle.owner);
  } finally {
    if (refreshCycles.get(cycle.key) === cycle) refreshCycles.delete(cycle.key);
  }
}

function enqueueRefresh(error: unknown, config: AuthRequestConfig): Promise<unknown> {
  const key = refreshCycleKey(config);
  let cycle = refreshCycles.get(key);
  let shouldStart = false;
  if (!cycle) {
    cycle = { key, owner: config, subscribers: [] };
    refreshCycles.set(key, cycle);
    shouldStart = true;
  }

  const response = new Promise((resolve, reject) => {
    cycle!.subscribers.push({
      config,
      error,
      resolve: (token: string) => {
        config._retry = true;
        config.headers.Authorization = `Bearer ${token}`;
        resolve(client(config));
      },
      reject,
    });
  });
  if (shouldStart) void runRefreshCycle(cycle);
  return response;
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

      return enqueueRefresh(error, originalRequest);
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