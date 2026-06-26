import type { StrategyParamsV1, StrategyPresetMeta, Timeframe } from "../lib/strategyParams";

const BASE = "";

async function parseErrorResponse(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = body.detail;
  const message = Array.isArray(detail)
    ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ")
    : detail;
  return message || res.statusText;
}

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
    throw new Error(await parseErrorResponse(res));
  }
  return res.json() as Promise<T>;
}

async function requestForm<T>(path: string, form: FormData, method = "POST"): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  return res.json() as Promise<T>;
}

export type MeResponse = {
  username: string;
  has_profile_photo: boolean;
};

export const PROFILE_PHOTO_PATH = "/api/auth/profile-photo";

export function profilePhotoUrl(cacheBust?: number): string {
  return cacheBust ? `${PROFILE_PHOTO_PATH}?t=${cacheBust}` : PROFILE_PHOTO_PATH;
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
  setup: (data: {
    username: string;
    password: string;
    confirm_password: string;
    profile_photo?: File | null;
  }) => {
    const form = new FormData();
    form.append("username", data.username);
    form.append("password", data.password);
    form.append("confirm_password", data.confirm_password);
    if (data.profile_photo) {
      form.append("profile_photo", data.profile_photo);
    }
    return requestForm<{ username: string; status: string; has_profile_photo: boolean }>(
      "/api/auth/setup",
      form,
    );
  },
  login: (data: { username: string; password: string }) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request<MeResponse>("/api/auth/me"),
  uploadProfilePhoto: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestForm<{ status: string; has_profile_photo: boolean }>(
      "/api/auth/profile-photo",
      form,
      "PUT",
    );
  },
  deleteProfilePhoto: () =>
    request<{ status: string; has_profile_photo: boolean }>("/api/auth/profile-photo", {
      method: "DELETE",
    }),
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
  deleteModel: (id: string) =>
    request<{ ok: boolean }>(`/api/settings/models/${id}`, { method: "DELETE" }),
  testModel: (id: string) =>
    request<{ ok: boolean; message: string }>(`/api/settings/models/${id}/test`, { method: "POST" }),
  testModelConnection: (data: CreateModelInput) =>
    request<{ ok: boolean; message: string }>("/api/settings/models/test-connection", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getDataConnections: () =>
    request<{ newsapi: NewsApiConnection; models: ModelConnection[] }>(
      "/api/settings/data-connections",
    ),
  saveNewsApi: (data: { api_key: string; enabled: boolean }) =>
    request<NewsApiConnection>("/api/settings/data-connections/newsapi", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  saveModelConnection: (modelId: string, data: { capabilities: Record<string, boolean> }) =>
    request<ModelConnection>(`/api/settings/data-connections/models/${modelId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  testNewsApi: (data?: { api_key?: string }) =>
    request<{ ok: boolean; message: string }>("/api/settings/data-connections/newsapi/test", {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),

  getExchangeConnections: () =>
    request<ExchangeConnectionsResponse>("/api/settings/exchanges"),
  getOandaConnection: () => request<OandaConnection>("/api/settings/exchanges/oanda"),
  saveOandaConnection: (data: {
    access_token: string;
    environment: OandaEnvironment;
    account_id: string;
  }) =>
    request<OandaConnection>("/api/settings/exchanges/oanda", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteOandaConnection: () =>
    request<{ ok: boolean }>("/api/settings/exchanges/oanda", { method: "DELETE" }),
  testOandaConnection: (data: {
    access_token: string;
    environment: OandaEnvironment;
    account_id?: string;
  }) =>
    request<OandaTestResult>("/api/settings/exchanges/oanda/test-connection", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  testOandaConnectionSaved: () =>
    request<OandaTestResult>("/api/settings/exchanges/oanda/test", { method: "POST" }),
  getOandaAccountSummary: () =>
    request<OandaAccountSummary>("/api/settings/exchanges/oanda/account-summary"),

  getResearchSettings: () => request<ResearchSettings>("/api/settings/research"),
  saveResearchSettings: (data: Partial<ResearchSettings>) =>
    request<ResearchSettings>("/api/settings/research", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getForexPairs: () =>
    request<{
      catalog: string[];
      enabled_pairs: string[];
      enabled: boolean;
      primary_exchange: string | null;
    }>("/api/settings/assets/forex/pairs"),
  getAssetSettings: (assetClass: AssetClass) =>
    request<AssetSettings>(`/api/settings/assets/${assetClass}`),
  saveAssetSettings: (
    assetClass: AssetClass,
    data: {
      enabled: boolean;
      enabled_pairs?: string[];
      primary_exchange?: string | null;
    },
  ) =>
    request<AssetSettings>(`/api/settings/assets/${assetClass}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getResearchSignals: () =>
    request<ResearchSignalsSnapshot>("/api/research/signals"),
  listResearchReports: (limit = 200) =>
    request<{ reports: ResearchReportMeta[] }>(`/api/research/reports?limit=${limit}`),
  getResearchReport: (filename: string) =>
    request<ResearchReportContent>(
      `/api/research/reports/content?filename=${encodeURIComponent(filename)}`,
    ),

  listStrategies: () => request<{ strategies: Strategy[] }>("/api/strategies"),
  getStrategy: (id: string) => request<Strategy>(`/api/strategies/${encodeURIComponent(id)}`),
  createStrategy: (data: CreateStrategyInput) =>
    request<Strategy>("/api/strategies", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateStrategy: (id: string, data: UpdateStrategyInput) =>
    request<Strategy>(`/api/strategies/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteStrategy: (id: string) =>
    request<{ status: string; id: string }>(`/api/strategies/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  listStrategyPresets: () =>
    request<{ presets: StrategyPresetMeta[] }>("/api/strategies/presets"),
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

export type ModelProviderType = "open_webui" | "openai" | "claude" | "grok";

export type CreateModelInput = {
  title: string;
  type: ModelProviderType;
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

export type ModelConnection = {
  model_id: string;
  title: string;
  provider_type: string;
  model_name: string;
  enabled: boolean;
  api_key_set: boolean;
  available_capabilities: string[];
  capability_labels: Record<string, string>;
  capabilities: Record<string, boolean>;
};

export type OandaEnvironment = "practice" | "live";

export type OandaConnection = {
  exchange_id: "oanda";
  connected: boolean;
  environment: OandaEnvironment;
  account_id: string | null;
  access_token: string | null;
  access_token_set: boolean;
};

export type ExchangeConnectionsResponse = {
  oanda: OandaConnection;
};

export type OandaAccount = {
  id: string;
  tags?: string[];
};

export type OandaTestResult = {
  ok: boolean;
  message: string;
  accounts: OandaAccount[];
};

export type OandaAccountSummary = {
  id: string | null;
  alias: string | null;
  currency: string | null;
  balance: string | null;
  nav: string | null;
  unrealized_pl: string | null;
  realized_pl: string | null;
  margin_available: string | null;
  margin_used: string | null;
  open_trade_count: number | null;
  open_position_count: number | null;
  pending_order_count: number | null;
};

export type ReasoningEffort = "none" | "low" | "medium" | "high";

export type ContributorModel = {
  model_id: string;
  reasoning_effort: ReasoningEffort;
  enabled: boolean;
};

export type ResearchDataSources = {
  newsapi: boolean;
  web_search_enabled: boolean;
  web_search_model_id: string | null;
  x_search_enabled: boolean;
  x_search_model_id: string | null;
};

export type ResearchScheduleMarket = {
  id: string;
  name: string;
  label: string;
  timezone: string;
  open_time_local: string;
};

export type ResearchSettings = {
  id: string;
  contributor_models: ContributorModel[];
  synthesis_model_id: string | null;
  synthesis_reasoning_effort: ReasoningEffort;
  data_sources: ResearchDataSources;
  daily_report_enabled: boolean;
  daily_report_market_id: string;
  daily_report_market_offset_hours: number;
  last_daily_run_date: string | null;
  schedule_markets?: ResearchScheduleMarket[];
  schedule_description?: string;
};

export type AssetClass = "forex" | "metals" | "stocks" | "crypto" | "futures" | "options";

export type AssetSettings = {
  asset_class: AssetClass;
  enabled: boolean;
  enabled_pairs?: string[];
  enabled_symbols?: string[];
  primary_exchange: string | null;
};

export type ResearchSignal = "buy" | "sell" | "hold" | "mixed";
export type ResearchTone = "bullish" | "bearish" | "neutral";
export type ResearchConviction = "low" | "medium" | "high";

export type ResearchSignalItem = {
  symbol: string;
  signal: ResearchSignal | null;
  tone: ResearchTone | null;
  approach: string | null;
  conviction: ResearchConviction | null;
  status: "ok" | "missing" | "not_implemented";
};

export type ResearchAssetSignals = {
  asset_class: AssetClass;
  label: string;
  implemented: boolean;
  items: ResearchSignalItem[];
};

export type ResearchSignalsSnapshot = {
  report_date: string | null;
  report_filename: string | null;
  generated_at: string | null;
  asset_classes: ResearchAssetSignals[];
};

export type ResearchReportType = "daily" | "daily_model" | "weekly" | string;

export type ResearchReportMeta = {
  filename: string;
  date: string;
  type: ResearchReportType;
  path: string;
  model_label: string | null;
  generated_at: string | null;
  reasoning_effort: string | null;
  size_bytes: number;
};

export type ResearchReportContent = {
  filename: string;
  content: string;
  date: string | null;
  type: ResearchReportType | null;
  model_label: string | null;
  generated_at: string | null;
  reasoning_effort: string | null;
};

export type StrategyType = "preset" | "custom";

export type StrategyStats = {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number | null;
  realized_pnl: number;
  open_positions: number;
  last_trade_at: string | null;
};

export type Strategy = {
  id: string;
  name: string;
  asset_class: AssetClass;
  asset_class_label: string;
  timeframe?: Timeframe;
  description: string;
  enabled: boolean;
  instruments: string[];
  instrument_selection?: StrategyInstrumentSelection;
  stats: StrategyStats;
  created_at: string | null;
  updated_at: string | null;
  strategy_type?: StrategyType;
  preset_id?: string | null;
  route?: string | null;
  params?: StrategyParamsV1;
  params_schema_version?: number;
};

export type StrategyInstrumentSelection = Partial<Record<AssetClass, string[]>>;

export type CreateStrategyInput = {
  name: string;
  description: string;
  preset_id: string;
  params: StrategyParamsV1;
  instrument_selection: StrategyInstrumentSelection;
  enabled?: boolean;
};

export type UpdateStrategyInput = {
  name?: string;
  description?: string;
  params?: StrategyParamsV1;
  instrument_selection?: StrategyInstrumentSelection;
  enabled?: boolean;
};

export type { StrategyParamsV1, StrategyPresetMeta, Timeframe };
