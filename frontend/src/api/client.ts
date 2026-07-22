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
  /** Browser-usable photo URL (Supabase Storage public URL or local API path). */
  profile_photo_url?: string | null;
  display_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  auth_mode?: "builtin" | "oidc";
  identity_managed_by_idp?: boolean;
};

export type CandleBar = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CandlesResponse = {
  symbol: string;
  timeframe: string;
  source: string;
  candles: CandleBar[];
};

export type TradeCandlesResponse = CandlesResponse & {
  since: string;
  until: string;
  display_since: string;
  display_until: string;
  warmup_bars: number;
};

export type AnalysisRunCandlesResponse = TradeCandlesResponse & {
  price_side: string;
};

export const PROFILE_PHOTO_PATH = "/api/auth/profile-photo";

/** Build a display URL for a profile photo, with optional cache-busting. */
export function profilePhotoUrl(
  photoUrl?: string | null,
  cacheBust?: number,
): string | null {
  if (!photoUrl) return null;
  if (!cacheBust) return photoUrl;
  const sep = photoUrl.includes("?") ? "&" : "?";
  return `${photoUrl}${sep}t=${cacheBust}`;
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

export type DomainSettingsConfig = {
  domain: string;
  supabase_domain: string;
  supabase_url: string;
  config_path: string;
  apply_available: boolean;
  dev_mode?: boolean;
  message?: string;
  status?: string;
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

export type AuthConfig = {
  mode: "builtin" | "oidc";
  setup_complete: boolean;
  mfa_available: boolean;
  supabase_configured?: boolean;
  supabase_url?: string;
  supabase_anon_key?: string;
};

export type LoginResponse =
  | { username: string; status: "ok" }
  | { username: string; status: "mfa_required"; mfa_token: string };

export type MfaFactor = {
  id: string;
  friendly_name: string;
  factor_type: string;
  status: string;
};

export type MfaStatus = {
  available: boolean;
  enabled: boolean;
  factors: MfaFactor[];
};

export type MfaEnrollResponse = {
  status: string;
  enroll_token: string;
  factor_id: string;
  qr_code: string;
  secret: string;
  uri: string;
};

export const api = {
  authConfig: () => request<AuthConfig>("/api/auth/config"),
  setupStatus: () => request<{ setup_complete: boolean }>("/api/auth/setup/status"),
  onboardingStatus: () => request<OnboardingStatus>("/api/onboarding/status"),
  updateOnboardingProgress: (data: OnboardingProgressInput) =>
    request<OnboardingStatus>("/api/onboarding/progress", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  verifyOnboarding: () =>
    request<OnboardingStatus & { verified: boolean; checks: Record<string, boolean | null> }>(
      "/api/onboarding/verify",
      { method: "POST" },
    ),
  completeOnboarding: () =>
    request<OnboardingStatus>("/api/onboarding/complete", { method: "POST" }),
  setup: (data: {
    first_name: string;
    last_name: string;
    email: string;
    password: string;
    confirm_password: string;
    profile_photo?: File | null;
  }) => {
    const form = new FormData();
    form.append("first_name", data.first_name);
    form.append("last_name", data.last_name);
    form.append("email", data.email);
    form.append("password", data.password);
    form.append("confirm_password", data.confirm_password);
    if (data.profile_photo) {
      form.append("profile_photo", data.profile_photo);
    }
    return requestForm<{
      username: string;
      status: string;
      has_profile_photo: boolean;
      profile_photo_url?: string | null;
    }>("/api/auth/setup", form);
  },
  login: (data: { username: string; password: string }) =>
    request<LoginResponse>("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),
  loginMfa: (data: { mfa_token: string; code: string }) =>
    request<LoginResponse>("/api/auth/login/mfa", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  mfaStatus: () => request<MfaStatus>("/api/auth/mfa/status"),
  mfaEnroll: (data: { password: string }) =>
    request<MfaEnrollResponse>("/api/auth/mfa/enroll", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  mfaVerify: (data: { enroll_token: string; code: string }) =>
    request<{ status: string; enabled: boolean; factor_id: string }>("/api/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  mfaDisable: (data: { password: string; factor_id: string }) =>
    request<{ status: string; enabled: boolean }>("/api/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  logout: () => request<{ status: string; logout_url?: string | null }>("/api/auth/logout", { method: "POST" }),
  oidcLogout: () =>
    request<{ status: string; logout_url?: string | null }>("/api/auth/oidc/logout", {
      method: "POST",
    }),
  me: () => request<MeResponse>("/api/auth/me"),
  uploadProfilePhoto: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestForm<{
      status: string;
      has_profile_photo: boolean;
      profile_photo_url?: string | null;
    }>("/api/auth/profile-photo", form, "PUT");
  },
  deleteProfilePhoto: () =>
    request<{
      status: string;
      has_profile_photo: boolean;
      profile_photo_url?: string | null;
    }>("/api/auth/profile-photo", {
      method: "DELETE",
    }),
  changeUsername: (data: { username: string; current_password: string }) =>
    request<{ username: string; status: string }>("/api/auth/account/username", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  changePassword: (data: {
    current_password: string;
    password: string;
    confirm_password: string;
  }) =>
    request<{ status: string }>("/api/auth/account/password", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  updateProfile: (data: { first_name?: string | null; last_name?: string | null }) =>
    request<{
      status: string;
      display_name: string | null;
      first_name: string | null;
      last_name: string | null;
    }>("/api/auth/account/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  getDisplaySettings: () =>
    request<{ market_indicators: MarketIndicators }>("/api/auth/account/display"),
  updateDisplaySettings: (data: { market_indicators: MarketIndicators }) =>
    request<{ status: string; market_indicators: MarketIndicators }>("/api/auth/account/display", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  getGeneralSettings: () => request<GeneralSettings>("/api/auth/account/general"),
  updateGeneralSettings: (data: GeneralSettings) =>
    request<{ status: string } & GeneralSettings>("/api/auth/account/general", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  health: () => request<Record<string, unknown>>("/api/health"),
  bots: () =>
    request<{
      bots: Array<{
        name: string;
        state: string;
        started_at?: string | null;
        last_error?: string | null;
        next_candle_fetches?: Record<string, string>;
        analysis_candle_timeframes?: string[];
      }>;
    }>("/api/bots"),
  dbStats: () =>
    request<{
      database: string;
      uri?: string;
      tables: Record<string, number>;
      error?: string;
    }>("/api/system/db"),
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
  getDomainSettings: () => request<DomainSettingsConfig>("/api/settings/domain"),
  applyDomainSettings: (data: { domain: string; supabase_domain: string }) =>
    request<DomainSettingsConfig>("/api/settings/domain/apply", {
      method: "POST",
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
  listAvailableModels: (id: string) =>
    request<{ ok: boolean; message: string; models: AvailableProviderModel[] }>(
      `/api/settings/models/${id}/available`,
    ),
  listAvailableModelsFromCredentials: (data: {
    type: ModelProviderType;
    base_url?: string;
    api_key?: string;
  }) =>
    request<{ ok: boolean; message: string; models: AvailableProviderModel[] }>(
      "/api/settings/models/list-available",
      { method: "POST", body: JSON.stringify(data) },
    ),

  getDataConnections: () =>
    request<{ newsapi: NewsApiConnection; massive: MassiveConnection; models: ModelConnection[] }>(
      "/api/settings/data-connections",
    ),
  saveNewsApi: (data: { api_key: string; enabled: boolean }) =>
    request<NewsApiConnection>("/api/settings/data-connections/newsapi", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteNewsApi: () =>
    request<NewsApiConnection>("/api/settings/data-connections/newsapi", {
      method: "DELETE",
    }),
  saveMassive: (data: { api_key: string; enabled: boolean }) =>
    request<MassiveConnection>("/api/settings/data-connections/massive", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteMassive: () =>
    request<MassiveConnection>("/api/settings/data-connections/massive", {
      method: "DELETE",
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
  testMassive: (data?: { api_key?: string }) =>
    request<{ ok: boolean; message: string }>("/api/settings/data-connections/massive/test", {
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
  getOandaAccounts: () =>
    request<OandaAccountsSnapshot>("/api/settings/exchanges/oanda/accounts"),
  getOandaAccountSummaryHistory: (params?: { since?: string; until?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.since) search.set("since", params.since);
    if (params?.until) search.set("until", params.until);
    if (params?.limit != null) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<OandaAccountSummaryHistory>(
      `/api/settings/exchanges/oanda/account-summary/history${query ? `?${query}` : ""}`,
    );
  },

  getResearchSettings: () => request<ResearchSettings>("/api/settings/research"),
  saveResearchSettings: (data: Partial<ResearchSettings>) =>
    request<ResearchSettings>("/api/settings/research", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  saveWeeklyResearchSettings: (data: Partial<WeeklyResearchSettings>) =>
    request<ResearchSettings>("/api/settings/research/weekly", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  listBackups: () =>
    request<BackupListResponse>("/api/settings/backups"),
  exportCurrentBackup: () => request<ConfigBackupRecord>("/api/settings/backups/export"),
  getBackupSchedule: () => request<BackupScheduleSettings>("/api/settings/backups/schedule"),
  saveBackupSchedule: (data: Partial<BackupScheduleSettingsInput>) =>
    request<BackupScheduleSettings>("/api/settings/backups/schedule", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  createBackup: (data?: { label?: string }) =>
    request<ConfigBackupSummary>("/api/settings/backups", {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
  importBackup: (file: File, options?: { label?: string; restore?: boolean }) => {
    const form = new FormData();
    form.append("file", file);
    if (options?.label?.trim()) form.append("label", options.label.trim());
    if (options?.restore) form.append("restore", "true");
    return requestForm<ConfigBackupImportResult>("/api/settings/backups/import", form);
  },
  getBackup: (backupId: string) => request<ConfigBackupRecord>(`/api/settings/backups/${backupId}`),
  restoreBackup: (backupId: string, options?: { scope?: ConfigBackupRestoreScope }) =>
    request<ConfigBackupRestoreResult>(`/api/settings/backups/${backupId}/restore`, {
      method: "POST",
      body: JSON.stringify({ scope: options?.scope ?? "full" }),
    }),
  deleteBackup: (backupId: string) =>
    request<{ ok: boolean }>(`/api/settings/backups/${backupId}`, { method: "DELETE" }),

  getRssFeeds: () => request<RssFeedsCatalog>("/api/settings/rss-feeds"),
  saveRssFeeds: (data: Partial<RssFeedsSettings>) =>
    request<RssFeedsCatalog>("/api/settings/rss-feeds", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  getRssFeedsOpmlUrl: () => "/api/settings/rss-feeds/opml",

  getForexPairs: () =>
    request<{
      catalog: string[];
      enabled_pairs: string[];
      pair_order: string[];
      enabled: boolean;
      primary_exchange: string | null;
      enabled_sessions: Record<string, boolean>;
      only_one_position_per_pair: boolean;
      sessions: { id: string; name: string; hours: string }[];
    }>("/api/settings/assets/forex/pairs"),
  getCandles: (params: {
    symbol: string;
    timeframe: string;
    limit?: number;
    since?: string;
    until?: string;
  }) => {
    const search = new URLSearchParams({
      symbol: params.symbol,
      timeframe: params.timeframe,
      limit: String(params.limit ?? 200),
    });
    if (params.since) search.set("since", params.since);
    if (params.until) search.set("until", params.until);
    return request<CandlesResponse>(`/api/market-data/candles?${search.toString()}`);
  },
  getCandleDelta: (params: { symbol: string; timeframe: string; after: string }) =>
    request<CandlesResponse & { latest_time: string }>(
      `/api/market-data/candles/delta?symbol=${encodeURIComponent(params.symbol)}&timeframe=${encodeURIComponent(params.timeframe)}&after=${encodeURIComponent(params.after)}`,
    ),
  getAssetSettings: (assetClass: AssetClass) =>
    request<AssetSettings>(`/api/settings/assets/${assetClass}`),
  saveAssetSettings: (
    assetClass: AssetClass,
    data: {
      enabled: boolean;
      enabled_pairs?: string[];
      pair_order?: string[];
      enabled_sessions?: Record<string, boolean>;
      only_one_position_per_pair?: boolean;
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
  getResearchReportSignedUrl: (filename: string) =>
    request<{ filename: string; signed_url: string; expires_in: number }>(
      `/api/research/reports/signed-url?filename=${encodeURIComponent(filename)}`,
    ),
  getResearchReportsUnreadCount: () =>
    request<ResearchReportsUnreadCount>("/api/research/reports/unread-count"),
  markResearchReportRead: (filename: string) =>
    request<ResearchReportsUnreadCount & { ok: boolean; filename: string }>(
      `/api/research/reports/mark-read?filename=${encodeURIComponent(filename)}`,
      { method: "POST" },
    ),
  markResearchReportUnread: (filename: string) =>
    request<ResearchReportsUnreadCount & { ok: boolean; filename: string }>(
      `/api/research/reports/mark-unread?filename=${encodeURIComponent(filename)}`,
      { method: "POST" },
    ),
  markAllResearchReportsRead: (filenames?: string[]) =>
    request<ResearchReportsUnreadCount & { ok: boolean; marked: number }>(
      "/api/research/reports/mark-all-read",
      {
        method: "POST",
        body: JSON.stringify({ filenames: filenames ?? null }),
      },
    ),
  runResearchDailyReport: (force = true) =>
    request<BackgroundTaskAccepted>("/api/research/reports/run-daily", {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  rerunResearchReport: (filename: string) =>
    request<BackgroundTaskAccepted>(
      `/api/research/reports/rerun?filename=${encodeURIComponent(filename)}`,
      { method: "POST" },
    ),
  deleteResearchReport: (filename: string) =>
    request<{ filename: string; date: string; type: string }>(
      `/api/research/reports?filename=${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  runWeeklyBrief: (force = false) =>
    request<BackgroundTaskAccepted>("/api/research/reports/run-weekly-brief", {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  runWeeklyDebrief: (force = false) =>
    request<BackgroundTaskAccepted>("/api/research/reports/run-weekly-debrief", {
      method: "POST",
      body: JSON.stringify({ force }),
    }),

  getActiveBackgroundTask: () =>
    request<{ task: BackgroundTask | null }>("/api/tasks/active"),
  getRecentBackgroundTasks: (limit = 3) =>
    request<{ tasks: BackgroundTask[] }>(`/api/tasks/recent?limit=${limit}`),
  cancelBackgroundTask: (taskId: string) =>
    request<{ ok: boolean; task_id: string }>(`/api/tasks/${taskId}/cancel`, {
      method: "POST",
    }),

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
  promoteStrategy: (id: string) =>
    request<Strategy>(`/api/strategies/${encodeURIComponent(id)}/promote`, {
      method: "POST",
    }),
  deleteStrategy: (id: string) =>
    request<{ status: string; id: string }>(`/api/strategies/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  listStrategyVersions: (id: string, params?: { limit?: number; offset?: number }) => {
    const search = new URLSearchParams();
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.offset != null) search.set("offset", String(params.offset));
    const qs = search.toString();
    return request<StrategyVersionsResponse>(
      `/api/strategies/${encodeURIComponent(id)}/versions${qs ? `?${qs}` : ""}`,
    );
  },
  getStrategyVersion: (strategyId: string, versionId: string) =>
    request<StrategyVersionDetail>(
      `/api/strategies/${encodeURIComponent(strategyId)}/versions/${encodeURIComponent(versionId)}`,
    ),
  queueStrategyBacktests: (
    ids: string[],
    options?: {
      name?: string;
      instrument?: string;
      period?: BacktestPeriod;
      verbose?: boolean;
      account_margin?: number;
    },
  ) =>
    request<{ strategies: Strategy[]; queued: number; runs: BacktestRun[] }>(
      "/api/strategies/backtest",
      {
        method: "POST",
        body: JSON.stringify({
          ids,
          name: options?.name,
          instrument: options?.instrument,
          period: options?.period ?? "6m",
          verbose: options?.verbose ?? false,
          account_margin: options?.account_margin ?? 10_000,
        }),
      },
    ),
  listStrategyPresets: () =>
    request<{ presets: StrategyPresetMeta[] }>("/api/strategies/presets"),

  listBacktestRuns: (params?: {
    limit?: number;
    before?: string;
    strategy_id?: string;
    status?: BacktestRunStatus;
  }) => {
    const search = new URLSearchParams();
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.before) search.set("before", params.before);
    if (params?.strategy_id) search.set("strategy_id", params.strategy_id);
    if (params?.status) search.set("status", params.status);
    const query = search.toString();
    return request<BacktestRunsResponse>(`/api/backtest-runs${query ? `?${query}` : ""}`);
  },

  getBacktestRun: (runId: string) =>
    request<BacktestRun>(`/api/backtest-runs/${encodeURIComponent(runId)}`),

  getBacktestRunCandles: (runId: string, params?: { around?: string }) => {
    const search = new URLSearchParams();
    if (params?.around) search.set("around", params.around);
    const query = search.toString();
    return request<CandlesResponse>(
      `/api/backtest-runs/${encodeURIComponent(runId)}/candles${query ? `?${query}` : ""}`,
    );
  },

  startBacktestRun: (runId: string) =>
    request<BacktestRun>(`/api/backtest-runs/${encodeURIComponent(runId)}/start`, {
      method: "POST",
    }),

  cancelBacktestRun: (runId: string) =>
    request<BacktestRun>(`/api/backtest-runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    }),

  listBacktestLogs: (
    runId: string,
    params?: { after_id?: number; limit?: number; level?: string },
  ) => {
    const search = new URLSearchParams();
    if (params?.after_id != null) search.set("after_id", String(params.after_id));
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.level) search.set("level", params.level);
    const query = search.toString();
    return request<{ logs: BacktestLog[] }>(
      `/api/backtest-runs/${encodeURIComponent(runId)}/logs${query ? `?${query}` : ""}`,
    );
  },

  listBacktestActions: (
    runId: string,
    params?: { after_sequence?: number; kind?: string; limit?: number },
  ) => {
    const search = new URLSearchParams();
    if (params?.after_sequence != null) {
      search.set("after_sequence", String(params.after_sequence));
    }
    if (params?.kind) search.set("kind", params.kind);
    if (params?.limit != null) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<{ actions: BacktestAction[] }>(
      `/api/backtest-runs/${encodeURIComponent(runId)}/actions${query ? `?${query}` : ""}`,
    );
  },

  getBacktestSettings: () => request<BacktestSettings>("/api/backtest/settings"),

  updateBacktestSettings: (data: Partial<BacktestSettings>) =>
    request<BacktestSettings>("/api/backtest/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getAiStrategySettings: () => request<AiStrategySettings>("/api/settings/ai-strategies"),

  updateAiStrategySettings: (data: Partial<AiStrategySettings>) =>
    request<AiStrategySettings>("/api/settings/ai-strategies", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getStrategyStartup: (strategyId: string) =>
    request<{ job: AiStrategyStartupJob | null }>(
      `/api/strategies/${encodeURIComponent(strategyId)}/startup`,
    ),

  getStrategyActivity: (strategyId: string, params?: { limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.limit != null) search.set("limit", String(params.limit));
    const qs = search.toString();
    return request<AiStrategyActivityResponse>(
      `/api/strategies/${encodeURIComponent(strategyId)}/activity${qs ? `?${qs}` : ""}`,
    );
  },

  retryStrategyStartup: (strategyId: string) =>
    request<{ job: AiStrategyStartupJob }>(
      `/api/strategies/${encodeURIComponent(strategyId)}/startup`,
      { method: "POST" },
    ),

  cancelStrategyStartup: (strategyId: string) =>
    request<{ job: AiStrategyStartupJob | null }>(
      `/api/strategies/${encodeURIComponent(strategyId)}/startup/cancel`,
      { method: "POST" },
    ),

  requestBacktestAiFeedback: (runId: string) =>
    request<BacktestRun>(
      `/api/backtest-runs/${encodeURIComponent(runId)}/ai-feedback`,
      { method: "POST" },
    ),

  deleteBacktestRun: (runId: string) =>
    request<{ id: string; status: string }>(
      `/api/backtest-runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
    ),

  getMarketStatus: () => request<MarketStatusResponse>("/api/market-status"),

  getBotActivity: (limit = 20) =>
    request<BotActivityResponse>(`/api/bot/activity?limit=${limit}`),

  getCostLedger: (params?: { limit?: number; before?: string; category?: string }) => {
    const search = new URLSearchParams();
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.before) search.set("before", params.before);
    if (params?.category) search.set("category", params.category);
    const query = search.toString();
    return request<CostLedgerResponse>(`/api/cost-ledger${query ? `?${query}` : ""}`);
  },

  getCostLedgerSummary: (params?: {
    since?: string;
    until?: string;
    category?: string;
    billable_only?: boolean;
  }) => {
    const search = new URLSearchParams();
    if (params?.since) search.set("since", params.since);
    if (params?.until) search.set("until", params.until);
    if (params?.category) search.set("category", params.category);
    if (params?.billable_only === false) search.set("billable_only", "false");
    const query = search.toString();
    return request<CostLedgerSummary>(
      `/api/cost-ledger/summary${query ? `?${query}` : ""}`,
    );
  },

  getNextCandlePreview: () => request<NextCandlePreviewResponse>("/api/bots/next-candle-preview"),

  listStrategyAnalysisRuns: (params?: {
    limit?: number;
    before?: string;
    strategy_id?: string;
    pair?: string;
    analysis_purpose?: "entry" | "exit";
  }) => {
    const search = new URLSearchParams();
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.before) search.set("before", params.before);
    if (params?.strategy_id) search.set("strategy_id", params.strategy_id);
    if (params?.pair) search.set("pair", params.pair);
    if (params?.analysis_purpose) search.set("analysis_purpose", params.analysis_purpose);
    const query = search.toString();
    return request<StrategyAnalysisRunsResponse>(
      `/api/strategy-analysis-runs${query ? `?${query}` : ""}`,
    );
  },

  getStrategyAnalysisRun: (runId: string) =>
    request<StrategyAnalysisRun>(
      `/api/strategy-analysis-runs/${encodeURIComponent(runId)}`,
    ),

  getStrategyAnalysisRunCandles: (runId: string) =>
    request<AnalysisRunCandlesResponse>(
      `/api/strategy-analysis-runs/${encodeURIComponent(runId)}/candles`,
    ),

  deleteStrategyAnalysisRun: (runId: string) =>
    request<{ id: string; status: string }>(
      `/api/strategy-analysis-runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
    ),

  runStrategyAnalysis: (body: {
    strategy_id: string;
    asset_class: string;
    symbol: string;
  }) =>
    request<StrategyAnalysisRun>("/api/strategy-analysis-runs/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listTrades: (params?: {
    status?: "open" | "closed" | "all";
    limit?: number;
    before?: string;
    strategy_id?: string;
    pair?: string;
  }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.before) search.set("before", params.before);
    if (params?.strategy_id) search.set("strategy_id", params.strategy_id);
    if (params?.pair) search.set("pair", params.pair);
    const query = search.toString();
    return request<TradesListResponse>(`/api/trades${query ? `?${query}` : ""}`);
  },

  getTrade: (tradeId: string) =>
    request<Trade>(`/api/trades/${encodeURIComponent(tradeId)}`),

  getTradeCandles: (tradeId: string) =>
    request<TradeCandlesResponse>(`/api/trades/${encodeURIComponent(tradeId)}/candles`),

  closeTrade: (tradeId: string) =>
    request<Trade>(`/api/trades/${encodeURIComponent(tradeId)}/close`, {
      method: "POST",
    }),

  debugTradeRow: (tradeId: string) =>
    request<{ ok: boolean; trade_id: string; broker_lot_id: string; live_on_broker: boolean | null }>(
      `/api/trades/${encodeURIComponent(tradeId)}/debug`,
      { method: "POST" },
    ),

  getTradeReconciliation: () => request<TradeReconciliation>("/api/trades/reconciliation"),

  getInstrumentExposure: (exchangeId = "oanda") =>
    request<InstrumentExposureResponse>(`/api/trades/exposure?exchange_id=${encodeURIComponent(exchangeId)}`),

  syncTrades: () =>
    request<BackgroundTaskAccepted>("/api/trades/sync", {
      method: "POST",
    }),
};

export type BotActivityEvent = {
  id: string;
  action_type: string;
  title: string;
  detail: string | null;
  source: string | null;
  metadata: Record<string, unknown>;
  occurred_at: string;
};

export type BotActivityResponse = {
  events: BotActivityEvent[];
  latest: BotActivityEvent | null;
};

export type CostLedgerEntry = {
  id: string;
  category: string;
  amount_usd: number | null;
  description: string;
  source: string | null;
  metadata: Record<string, unknown>;
  occurred_at: string;
};

export type CostLedgerResponse = {
  items: CostLedgerEntry[];
  latest: CostLedgerEntry | null;
};

export type CostLedgerCategoryTotal = {
  category: string;
  amount_usd: number;
  count: number;
};

export type CostLedgerSummary = {
  totals: CostLedgerCategoryTotal[];
  grand_total_usd: number;
  since: string | null;
  until: string | null;
};

export type NextCandlePreviewAssetSection = {
  asset_class: string;
  label: string;
  symbols: string[];
};

export type NextCandlePreviewResponse = {
  timeframe: string | null;
  target_at: string | null;
  symbols: string[];
  asset_sections?: NextCandlePreviewAssetSection[];
  skip_reason?: string | null;
};

export type StrategyAnalysisIntent = {
  direction: string;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  confidence: number;
};

export type StrategyAnalysisExecution = {
  processed_at: string;
  gates_passed: boolean;
  gate_reasons: string[];
  gate_details?: Record<string, Record<string, unknown>>;
  priority_winner: boolean;
  intent_queued: boolean;
  intent: StrategyAnalysisIntent | null;
  analysis_purpose?: "entry" | "exit";
  exit_triggered?: boolean;
  exit_closed?: boolean;
  exit_reason?: string | null;
  trade_id?: string | null;
};

export type StrategyAnalysisRun = {
  id: string;
  strategy_id: string;
  strategy_name: string;
  pair: string;
  timeframe: string;
  direction: string | null;
  confidence: number;
  signal_type: string;
  min_candles: number;
  metadata: Record<string, unknown>;
  candle_time: string | null;
  analyzed_at: string;
  run_type: string;
  analysis_purpose?: "entry" | "exit";
  trade_id?: string | null;
  execution: StrategyAnalysisExecution | null;
};

export type StrategyAnalysisRunsResponse = {
  runs: StrategyAnalysisRun[];
  latest: StrategyAnalysisRun | null;
};

export type ChildOrder = {
  broker_order_id: string;
  order_type: string;
  state: string;
  price: number | null;
  trade_id?: string | null;
  create_time?: string | null;
  filled_time?: string | null;
  filling_event_id?: string | null;
  cancelling_event_id?: string | null;
};

export type Trade = {
  id: string;
  exchange_id?: string;
  strategy_id: string;
  strategy_name: string;
  pair: string;
  symbol?: string;
  asset_class: string;
  direction: string;
  entry_price: number;
  stop_loss: ChildOrder | null;
  take_profit: ChildOrder | null;
  stop_loss_price?: number | null;
  take_profit_price?: number | null;
  stop_loss_order?: ChildOrder | null;
  take_profit_order?: ChildOrder | null;
  exit_mode: string;
  risk_pct: number;
  initial_qty: number;
  current_qty: number;
  units: number;
  confidence: number;
  state: "open" | "closed" | "cancelled";
  broker_lot_id: string | null;
  open_time: string | null;
  close_time: string | null;
  close_reason?: string;
  execution_reason?: string | null;
  reason_display?: {
    code: string | null;
    label: string | null;
    short: string | null;
    category: "signal" | "import" | "exit" | "manual" | "broker" | "other" | null;
  };
  close_metadata?: Record<string, unknown>;
  exit_price?: number | null;
  realized_pl?: number | null;
  unrealized_pl?: number | null;
  timeframe?: string | null;
  entry_candle_open?: string | null;
  exit_candle_open?: string | null;
  metadata: Record<string, unknown>;
  trade_date?: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type InstrumentExposureRow = {
  exchange_id: string;
  symbol: string;
  pair?: string;
  direction: string;
  total_qty: number;
  average_price: number | null;
  unrealized_pl: number | null;
  broker_lot_ids: string[];
};

export type InstrumentExposureResponse = {
  exposure: InstrumentExposureRow[];
  count: number;
};

export type TradesListResponse = {
  trades: Trade[];
  latest: Trade | null;
};

export type TradeReconciliationMatch = {
  ledger_trade_id?: string;
  local_lot_id?: string;
  broker_trade_id: string;
  broker_lot_id?: string;
  pair: string;
  direction: string;
  match_type: "broker_order_id" | "broker_lot_id" | "pair_direction";
};

export type BrokerOpenTrade = {
  id: string;
  broker_lot_id?: string;
  instrument: string;
  pair: string;
  units: number;
  direction: string;
  price: number;
  entry_price?: number;
  unrealized_pl: number | null;
  current_price: number | null;
  open_time: string | null;
  stop_loss?: ChildOrder | null;
  take_profit?: ChildOrder | null;
};

export type TradeLedgerMarket = {
  current_price: number | null;
  unrealized_pl: number | null;
};

export type TradeReconciliation = {
  configured: boolean;
  ledger_open_count: number;
  local_open_count?: number;
  broker_open_count: number;
  status: "matched" | "mismatch" | "unconfigured";
  matched: TradeReconciliationMatch[];
  ledger_badges: Record<string, "matched" | "ledger_only" | "local_only">;
  lot_badges?: Record<string, "matched" | "ledger_only" | "local_only">;
  ledger_market: Record<string, TradeLedgerMarket>;
  lot_market?: Record<string, TradeLedgerMarket>;
  unmatched_ledger: Trade[];
  unmatched_local?: Trade[];
  unmatched_broker: BrokerOpenTrade[];
  broker_trades: BrokerOpenTrade[];
  broker_lots?: BrokerOpenTrade[];
};

// TODO(trades-suggestions): wire Suggested tab when backend is ready.
// export type EntrySuggestion = { kind: string; run_id: string; ... };
// export type ExitSuggestion = { trade_id: string; urgency: string; ... };

export type AiModel = {
  id: string;
  title: string;
  type: string;
  base_url: string;
  model_name?: string;
  default_model_name?: string;
  api_key: string | null;
  api_key_set: boolean;
  enabled: boolean;
  created_at: string;
};

export type AvailableProviderModel = {
  id: string;
  name: string;
};

export type ModelProviderType = "open_webui" | "openai" | "claude" | "grok";

export type CreateModelInput = {
  title?: string;
  type: ModelProviderType;
  base_url?: string;
  model_name?: string;
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

export type MassiveConnection = {
  type: string;
  enabled: boolean;
  api_key: string | null;
  api_key_set: boolean;
};

export type MarketIndicators = Record<string, boolean>;

export type GeneralSettings = {
  timezone_auto: boolean;
  timezone: string | null;
  show_utc_times: boolean;
  time_format: "12h" | "24h";
};

export type MarketSessionStatus = {
  id: string;
  name: string;
  status: "open" | "closed";
  exchange_status?: string;
  hours: string;
  next_open?: string;
  next_open_label?: string;
  closes_at?: string;
  closes_at_label?: string;
};

export type MarketStatusResponse = {
  enabled: boolean;
  available?: boolean;
  configured?: boolean;
  connection_enabled?: boolean;
  error?: string;
  server_time?: string;
  fx_open?: boolean;
  market?: string;
  sessions: MarketSessionStatus[];
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
  /** Set when the token works on the other OANDA environment (practice/live). */
  suggested_environment?: OandaEnvironment;
  diagnostics?: {
    token_length?: number;
    token_looks_masked?: boolean;
    environments_tried?: string[];
  };
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
  account_id?: string | null;
  environment?: string | null;
  synced_at?: string | null;
};

export type OandaAccountsSnapshot = {
  accounts: Array<{ id: string; tags: string[] }>;
  environment: string | null;
  synced_at: string | null;
};

export type OandaAccountSummaryHistory = {
  account_id: string;
  points: OandaAccountSummary[];
};

export type ReasoningEffort = "none" | "low" | "medium" | "high";

export type ContributorModel = {
  model_id: string;
  model_name?: string | null;
  reasoning_effort: ReasoningEffort;
  enabled: boolean;
};

export type ResearchDataSources = {
  newsapi: boolean;
  rss_enabled: boolean;
  rss_categories: Record<string, boolean>;
  web_search_enabled: boolean;
  web_search_model_id: string | null;
  x_search_enabled: boolean;
  x_search_model_id: string | null;
};

export type RssFeedCategory = {
  id: string;
  label: string;
  description: string;
  enabled: boolean;
  feed_count: number;
};

export type RssFeedItem = {
  id: string;
  title: string;
  url: string;
  category: string;
  category_enabled: boolean;
};

export type RssFeedsCatalog = {
  rss_enabled: boolean;
  categories: RssFeedCategory[];
  feeds: RssFeedItem[];
  total_feeds: number;
  enabled_feed_count: number;
};

export type RssFeedsSettings = {
  rss_enabled?: boolean;
  rss_categories?: Record<string, boolean>;
};

export type ResearchScheduleMarket = {
  id: string;
  name: string;
  label: string;
  timezone: string;
  open_time_local: string;
  close_time_local?: string;
};

export type WeeklyPromptPreview = {
  system_prompt: string;
  user_template: string;
};

export type WeeklyResearchSettings = {
  weekly_brief_enabled?: boolean;
  weekly_brief_model_id?: string | null;
  weekly_brief_model_name?: string | null;
  weekly_brief_reasoning_effort?: ReasoningEffort;
  weekly_brief_market_id?: string;
  weekly_brief_market_offset_hours?: number;
  weekly_debrief_enabled?: boolean;
  weekly_debrief_model_id?: string | null;
  weekly_debrief_model_name?: string | null;
  weekly_debrief_reasoning_effort?: ReasoningEffort;
  weekly_debrief_market_id?: string;
  weekly_debrief_market_offset_hours?: number;
};

export type ResearchSettings = {
  id: string;
  contributor_models: ContributorModel[];
  synthesis_model_id: string | null;
  synthesis_model_name: string | null;
  synthesis_reasoning_effort: ReasoningEffort;
  data_sources: ResearchDataSources;
  daily_report_enabled: boolean;
  daily_report_market_id: string;
  daily_report_market_offset_hours: number;
  last_daily_run_date: string | null;
  weekly_brief_enabled: boolean;
  weekly_brief_model_id: string | null;
  weekly_brief_model_name: string | null;
  weekly_brief_reasoning_effort: ReasoningEffort;
  weekly_brief_market_id: string;
  weekly_brief_market_offset_hours: number;
  last_weekly_brief_run_week: string | null;
  weekly_debrief_enabled: boolean;
  weekly_debrief_model_id: string | null;
  weekly_debrief_model_name: string | null;
  weekly_debrief_reasoning_effort: ReasoningEffort;
  weekly_debrief_market_id: string;
  weekly_debrief_market_offset_hours: number;
  last_weekly_debrief_run_week: string | null;
  schedule_markets?: ResearchScheduleMarket[];
  schedule_description?: string;
  weekly_brief_schedule_description?: string;
  weekly_debrief_schedule_description?: string;
  schedule_warnings?: string[];
  weekly_brief_prompt_preview?: WeeklyPromptPreview;
  weekly_debrief_prompt_preview?: WeeklyPromptPreview;
};

export type OnboardingStepId =
  | "admin"
  | "exchange"
  | "instruments"
  | "data_sources"
  | "models"
  | "finish";

export type OnboardingStatus = {
  auth_complete: boolean;
  onboarding_complete: boolean;
  current_step: OnboardingStepId;
  selected_exchange_id: string | null;
  enabled_pairs: string[] | null;
  strategy_id: string | null;
  strategy_name: string | null;
};

export type OnboardingProgressInput = {
  current_step?: OnboardingStepId;
  selected_exchange_id?: string | null;
  enabled_pairs?: string[] | null;
  strategy_id?: string | null;
  strategy_name?: string | null;
  clear_selected_exchange?: boolean;
};

export type AssetClass = "forex" | "metals" | "stocks" | "crypto" | "futures" | "options";

export type AssetSettings = {
  asset_class: AssetClass;
  enabled: boolean;
  enabled_pairs?: string[];
  pair_order?: string[];
  enabled_symbols?: string[];
  enabled_sessions?: Record<string, boolean>;
  only_one_position_per_pair?: boolean;
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

export type ResearchReportType =
  | "daily"
  | "daily_model"
  | "weekly_brief"
  | "weekly_debrief"
  | string;

export type ResearchReportMeta = {
  filename: string;
  date: string;
  type: ResearchReportType;
  path: string;
  model_label: string | null;
  generated_at: string | null;
  reasoning_effort: string | null;
  size_bytes: number;
  is_read: boolean;
};

export type ResearchReportContent = {
  filename: string;
  content: string | null;
  signed_url?: string | null;
  expires_in?: number | null;
  uses_storage?: boolean;
  path?: string | null;
  date: string | null;
  type: ResearchReportType | null;
  model_label: string | null;
  generated_at: string | null;
  reasoning_effort: string | null;
};

export type ResearchReportsUnreadCount = {
  unread_count: number;
  daily: number;
  weekly: number;
};

export const RESEARCH_REPORTS_UNREAD_UPDATED = "brokerai:research-reports-unread-updated";

export function notifyResearchReportsUnreadUpdated(): void {
  window.dispatchEvent(new Event(RESEARCH_REPORTS_UNREAD_UPDATED));
}

export type BackgroundTaskAccepted = {
  task_id: string;
  status: "accepted";
};

export type BackgroundTask = {
  id: string;
  kind: string;
  label: string;
  status: "running" | "success" | "failed" | "skipped" | "cancelled";
  message: string;
  step: string;
  progress: number;
  started_at: string;
  finished_at?: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  cancellable?: boolean;
  cancel_requested_at?: string | null;
};

export type BackgroundTaskCompletedDetail = {
  kind: string;
  status: BackgroundTask["status"];
  result?: Record<string, unknown> | null;
  error?: string | null;
};

export const BACKGROUND_TASK_COMPLETED_EVENT = "background-task:completed";

export const RESEARCH_TASK_KINDS = {
  daily: "research_daily",
  dailyRerun: "research_daily_rerun",
  weeklyBrief: "research_weekly_brief",
  weeklyDebrief: "research_weekly_debrief",
} as const;

export const TRADE_SYNC_TASK_KIND = "trade_sync";

export type TradeSyncResult = {
  configured: boolean;
  imported: number;
  updated: number;
  closed: number;
  backfilled: number;
  skipped: number;
  lots_upserted?: number;
  events_upserted?: number;
  enriched?: number;
  backfilled_lot_ids?: string[];
  error?: string;
  mode?: string;
};

export type ResearchRunDailyResult = {
  ok: boolean;
  report_path: string | null;
  model_report_paths: string[];
  groups_processed: string[];
  errors: string[];
  skipped_reason: string | null;
};

export type ResearchRunWeeklyResult = {
  ok: boolean;
  report_path: string | null;
  week_key: string | null;
  errors: string[];
  skipped_reason: string | null;
};

export type StrategyType = "preset" | "custom";

export type BacktestStatus =
  | "not_run"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type BacktestRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type BacktestPeriod = "1m" | "3m" | "6m" | "1y" | "2y" | "5y";

export type BacktestRunStats = {
  total_trades: number | null;
  win_rate: number | null;
  realized_pnl: number | null;
  max_drawdown: number | null;
};

export type BacktestEquityPoint = {
  time: string;
  equity: number;
};

export type BacktestAiFeedbackStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed";

export type BacktestAiSuggestion = {
  id: string;
  path: string;
  label?: string;
  from?: unknown;
  to: unknown;
  rationale?: string;
  priority?: number;
  test_alone?: boolean;
};

export type BacktestAiMemoryNote = {
  id: string;
  kind: "standing_rule" | "anti_rule" | "lesson" | "note" | string;
  text: string;
  bias?: string | null;
  keywords?: string[];
  priority?: number;
};

export type BacktestAiFeedback = {
  status: BacktestAiFeedbackStatus;
  model_id: string | null;
  model_name: string | null;
  reasoning_effort: ReasoningEffort | null;
  markdown: string | null;
  suggestions?: BacktestAiSuggestion[];
  memory_notes?: BacktestAiMemoryNote[];
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  usage?: Record<string, unknown> | null;
};

export type BacktestRun = {
  id: string;
  name?: string;
  strategy_id: string;
  strategy_name: string;
  asset_class: AssetClass | string;
  asset_class_label: string;
  timeframe?: string | null;
  instruments: string[];
  instrument?: string | null;
  period?: BacktestPeriod | string;
  period_start?: string | null;
  period_end?: string | null;
  account_margin?: number;
  verbose?: boolean;
  status: BacktestRunStatus;
  progress_pct?: number;
  current_bar?: string | null;
  status_message?: string | null;
  cancel_requested?: boolean;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  stats: BacktestRunStats;
  equity_curve?: BacktestEquityPoint[];
  params_snapshot?: Record<string, unknown> | null;
  ai_feedback?: BacktestAiFeedback | null;
  origin?: string | null;
  cadence_key?: string | null;
  digest_version?: string | number | null;
};

export type BacktestLog = {
  id: number;
  run_id: string;
  level: string;
  message: string;
  meta?: Record<string, unknown> | null;
  created_at: string;
};

export type BacktestAction = {
  id: number;
  run_id: string;
  sequence: number;
  kind: string;
  message: string;
  bar_time?: string | null;
  meta?: Record<string, unknown> | null;
  created_at: string;
};

export type BacktestSettings = {
  max_concurrent: number;
  auto_start: boolean;
  ai_feedback_enabled: boolean;
  ai_feedback_auto_on_complete: boolean;
  ai_feedback_model_id: string | null;
  ai_feedback_model_name: string | null;
  ai_feedback_reasoning_effort: ReasoningEffort;
  daily_ai_strategy_backtest_enabled?: boolean;
  daily_ai_strategy_backtest_period?: BacktestPeriod | string;
};

export type AiStrategySettings = {
  startup_enabled: boolean;
  startup_loop_count: number;
  startup_backtest_period: BacktestPeriod | string;
  startup_timeout_minutes: number;
};

export type AiStrategyStartupJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type AiStrategyStartupJobPhase =
  | "ensuring_reports"
  | "seeding_digest"
  | "looping"
  | "done";

export type AiStrategyStartupJob = {
  id: string;
  strategy_id: string;
  status: AiStrategyStartupJobStatus;
  phase: AiStrategyStartupJobPhase;
  loop_index?: number;
  loop_target?: number;
  required_reports?: string[];
  skipped_reports?: string[];
  pending_reports?: string[];
  current_backtest_run_id?: string | null;
  seed_digest_version?: number | null;
  status_message?: string | null;
  last_seed_wait?: string | null;
  error?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
};

export type AiStrategyActivityKind =
  | "startup"
  | "backtest"
  | "digest"
  | "learning"
  | "lifecycle"
  | "version";

export type AiStrategyActivityEvent = {
  id: string;
  kind: AiStrategyActivityKind | string;
  status: string;
  title: string;
  detail?: string | null;
  occurred_at: string;
  href?: string | null;
  meta?: Record<string, unknown>;
};

export type AiStrategyDigestSummary = {
  id?: string;
  version?: number | null;
  created_at?: string | null;
  source?: string | null;
  summary?: string | null;
  standing_rule_count?: number;
  anti_rule_count?: number;
  standing_rules?: string[];
  anti_rules?: string[];
};

export type AiStrategyActivityResponse = {
  strategy: Strategy;
  startup_job: AiStrategyStartupJob | null;
  latest_digest: AiStrategyDigestSummary | null;
  events: AiStrategyActivityEvent[];
  active: boolean;
};

export type BacktestRunsResponse = {
  runs: BacktestRun[];
  latest: BacktestRun | null;
};

export type StrategyStats = {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number | null;
  realized_pnl: number;
  open_positions: number;
  last_trade_at: string | null;
};

/** AI Strategy lifecycle phase (strategy doc, not params). */
export type StrategyExecutionPhase = "warming" | "ready" | "live";

export type StrategyWarmup = {
  unit?: string;
  target_days?: number | null;
  min_closed_bars_per_day?: number;
  episode_id?: string;
  started_at?: string | null;
  eligible_trading_days?: string[];
  completed_days?: number;
  bars_today_et?: number;
  current_trading_day_et?: string | null;
  ready_at?: string | null;
  live_at?: string | null;
};

export type StrategyAiImprove = {
  enabled?: boolean;
  last_queued_et_date?: string | null;
  skip_reason?: string | null;
};

export type Strategy = {
  id: string;
  name: string;
  asset_class: AssetClass;
  asset_class_label: string;
  timeframe?: Timeframe;
  description: string;
  enabled: boolean;
  backtest_status?: BacktestStatus;
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
  /** Present on AI Strategy docs after create. */
  execution_phase?: StrategyExecutionPhase;
  warmup?: StrategyWarmup;
  ai_improve?: StrategyAiImprove;
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

export type StrategyVersionSummary = {
  id: string;
  strategy_id: string;
  version: number;
  created_at: string | null;
  change_label: string;
};

export type StrategyVersionSnapshot = {
  name: string;
  description: string;
  params: StrategyParamsV1;
  instrument_selection: StrategyInstrumentSelection;
  enabled: boolean;
  preset_id?: string | null;
};

export type StrategyVersionDetail = StrategyVersionSummary & {
  snapshot: StrategyVersionSnapshot;
};

export type StrategyVersionsResponse = {
  versions: StrategyVersionSummary[];
  total: number;
  limit: number;
  offset: number;
};

export const STRATEGY_VERSIONS_PAGE_SIZE = 20;

export type ConfigBackupKind = "change" | "full";
export type ConfigBackupPayloadType = "full" | "incremental";
export type ConfigBackupSource = "manual" | "scheduled" | "baseline" | "import";
export type ConfigBackupRestoreScope = "setting" | "full";

export type ConfigBackupSummary = {
  id: string;
  kind: ConfigBackupKind;
  payload_type?: ConfigBackupPayloadType;
  source?: ConfigBackupSource | null;
  base_backup_id?: string | null;
  label?: string | null;
  trigger: string;
  summary: string;
  created_at: string;
  schema_version: number;
  category?: string;
  change_label?: string;
  included_areas?: string[];
};

export type ConfigBackupRecord = ConfigBackupSummary & {
  payload: Record<string, unknown>;
};

export type ConfigBackupRestoreResult = {
  restored_id: string;
  safety_backup_id?: string | null;
  safety_backup?: ConfigBackupSummary | null;
  summary?: string | null;
  scope?: ConfigBackupRestoreScope;
};

export type BackupScheduleSettingsInput = {
  enabled?: boolean;
  mode?: "daily" | "daily_time" | "interval";
  daily_market_id?: string;
  daily_offset_hours?: number;
  daily_time?: string;
  interval_hours?: number;
  full_retention?: number;
  change_retention?: number;
};

export type BackupScheduleSettings = BackupScheduleSettingsInput & {
  last_scheduled_at?: string | null;
  schedule_markets?: ResearchScheduleMarket[];
  schedule_timezone?: string;
};

export type ConfigBackupTimeline = {
  items: ConfigBackupSummary[];
  total: number;
};

export type BackupListResponse = {
  timeline: ConfigBackupTimeline;
  full_retention: number;
  change_retention: number;
};

export const BACKUP_TIMELINE_PAGE_SIZE = 25;

export type ConfigBackupImportResult = {
  backup: ConfigBackupSummary;
  restored?: boolean;
  safety_backup_id?: string | null;
  safety_backup?: ConfigBackupSummary | null;
};

export type { StrategyParamsV1, StrategyPresetMeta, Timeframe };
