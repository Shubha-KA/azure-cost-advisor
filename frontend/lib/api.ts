const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export type Scope = { tenantId: string; subscriptionId: string };

export async function api<T>(
  path: string,
  scope?: Scope,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (scope?.tenantId) headers.set("X-Tenant-ID", scope.tenantId);
  if (scope?.subscriptionId) {
    headers.set("X-Subscription-ID", scope.subscriptionId);
  }
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.href = `${API}/api/auth/logout`;
      return new Promise(() => {}) as Promise<T>;
    }
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const loginUrl = `${API}/api/auth/login`;
export const logoutUrl = `${API}/api/auth/logout`;
