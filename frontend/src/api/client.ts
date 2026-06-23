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
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ")
      : detail;
    throw new Error(message || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type UpdateVersionRef = {
  track?: string;
  ref?: string;
  commit?: string;
  commit_short?: string;
};

export type UpdateSettingsConfig = {
  update_track: "branch" | "release" | "latest-release";
  branch: string;
  release: string;
  repo: string;
  auto_update: boolean;
  configured_pin: string;
  config_path: string;
  config_writable: boolean;
};

export type UpdateStatusResponse = {
  dev_mode?: boolean;
  checked?: boolean;
  status: "idle" | "running" | "success" | "failed" | "up_to_date";
  message?: string;
  step?: string;
  progress?: number;
  configured_pin?: string;
  update_track?: "branch" | "release" | "latest-release";
  branch?: string;
  release?: string | null;
  repo?: string;
  auto_update?: boolean;
  installed_track?: string;
  installed_ref?: string;
  installed_commit?: string;
  installed_version?: string;
  update_available?: boolean | null;
  log_tail?: string[];
  check?: {
    status?: string;
    configured_pin?: string;
    update_track?: string;
    available?: UpdateVersionRef;
    installed?: UpdateVersionRef;
  } | null;
  error?: string | null;
  check_error?: string | null;
};

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
  updateStatus: () => request<UpdateStatusResponse>("/api/update/status"),
  getUpdateSettings: () => request<UpdateSettingsConfig>("/api/settings/update"),
  saveUpdateSettings: (data: {
    update_track: UpdateSettingsConfig["update_track"];
    branch: string;
    release: string;
    auto_update: boolean;
  }) =>
    request<UpdateSettingsConfig>("/api/settings/update", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  checkForUpdate: () =>
    request<UpdateStatusResponse>("/api/update/check", { method: "POST" }),
  triggerUpdate: () =>
    request<{ action: string; status: string; message: string }>("/api/update", {
      method: "POST",
    }),
  getPowerStatus: () =>
    request<{ available: boolean; dev_mode?: boolean }>("/api/system/power"),
  rebootSystem: () =>
    request<{ action: string; status: string; message: string }>("/api/system/reboot", {
      method: "POST",
    }),
  shutdownSystem: () =>
    request<{ action: string; status: string; message: string }>("/api/system/shutdown", {
      method: "POST",
    }),
  startBot: (name: string) => request(`/api/bots/${name}/start`, { method: "POST" }),
  stopBot: (name: string) => request(`/api/bots/${name}/stop`, { method: "POST" }),
};
