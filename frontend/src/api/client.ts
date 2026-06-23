const BASE = "";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  setupStatus: () => request<{ setup_complete: boolean }>("/api/auth/setup/status"),
  setup: (data: { username: string; password: string; confirm_password: string }) =>
    request("/api/auth/setup", { method: "POST", body: JSON.stringify(data) }),
  login: (data: { username: string; password: string }) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request<{ username: string }>("/api/auth/me"),
  health: () => request<Record<string, unknown>>("/api/health"),
  bots: () => request<{ bots: Array<{ name: string; state: string }> }>("/api/bots"),
  dbStats: () =>
    request<{ database: string; collections: Record<string, number>; error?: string }>(
      "/api/system/db",
    ),
  updateStatus: () => request<Record<string, unknown>>("/api/update/status"),
  triggerUpdate: () => request("/api/update", { method: "POST" }),
  startBot: (name: string) => request(`/api/bots/${name}/start`, { method: "POST" }),
  stopBot: (name: string) => request(`/api/bots/${name}/stop`, { method: "POST" }),
};
