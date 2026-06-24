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
  update_track: "branch" | "release" | "latest-release" | "next-major";
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
  update_track?: "branch" | "release" | "latest-release" | "next-major";
  branch?: string;
  release?: string | null;
  repo?: string;
  auto_update?: boolean;
  installed_track?: string;
  installed_ref?: string;
  installed_commit?: string;
  installed_version?: string;
  update_available?: boolean | null;
  downgrade_blocked?: boolean | null;
  log_tail?: string[];
  check?: {
    status?: "up-to-date" | "update-available" | "downgrade-blocked" | "error";
    commit_relation?: "same" | "upgrade" | "downgrade" | "diverged" | "unknown";
    message?: string;
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

  listModels: () => request<{ models: AiModel[] }>("/api/settings/models"),
  createModel: (data: CreateModelInput) =>
    request<AiModel>("/api/settings/models", { method: "POST", body: JSON.stringify(data) }),
  updateModel: (id: string, data: UpdateModelInput) =>
    request<AiModel>(`/api/settings/models/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  toggleModel: (id: string, enabled: boolean) =>
    request<AiModel>(`/api/settings/models/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  testModel: (id: string) =>
    request<{ ok: boolean; message: string }>(`/api/settings/models/${id}/test`, { method: "POST" }),
  testModelConnection: (data: CreateModelInput) =>
    request<{ ok: boolean; message: string }>("/api/settings/models/test-connection", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getDataConnections: () =>
    request<{ newsapi: NewsApiConnection }>("/api/settings/data-connections"),
  saveNewsApi: (data: { api_key: string; enabled: boolean }) =>
    request<NewsApiConnection>("/api/settings/data-connections/newsapi", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  testNewsApi: () =>
    request<{ ok: boolean; message: string }>("/api/settings/data-connections/newsapi/test", {
      method: "POST",
    }),

  getResearchSettings: () => request<ResearchSettings>("/api/settings/research"),
  saveResearchSettings: (data: Partial<ResearchSettings>) =>
    request<ResearchSettings>("/api/settings/research", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getForexPairs: () =>
    request<{ catalog: string[]; enabled_pairs: string[]; enabled: boolean }>(
      "/api/settings/assets/forex/pairs",
    ),
  getAssetSettings: (assetClass: AssetClass) =>
    request<AssetSettings>(`/api/settings/assets/${assetClass}`),
  saveAssetSettings: (assetClass: AssetClass, data: { enabled: boolean; enabled_pairs?: string[] }) =>
    request<AssetSettings>(`/api/settings/assets/${assetClass}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  listResearchReports: (limit = 50) =>
    request<{ reports: ResearchReportMeta[] }>(`/api/research/reports?limit=${limit}`),
};

export type AiModel = {
  id: string;
  title: string;
  type: string;
  base_url: string;
  model_name: string;
  api_key: string | null;
  api_key_set: boolean;
  enabled: boolean;
  created_at: string;
};

export type CreateModelInput = {
  title: string;
  type: "open_webui";
  base_url: string;
  model_name: string;
  api_key?: string;
  enabled?: boolean;
};

export type UpdateModelInput = {
  title?: string;
  base_url?: string;
  model_name?: string;
  api_key?: string;
  enabled?: boolean;
};

export type NewsApiConnection = {
  type: string;
  enabled: boolean;
  api_key: string | null;
  api_key_set: boolean;
};

export type ResearchSettings = {
  id: string;
  selected_model_id: string | null;
  daily_report_enabled: boolean;
  last_daily_run_date: string | null;
};

export type AssetClass = "forex" | "stocks" | "crypto" | "futures" | "options";

export type AssetSettings = {
  asset_class: AssetClass;
  enabled: boolean;
  enabled_pairs?: string[];
};

export type ResearchReportMeta = {
  filename: string;
  date: string;
  type: string;
  path: string;
};
