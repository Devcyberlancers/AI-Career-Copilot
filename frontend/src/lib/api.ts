import {
  clearSession,
  getRefreshToken,
  getToken,
  setSession,
} from "./auth";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const SESSION_EXPIRED_EVENT = "auth:session-expired";
const REFRESH_ENDPOINT = "/refresh";
const NO_REFRESH_ENDPOINTS = new Set(["/login", "/signup", REFRESH_ENDPOINT]);

let refreshPromise: Promise<string | null> | null = null;

export interface ApiRequestOptions extends RequestInit {
  body?: any;
}

interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

function buildRequestConfig(
  options: ApiRequestOptions,
  token: string | null,
): RequestInit {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else {
    headers.delete("Authorization");
  }

  const config: RequestInit = {
    ...options,
    headers,
  };

  if (options.body && !(options.body instanceof FormData)) {
    config.body = JSON.stringify(options.body);
  }

  return config;
}

function expireSession(): void {
  clearSession();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
}

async function requestNewAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  try {
    const response = await fetch(`${API_URL}${REFRESH_ENDPOINT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      console.warn("Access token refresh failed", response.status);
      return null;
    }

    const data = (await response.json()) as RefreshResponse;
    if (!data.access_token || !data.refresh_token) {
      console.warn("Access token refresh returned an invalid response");
      return null;
    }

    setSession({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
    });
    return data.access_token;
  } catch (error) {
    console.error("Access token refresh request failed", error);
    return null;
  }
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = requestNewAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function apiRequest<T>(
  endpoint: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  let response = await fetch(
    `${API_URL}${endpoint}`,
    buildRequestConfig(options, getToken()),
  );

  if (response.status === 401 && !NO_REFRESH_ENDPOINTS.has(endpoint)) {
    const newAccessToken = await refreshAccessToken();
    if (newAccessToken) {
      response = await fetch(
        `${API_URL}${endpoint}`,
        buildRequestConfig(options, newAccessToken),
      );
      if (response.status === 401) {
        expireSession();
      }
    } else {
      expireSession();
    }
  }

  if (!response.ok) {
    let errorMessage = "An error occurred";
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      errorMessage = response.statusText || errorMessage;
    }
    throw new Error(errorMessage);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}
