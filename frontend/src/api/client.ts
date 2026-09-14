import axios from "axios";
import { classifyToken, getTokenSubject } from "../utils/jwt";
import { useAuthStore } from "../store/authStore";

const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

// Factory ID auto-injection for GET requests on business APIs
// Excluded: auth, group, product-lines, factories (management endpoints)
// NOTE: baseURL is "/api", so config.url is relative (e.g. "/auth/login", "/group/dashboard")
const FACTORY_ID_EXCLUDE_PREFIXES = ["/auth/", "/group/", "/product-lines", "/factories"];

// Shared by every request that receives a 401 while refresh is in flight.
let refreshPromise: Promise<string | null> | null = null;

function bearerToken(headers: { Authorization?: unknown; get?: (name: string) => unknown }) {
  const authorization = headers.get?.("Authorization") ?? headers.Authorization;
  return typeof authorization === "string" && authorization.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length)
    : null;
}

function rejectForCurrentSession(error: unknown, request: { headers: { Authorization?: unknown; get?: (name: string) => unknown } }) {
  const requestToken = bearerToken(request.headers);
  const storedToken = localStorage.getItem("access_token");
  if (storedToken === requestToken) {
    useAuthStore.getState().logout();
    window.location.href = "/login";
  } else if (!storedToken) {
    window.location.href = "/login";
  }
  return Promise.reject(error);
}

client.interceptors.request.use((config) => {
  const authState = useAuthStore.getState();
  const token = localStorage.getItem("access_token");
  if (authState.token !== token) {
    authState.syncStoredAccessToken();
    return Promise.reject(new Error("Access token changed in another tab"));
  }

  if (token && !bearerToken(config.headers)) {
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
      // A refresh request must reject back to tryRefreshToken(), which owns
      // generation-aware state cleanup. Retried requests fail closed.
      if (originalRequest.url?.includes("/auth/refresh")) {
        return Promise.reject(error);
      }
      if (originalRequest._retry) {
        return rejectForCurrentSession(error, originalRequest);
      }

      const initiatingToken = bearerToken(originalRequest.headers);
      originalRequest._retry = true;
      if (!refreshPromise) {
        refreshPromise = useAuthStore.getState().tryRefreshToken()
          .catch(() => null)
          .finally(() => { refreshPromise = null; });
      }

      const newToken = await refreshPromise;
      if (!newToken) return rejectForCurrentSession(error, originalRequest);

      const initiatingSubject = getTokenSubject(initiatingToken);
      const refreshedSubject = getTokenSubject(newToken);
      if (
        classifyToken(newToken) !== "valid"
        || !initiatingSubject
        || !refreshedSubject
        || initiatingSubject !== refreshedSubject
      ) {
        return Promise.reject(error);
      }

      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return client(originalRequest);
    }

    if (error.response?.status === 403) {
      if (originalRequest.url?.includes("/auth/me")) return Promise.reject(error);

      const authState = useAuthStore.getState();
      const storedToken = localStorage.getItem("access_token");
      if (authState.token !== storedToken) {
        authState.syncStoredAccessToken();
      } else if (bearerToken(originalRequest.headers) === authState.token) {
        await authState.fetchUser();
      }
    }
    return Promise.reject(error);
  }
);

export default client;