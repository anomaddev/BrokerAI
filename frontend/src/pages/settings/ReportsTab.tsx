import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type AiModel,
  type ContributorModel,
  type ReasoningEffort,
  type ResearchScheduleMarket,
  type WeeklyPromptPreview,
} from "../../api/client";
import ToggleSwitch from "../../components/ToggleSwitch";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import useAutoSave from "../../hooks/useAutoSave";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import {
  catalogSelectionKey,
  getProvider,
  parseCatalogSelectionKey,
  providerLabel,
} from "./modelProviders";

type CatalogOption = {
  key: string;
  sourceId: string;
  modelName: string;
  label: string;
  sourceTitle: string;
  providerType: string;
  sourceEnabled: boolean;
};
import {
  closeOffsetLabel,
  closeSchedulePreviewParts,
  DEFAULT_DAILY_REPORT_MARKET_ID,
  DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
  DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
  DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
  findScheduleMarket,
  formatScheduleMarketOptionLabel,
  MARKET_OFFSET_OPTIONS,
  offsetLabel,
  schedulePreviewParts,
  weeklyBriefSchedulePreviewParts,
} from "./researchMarkets";

const REASONING_OPTIONS: { value: ReasoningEffort; label: string }[] = [
  { value: "none", label: "None" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const DEFAULT_REASONING: ReasoningEffort = "high";

function ReasoningSelect({
  value,
  disabled,
  onChange,
  id,
}: {
  value: ReasoningEffort;
  disabled?: boolean;
  onChange: (value: ReasoningEffort) => void;
  id?: string;
}) {
  return (
    <div className="research-select-wrap">
      <select
        id={id}
        className="research-select"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as ReasoningEffort)}
      >
        {REASONING_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function PromptPreviewModal({
  title,
  preview,
  onClose,
}: {
  title: string;
  preview: WeeklyPromptPreview;
  onClose: () => void;
}) {
  return (
    <div className="settings-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="settings-modal research-prompt-modal"
        role="dialog"
        aria-labelledby="prompt-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-modal-header">
          <h3 id="prompt-modal-title">{title}</h3>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="settings-modal-body research-prompt-modal-body">
          <p className="settings-muted">
            Read-only preview. Prompt editing will be available in a future release.
          </p>
          <h4 className="research-prompt-section-title">System prompt</h4>
          <pre className="research-prompt-block">{preview.system_prompt}</pre>
          <h4 className="research-prompt-section-title">User message template</h4>
          <pre className="research-prompt-block">{preview.user_template}</pre>
        </div>
      </div>
    </div>
  );
}

type ReportsSnapshot = {
  models: AiModel[];
  catalog: CatalogOption[];
  contributors: Record<string, ContributorModel>;
  synthesisModelId: string | null;
  synthesisModelName: string | null;
  synthesisReasoning: ReasoningEffort;
  dailyReportEnabled: boolean;
  scheduleMarkets: ResearchScheduleMarket[];
  dailyReportMarketId: string;
  dailyReportMarketOffsetHours: number;
  weeklyBriefEnabled: boolean;
  weeklyBriefModelId: string | null;
  weeklyBriefModelName: string | null;
  weeklyBriefReasoning: ReasoningEffort;
  weeklyBriefMarketId: string;
  weeklyBriefMarketOffsetHours: number;
  weeklyDebriefEnabled: boolean;
  weeklyDebriefModelId: string | null;
  weeklyDebriefModelName: string | null;
  weeklyDebriefReasoning: ReasoningEffort;
  weeklyDebriefMarketId: string;
  weeklyDebriefMarketOffsetHours: number;
};

export default function ReportsTab() {
  const { timeOptions } = useGeneralSettings();
  const [models, setModels] = useState<AiModel[]>([]);
  const [catalog, setCatalog] = useState<CatalogOption[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [contributors, setContributors] = useState<Record<string, ContributorModel>>({});
  const [synthesisModelId, setSynthesisModelId] = useState<string | null>(null);
  const [synthesisModelName, setSynthesisModelName] = useState<string | null>(null);
  const [synthesisReasoning, setSynthesisReasoning] = useState<ReasoningEffort>(DEFAULT_REASONING);

  const [dailyReportEnabled, setDailyReportEnabled] = useState(false);
  const [scheduleMarkets, setScheduleMarkets] = useState<ResearchScheduleMarket[]>([]);
  const [dailyReportMarketId, setDailyReportMarketId] = useState(DEFAULT_DAILY_REPORT_MARKET_ID);
  const [dailyReportMarketOffsetHours, setDailyReportMarketOffsetHours] = useState(
    DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
  );

  const [weeklyBriefEnabled, setWeeklyBriefEnabled] = useState(false);
  const [weeklyBriefModelId, setWeeklyBriefModelId] = useState<string | null>(null);
  const [weeklyBriefModelName, setWeeklyBriefModelName] = useState<string | null>(null);
  const [weeklyBriefReasoning, setWeeklyBriefReasoning] = useState<ReasoningEffort>(DEFAULT_REASONING);
  const [weeklyBriefMarketId, setWeeklyBriefMarketId] = useState(DEFAULT_DAILY_REPORT_MARKET_ID);
  const [weeklyBriefMarketOffsetHours, setWeeklyBriefMarketOffsetHours] = useState(
    DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
  );

  const [weeklyDebriefEnabled, setWeeklyDebriefEnabled] = useState(false);
  const [weeklyDebriefModelId, setWeeklyDebriefModelId] = useState<string | null>(null);
  const [weeklyDebriefModelName, setWeeklyDebriefModelName] = useState<string | null>(null);
  const [weeklyDebriefReasoning, setWeeklyDebriefReasoning] =
    useState<ReasoningEffort>(DEFAULT_REASONING);
  const [weeklyDebriefMarketId, setWeeklyDebriefMarketId] = useState(DEFAULT_DAILY_REPORT_MARKET_ID);
  const [weeklyDebriefMarketOffsetHours, setWeeklyDebriefMarketOffsetHours] = useState(
    DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
  );

  const [scheduleWarnings, setScheduleWarnings] = useState<string[]>([]);
  const [briefPromptPreview, setBriefPromptPreview] = useState<WeeklyPromptPreview | null>(null);
  const [debriefPromptPreview, setDebriefPromptPreview] = useState<WeeklyPromptPreview | null>(
    null,
  );
  const [promptModal, setPromptModal] = useState<"brief" | "debrief" | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const enabledCatalog = useMemo(
    () => catalog.filter((item) => item.sourceEnabled),
    [catalog],
  );

  const snapshotRef = useRef<ReportsSnapshot>({
    models: [],
    catalog: [],
    contributors: {},
    synthesisModelId: null,
    synthesisModelName: null,
    synthesisReasoning: DEFAULT_REASONING,
    dailyReportEnabled: false,
    scheduleMarkets: [],
    dailyReportMarketId: DEFAULT_DAILY_REPORT_MARKET_ID,
    dailyReportMarketOffsetHours: DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
    weeklyBriefEnabled: false,
    weeklyBriefModelId: null,
    weeklyBriefModelName: null,
    weeklyBriefReasoning: DEFAULT_REASONING,
    weeklyBriefMarketId: DEFAULT_DAILY_REPORT_MARKET_ID,
    weeklyBriefMarketOffsetHours: DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
    weeklyDebriefEnabled: false,
    weeklyDebriefModelId: null,
    weeklyDebriefModelName: null,
    weeklyDebriefReasoning: DEFAULT_REASONING,
    weeklyDebriefMarketId: DEFAULT_DAILY_REPORT_MARKET_ID,
    weeklyDebriefMarketOffsetHours: DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
  });

  snapshotRef.current = {
    models,
    catalog,
    contributors,
    synthesisModelId,
    synthesisModelName,
    synthesisReasoning,
    dailyReportEnabled,
    scheduleMarkets,
    dailyReportMarketId,
    dailyReportMarketOffsetHours,
    weeklyBriefEnabled,
    weeklyBriefModelId,
    weeklyBriefModelName,
    weeklyBriefReasoning,
    weeklyBriefMarketId,
    weeklyBriefMarketOffsetHours,
    weeklyDebriefEnabled,
    weeklyDebriefModelId,
    weeklyDebriefModelName,
    weeklyDebriefReasoning,
    weeklyDebriefMarketId,
    weeklyDebriefMarketOffsetHours,
  };

  const applySavedSettings = useCallback(
    (saved: Awaited<ReturnType<typeof api.getResearchSettings>>) => {
      const map: Record<string, ContributorModel> = {};
      for (const entry of saved.contributor_models ?? []) {
        const modelName = entry.model_name || "";
        if (!modelName) continue;
        map[catalogSelectionKey(entry.model_id, modelName)] = {
          ...entry,
          model_name: modelName,
        };
      }
      setContributors(map);
      setSynthesisModelId(saved.synthesis_model_id ?? null);
      setSynthesisModelName(saved.synthesis_model_name ?? null);
      setSynthesisReasoning(saved.synthesis_reasoning_effort ?? DEFAULT_REASONING);
      setDailyReportEnabled(saved.daily_report_enabled ?? false);
      setScheduleMarkets((prev) => saved.schedule_markets ?? prev);
      setDailyReportMarketId(saved.daily_report_market_id ?? DEFAULT_DAILY_REPORT_MARKET_ID);
      setDailyReportMarketOffsetHours(
        saved.daily_report_market_offset_hours ?? DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
      );
      setWeeklyBriefEnabled(saved.weekly_brief_enabled ?? false);
      setWeeklyBriefModelId(saved.weekly_brief_model_id ?? null);
      setWeeklyBriefModelName(saved.weekly_brief_model_name ?? null);
      setWeeklyBriefReasoning(saved.weekly_brief_reasoning_effort ?? DEFAULT_REASONING);
      setWeeklyBriefMarketId(saved.weekly_brief_market_id ?? DEFAULT_DAILY_REPORT_MARKET_ID);
      setWeeklyBriefMarketOffsetHours(
        saved.weekly_brief_market_offset_hours ?? DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
      );
      setWeeklyDebriefEnabled(saved.weekly_debrief_enabled ?? false);
      setWeeklyDebriefModelId(saved.weekly_debrief_model_id ?? null);
      setWeeklyDebriefModelName(saved.weekly_debrief_model_name ?? null);
      setWeeklyDebriefReasoning(saved.weekly_debrief_reasoning_effort ?? DEFAULT_REASONING);
      setWeeklyDebriefMarketId(saved.weekly_debrief_market_id ?? DEFAULT_DAILY_REPORT_MARKET_ID);
      setWeeklyDebriefMarketOffsetHours(
        saved.weekly_debrief_market_offset_hours ?? DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
      );
      setScheduleWarnings(saved.schedule_warnings ?? []);
      setBriefPromptPreview(saved.weekly_brief_prompt_preview ?? null);
      setDebriefPromptPreview(saved.weekly_debrief_prompt_preview ?? null);
    },
    [],
  );

  const loadCatalog = useCallback(async (sources: AiModel[]) => {
    const enabled = sources.filter((source) => source.enabled);
    const results = await Promise.all(
      enabled.map(async (source) => {
        try {
          const response = await api.listAvailableModels(source.id);
          return { source, response };
        } catch (err) {
          return {
            source,
            response: {
              ok: false,
              message: err instanceof Error ? err.message : "Failed to list models",
              models: [] as Array<{ id: string; name: string }>,
            },
          };
        }
      }),
    );

    const next: CatalogOption[] = [];
    const errors: string[] = [];
    for (const { source, response } of results) {
      if (!response.ok) {
        errors.push(`${source.title}: ${response.message}`);
        const fallback =
          source.default_model_name || source.model_name || "";
        if (fallback) {
          next.push({
            key: catalogSelectionKey(source.id, fallback),
            sourceId: source.id,
            modelName: fallback,
            label: `${source.title} · ${fallback}`,
            sourceTitle: source.title,
            providerType: source.type,
            sourceEnabled: source.enabled,
          });
        }
        continue;
      }
      for (const model of response.models) {
        next.push({
          key: catalogSelectionKey(source.id, model.id),
          sourceId: source.id,
          modelName: model.id,
          label: `${source.title} · ${model.name || model.id}`,
          sourceTitle: source.title,
          providerType: source.type,
          sourceEnabled: source.enabled,
        });
      }
    }
    setCatalog(next);
    setCatalogError(errors.length ? errors.join("; ") : null);
  }, []);

  const saveEpochRef = useRef(0);
  const dirtyDailyRef = useRef(false);
  const dirtyWeeklyRef = useRef(false);

  const persistReportsSettings = useCallback(async () => {
    const epoch = ++saveEpochRef.current;
    const snapshot = snapshotRef.current;
    const saveDaily = dirtyDailyRef.current;
    const saveWeekly = dirtyWeeklyRef.current;
    if (!saveDaily && !saveWeekly) return;

    // Clear before awaits so edits during the request re-dirty and coalesce.
    dirtyDailyRef.current = false;
    dirtyWeeklyRef.current = false;

    const enabledSourceIds = new Set(
      snapshot.models.filter((m) => m.enabled).map((m) => m.id),
    );

    const contributorList = Object.values(snapshot.contributors).filter(
      (c) => c.enabled && c.model_name && enabledSourceIds.has(c.model_id),
    );

    let saved: Awaited<ReturnType<typeof api.saveWeeklyResearchSettings>> | null = null;
    let dailyDone = false;
    let weeklyDone = false;

    try {
      // Only hit the endpoints whose fields changed. Each PUT runs config backup;
      // doing both on every toggle was a major source of multi-second lag.
      if (saveDaily) {
        saved = await api.saveResearchSettings({
          contributor_models: contributorList,
          synthesis_model_id: snapshot.synthesisModelId,
          synthesis_model_name: snapshot.synthesisModelName,
          synthesis_reasoning_effort: snapshot.synthesisReasoning,
          daily_report_enabled: snapshot.dailyReportEnabled,
          daily_report_market_id: snapshot.dailyReportMarketId,
          daily_report_market_offset_hours: snapshot.dailyReportMarketOffsetHours,
        });
        dailyDone = true;
      }

      if (saveWeekly) {
        saved = await api.saveWeeklyResearchSettings({
          weekly_brief_enabled: snapshot.weeklyBriefEnabled,
          weekly_brief_model_id: snapshot.weeklyBriefModelId,
          weekly_brief_model_name: snapshot.weeklyBriefModelName,
          weekly_brief_reasoning_effort: snapshot.weeklyBriefReasoning,
          weekly_brief_market_id: snapshot.weeklyBriefMarketId,
          weekly_brief_market_offset_hours: snapshot.weeklyBriefMarketOffsetHours,
          weekly_debrief_enabled: snapshot.weeklyDebriefEnabled,
          weekly_debrief_model_id: snapshot.weeklyDebriefModelId,
          weekly_debrief_model_name: snapshot.weeklyDebriefModelName,
          weekly_debrief_reasoning_effort: snapshot.weeklyDebriefReasoning,
          weekly_debrief_market_id: snapshot.weeklyDebriefMarketId,
          weekly_debrief_market_offset_hours: snapshot.weeklyDebriefMarketOffsetHours,
        });
        weeklyDone = true;
      }
    } catch (err) {
      // Re-queue only the sections that did not complete so the next pass retries.
      if (saveDaily && !dailyDone) dirtyDailyRef.current = true;
      if (saveWeekly && !weeklyDone) dirtyWeeklyRef.current = true;
      throw err;
    }

    // Ignore stale responses so an older in-flight save cannot overwrite optimistic
    // toggle/UI state (that race made Enable switches feel delayed).
    if (epoch !== saveEpochRef.current || !saved) return;

    // Only sync server-derived fields; local form state is already optimistic.
    setScheduleWarnings(saved.schedule_warnings ?? []);
    setBriefPromptPreview(saved.weekly_brief_prompt_preview ?? null);
    setDebriefPromptPreview(saved.weekly_debrief_prompt_preview ?? null);
  }, []);

  const { saveStatus, saveNow, markReady, markNotReady, error: saveError } =
    useAutoSave({
      onSave: persistReportsSettings,
      canSave: () => !loading && models.length > 0,
    });

  useEffect(() => {
    (async () => {
      markNotReady();
      setLoading(true);
      try {
        const [modelsData, settings] = await Promise.all([
          api.listModels(),
          api.getResearchSettings(),
        ]);
        setModels(modelsData.models);
        applySavedSettings(settings);
        // Settings toggles should be interactive immediately; catalog listing can
        // hang on slow provider APIs and must not gate Enable switches.
        markReady();
        setLoading(false);
        void loadCatalog(modelsData.models);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load report settings");
        setLoading(false);
      }
    })();
  }, [applySavedSettings, loadCatalog, markNotReady, markReady]);

  const contributorCount = useMemo(
    () => Object.values(contributors).filter((c) => c.enabled).length,
    [contributors],
  );

  const displayCatalog = useMemo(() => {
    const byKey = new Map(catalog.map((item) => [item.key, item]));
    for (const [key, entry] of Object.entries(contributors)) {
      if (!entry.model_name || byKey.has(key)) continue;
      const source = models.find((m) => m.id === entry.model_id);
      byKey.set(key, {
        key,
        sourceId: entry.model_id,
        modelName: entry.model_name,
        label: `${source?.title || providerLabel(source?.type || "")} · ${entry.model_name}`,
        sourceTitle: source?.title || "Source",
        providerType: source?.type || "",
        sourceEnabled: Boolean(source?.enabled),
      });
    }
    for (const [sourceId, modelName] of [
      [synthesisModelId, synthesisModelName],
      [weeklyBriefModelId, weeklyBriefModelName],
      [weeklyDebriefModelId, weeklyDebriefModelName],
    ] as const) {
      if (!sourceId || !modelName) continue;
      const key = catalogSelectionKey(sourceId, modelName);
      if (byKey.has(key)) continue;
      const source = models.find((m) => m.id === sourceId);
      byKey.set(key, {
        key,
        sourceId,
        modelName,
        label: `${source?.title || "Source"} · ${modelName}`,
        sourceTitle: source?.title || "Source",
        providerType: source?.type || "",
        sourceEnabled: Boolean(source?.enabled),
      });
    }
    return Array.from(byKey.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [
    catalog,
    contributors,
    models,
    synthesisModelId,
    synthesisModelName,
    weeklyBriefModelId,
    weeklyBriefModelName,
    weeklyDebriefModelId,
    weeklyDebriefModelName,
  ]);

  function contributorFor(sourceId: string, modelName: string): ContributorModel {
    const key = catalogSelectionKey(sourceId, modelName);
    return (
      contributors[key] ?? {
        model_id: sourceId,
        model_name: modelName,
        reasoning_effort: DEFAULT_REASONING,
        enabled: false,
      }
    );
  }

  function markDailyDirty() {
    dirtyDailyRef.current = true;
  }

  function markWeeklyDirty() {
    dirtyWeeklyRef.current = true;
  }

  function patchSnapshot(patch: Partial<ReportsSnapshot>) {
    snapshotRef.current = { ...snapshotRef.current, ...patch };
    const touchesDaily =
      patch.dailyReportEnabled !== undefined ||
      patch.dailyReportMarketId !== undefined ||
      patch.dailyReportMarketOffsetHours !== undefined ||
      patch.synthesisModelId !== undefined ||
      patch.synthesisModelName !== undefined ||
      patch.synthesisReasoning !== undefined;
    const touchesWeekly =
      patch.weeklyBriefEnabled !== undefined ||
      patch.weeklyBriefModelId !== undefined ||
      patch.weeklyBriefModelName !== undefined ||
      patch.weeklyBriefReasoning !== undefined ||
      patch.weeklyBriefMarketId !== undefined ||
      patch.weeklyBriefMarketOffsetHours !== undefined ||
      patch.weeklyDebriefEnabled !== undefined ||
      patch.weeklyDebriefModelId !== undefined ||
      patch.weeklyDebriefModelName !== undefined ||
      patch.weeklyDebriefReasoning !== undefined ||
      patch.weeklyDebriefMarketId !== undefined ||
      patch.weeklyDebriefMarketOffsetHours !== undefined;
    if (touchesDaily) markDailyDirty();
    if (touchesWeekly) markWeeklyDirty();

    // Keep React state in sync immediately so toggles/selects don't wait on save.
    if (patch.dailyReportEnabled !== undefined) setDailyReportEnabled(patch.dailyReportEnabled);
    if (patch.dailyReportMarketId !== undefined) setDailyReportMarketId(patch.dailyReportMarketId);
    if (patch.dailyReportMarketOffsetHours !== undefined) {
      setDailyReportMarketOffsetHours(patch.dailyReportMarketOffsetHours);
    }
    if (patch.synthesisModelId !== undefined) setSynthesisModelId(patch.synthesisModelId);
    if (patch.synthesisModelName !== undefined) setSynthesisModelName(patch.synthesisModelName);
    if (patch.synthesisReasoning !== undefined) setSynthesisReasoning(patch.synthesisReasoning);
    if (patch.weeklyBriefEnabled !== undefined) setWeeklyBriefEnabled(patch.weeklyBriefEnabled);
    if (patch.weeklyBriefModelId !== undefined) setWeeklyBriefModelId(patch.weeklyBriefModelId);
    if (patch.weeklyBriefModelName !== undefined) setWeeklyBriefModelName(patch.weeklyBriefModelName);
    if (patch.weeklyBriefReasoning !== undefined) setWeeklyBriefReasoning(patch.weeklyBriefReasoning);
    if (patch.weeklyBriefMarketId !== undefined) setWeeklyBriefMarketId(patch.weeklyBriefMarketId);
    if (patch.weeklyBriefMarketOffsetHours !== undefined) {
      setWeeklyBriefMarketOffsetHours(patch.weeklyBriefMarketOffsetHours);
    }
    if (patch.weeklyDebriefEnabled !== undefined) setWeeklyDebriefEnabled(patch.weeklyDebriefEnabled);
    if (patch.weeklyDebriefModelId !== undefined) setWeeklyDebriefModelId(patch.weeklyDebriefModelId);
    if (patch.weeklyDebriefModelName !== undefined) {
      setWeeklyDebriefModelName(patch.weeklyDebriefModelName);
    }
    if (patch.weeklyDebriefReasoning !== undefined) {
      setWeeklyDebriefReasoning(patch.weeklyDebriefReasoning);
    }
    if (patch.weeklyDebriefMarketId !== undefined) setWeeklyDebriefMarketId(patch.weeklyDebriefMarketId);
    if (patch.weeklyDebriefMarketOffsetHours !== undefined) {
      setWeeklyDebriefMarketOffsetHours(patch.weeklyDebriefMarketOffsetHours);
    }
    saveNow();
  }

  function toggleContributor(sourceId: string, modelName: string, enabled: boolean) {
    const key = catalogSelectionKey(sourceId, modelName);
    markDailyDirty();
    setContributors((prev) => {
      const next = {
        ...prev,
        [key]: {
          ...contributorFor(sourceId, modelName),
          model_id: sourceId,
          model_name: modelName,
          enabled,
        },
      };
      snapshotRef.current = { ...snapshotRef.current, contributors: next };
      return next;
    });
    saveNow();
  }

  function setContributorReasoning(
    sourceId: string,
    modelName: string,
    reasoning: ReasoningEffort,
  ) {
    const key = catalogSelectionKey(sourceId, modelName);
    markDailyDirty();
    setContributors((prev) => {
      const next = {
        ...prev,
        [key]: {
          ...contributorFor(sourceId, modelName),
          model_id: sourceId,
          model_name: modelName,
          reasoning_effort: reasoning,
        },
      };
      snapshotRef.current = { ...snapshotRef.current, contributors: next };
      return next;
    });
    saveNow();
  }

  const dailyMarket = useMemo(
    () => findScheduleMarket(scheduleMarkets, dailyReportMarketId),
    [scheduleMarkets, dailyReportMarketId],
  );
  const briefMarket = useMemo(
    () => findScheduleMarket(scheduleMarkets, weeklyBriefMarketId),
    [scheduleMarkets, weeklyBriefMarketId],
  );
  const debriefMarket = useMemo(
    () => findScheduleMarket(scheduleMarkets, weeklyDebriefMarketId),
    [scheduleMarkets, weeklyDebriefMarketId],
  );

  const dailyPreview = useMemo(
    () => schedulePreviewParts(dailyMarket, dailyReportMarketOffsetHours, new Date(), timeOptions),
    [dailyMarket, dailyReportMarketOffsetHours, timeOptions],
  );
  const briefPreview = useMemo(
    () => weeklyBriefSchedulePreviewParts(briefMarket, weeklyBriefMarketOffsetHours, new Date(), timeOptions),
    [briefMarket, weeklyBriefMarketOffsetHours, timeOptions],
  );
  const debriefPreview = useMemo(
    () => closeSchedulePreviewParts(debriefMarket, weeklyDebriefMarketOffsetHours, new Date(), timeOptions),
    [debriefMarket, weeklyDebriefMarketOffsetHours, timeOptions],
  );

  const headerError = error ?? saveError;

  function renderScheduleFields({
    idPrefix,
    marketId,
    offsetHours,
    enabled,
    onMarketChange,
    onOffsetChange,
    offsetOptionsLabel,
  }: {
    idPrefix: string;
    marketId: string;
    offsetHours: number;
    enabled: boolean;
    onMarketChange: (value: string) => void;
    onOffsetChange: (value: number) => void;
    offsetOptionsLabel: (hours: number) => string;
  }) {
    return (
      <div className="research-schedule-fields">
        <div className="research-field research-schedule-field">
          <label className="research-field-label" htmlFor={`${idPrefix}-market`}>
            Market
          </label>
          <div className="research-select-wrap">
            <select
              id={`${idPrefix}-market`}
              className="research-select"
              value={marketId}
              disabled={!enabled}
              onChange={(e) => onMarketChange(e.target.value)}
            >
              {scheduleMarkets.map((market) => (
                <option key={market.id} value={market.id}>
                  {formatScheduleMarketOptionLabel(market, timeOptions)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="research-field research-schedule-field">
          <label className="research-field-label" htmlFor={`${idPrefix}-offset`}>
            Run time
          </label>
          <div className="research-select-wrap">
            <select
              id={`${idPrefix}-offset`}
              className="research-select"
              value={offsetHours}
              disabled={!enabled}
              onChange={(e) => onOffsetChange(Number(e.target.value))}
            >
              {MARKET_OFFSET_OPTIONS.map((hours) => (
                <option key={hours} value={hours}>
                  {offsetOptionsLabel(hours)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Reports"
        description={
          <>
            Configure analysis models, schedules, and synthesis for daily and weekly research
            reports. Data sources are under{" "}
            <Link to="/settings/data">Research → Data</Link>.
          </>
        }
        error={headerError}
        saveStatus={saveStatus}
      />

      <div className="settings-panel-body">
        {loading ? (
          <p className="settings-muted">Loading…</p>
        ) : models.length === 0 ? (
          <div className="research-empty-callout">
            <p className="research-empty-callout-title">No API sources configured</p>
            <p className="settings-muted">Add a provider under Settings → Models to get started.</p>
            <Link to="/settings/models" className="btn btn-secondary btn-sm research-empty-link">
              Go to Models
            </Link>
          </div>
        ) : (
          <div className="research-stack">
            {scheduleWarnings.length > 0 && (
              <div className="settings-callout settings-callout-warning">
                {scheduleWarnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            )}
            {catalogError && (
              <div className="settings-callout settings-callout-warning">
                <p>Could not load some model catalogs: {catalogError}</p>
              </div>
            )}

            <section className="settings-card research-card">
              <div className="settings-card-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">Analysis models</h3>
                  <p className="settings-muted">
                    Models available from your connected API sources. Each enabled model writes its
                    own report from the same sources.
                  </p>
                </div>
                {contributorCount > 0 && (
                  <span className="research-selection-count">{contributorCount} enabled</span>
                )}
              </div>

              {displayCatalog.length === 0 ? (
                <p className="settings-muted">
                  No models listed yet. Check API keys under Settings → Models, then refresh.
                </p>
              ) : (
              <ul className="research-model-checklist">
                {displayCatalog.map((option) => {
                  const provider = getProvider(option.providerType);
                  const contributor = contributorFor(option.sourceId, option.modelName);
                  const rowDisabled = !option.sourceEnabled;

                  return (
                    <li
                      key={option.key}
                      className={`research-model-checklist-item${
                        contributor.enabled ? " research-model-checklist-item--selected" : ""
                      }${rowDisabled ? " research-model-checklist-item--disabled" : ""}`}
                    >
                      <div className="research-model-row-head">
                        <ToggleSwitch
                          label={`Enable ${option.label}`}
                          checked={contributor.enabled}
                          disabled={rowDisabled}
                          onChange={(checked) =>
                            toggleContributor(option.sourceId, option.modelName, checked)
                          }
                        />
                        {provider && (
                          <img
                            src={provider.logo}
                            alt=""
                            className="research-model-checklist-logo"
                            width={32}
                            height={32}
                          />
                        )}
                        <span className="research-model-checklist-meta">
                          <span className="research-model-checklist-title">{option.modelName}</span>
                          <span className="settings-muted">
                            {providerLabel(option.providerType)} · {option.sourceTitle}
                            {rowDisabled ? " · source disabled" : ""}
                          </span>
                        </span>
                        <div className="research-model-reasoning">
                          <span className="research-field-label">Reasoning</span>
                          <ReasoningSelect
                            value={contributor.reasoning_effort}
                            disabled={rowDisabled || !contributor.enabled}
                            onChange={(value) =>
                              setContributorReasoning(option.sourceId, option.modelName, value)
                            }
                          />
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
              )}
            </section>

            <div className="reports-section-intro">
              <h3 className="reports-section-title">Automation</h3>
              <p className="settings-muted">
                Each report runs once per cycle when enabled. The weekly brief waits for that
                day&apos;s daily report; the debrief runs after the week ends.
              </p>
            </div>

            <section className="settings-card research-card research-schedule-card">
              <div className="research-schedule-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">Daily report</h3>
                  <p className="settings-muted">
                    Scheduled run for contributor analysis on enabled forex pairs.
                  </p>
                </div>
                <div className="research-schedule-enable">
                  <span className="research-schedule-enable-label">Enable</span>
                  <ToggleSwitch
                    label="Enable daily report"
                    checked={dailyReportEnabled}
                    onChange={(next) => patchSnapshot({ dailyReportEnabled: next })}
                  />
                </div>
              </div>

              <div
                className={`research-schedule-panel${
                  dailyReportEnabled ? "" : " research-schedule-panel--disabled"
                }`}
              >
                <div
                  className={`research-schedule-panel-layout${
                    dailyReportEnabled && dailyPreview ? " research-schedule-panel-layout--split" : ""
                  }`}
                >
                  {renderScheduleFields({
                    idPrefix: "daily-report",
                    marketId: dailyReportMarketId,
                    offsetHours: dailyReportMarketOffsetHours,
                    enabled: dailyReportEnabled,
                    onMarketChange: (value) => patchSnapshot({ dailyReportMarketId: value }),
                    onOffsetChange: (value) =>
                      patchSnapshot({ dailyReportMarketOffsetHours: value }),
                    offsetOptionsLabel: offsetLabel,
                  })}

                  {dailyReportEnabled && dailyPreview && (
                    <div className="research-schedule-preview">
                      <span className="research-schedule-preview-kicker">Next run (today)</span>
                      <p className="research-schedule-preview-time">~{dailyPreview.runTimeUtc}</p>
                      <p className="research-schedule-preview-detail">
                        {dailyPreview.offsetLabel} · {dailyPreview.marketLabel} · opens{" "}
                        {dailyPreview.openTimeLocal} {dailyPreview.timezone}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section className="settings-card research-card">
              <div className="settings-card-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">Daily synthesis</h3>
                  <p className="settings-muted">
                    One model merges every analysis into the comprehensive daily report.
                  </p>
                </div>
              </div>

              <div className="research-final-grid">
                <div className="research-field">
                  <label className="research-field-label" htmlFor="synthesis-model">
                    Synthesis model
                  </label>
                  <div className="research-select-wrap">
                    <select
                      id="synthesis-model"
                      className="research-select"
                      value={
                        synthesisModelId && synthesisModelName
                          ? catalogSelectionKey(synthesisModelId, synthesisModelName)
                          : ""
                      }
                      onChange={(e) => {
                        const value = e.target.value;
                        if (!value) {
                          patchSnapshot({
                            synthesisModelId: null,
                            synthesisModelName: null,
                          });
                          return;
                        }
                        const parsed = parseCatalogSelectionKey(value);
                        if (!parsed) return;
                        patchSnapshot({
                          synthesisModelId: parsed.sourceId,
                          synthesisModelName: parsed.modelName,
                        });
                      }}
                    >
                      <option value="">
                        {contributorCount <= 1 ? "Use the single analysis model" : "Select a model…"}
                      </option>
                      {enabledCatalog.map((option) => (
                        <option key={option.key} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="research-field">
                  <label className="research-field-label" htmlFor="synthesis-reasoning">
                    Reasoning
                  </label>
                  <ReasoningSelect
                    id="synthesis-reasoning"
                    value={synthesisReasoning}
                    onChange={(next) => patchSnapshot({ synthesisReasoning: next })}
                  />
                </div>
              </div>
              {contributorCount > 1 && !synthesisModelId && (
                <p className="settings-muted research-reasoning-hint">
                  Select a synthesis model to combine the {contributorCount} analysis reports.
                </p>
              )}
            </section>

            <section className="settings-card research-card research-schedule-card">
              <div className="research-schedule-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">Weekly brief</h3>
                  <p className="settings-muted">
                    Opening direction and actions for the week — runs after the daily report.
                  </p>
                </div>
                <div className="research-schedule-enable">
                  <span className="research-schedule-enable-label">Enable</span>
                  <ToggleSwitch
                    label="Enable weekly brief"
                    checked={weeklyBriefEnabled}
                    onChange={(next) => patchSnapshot({ weeklyBriefEnabled: next })}
                  />
                </div>
              </div>

              <div
                className={`research-schedule-panel${
                  weeklyBriefEnabled ? "" : " research-schedule-panel--disabled"
                }`}
              >
                <div className="reports-weekly-model-row">
                  <div className="research-field">
                    <label className="research-field-label" htmlFor="weekly-brief-model">
                      Model
                    </label>
                    <div className="research-select-wrap">
                      <select
                        id="weekly-brief-model"
                        className="research-select"
                        value={
                          weeklyBriefModelId && weeklyBriefModelName
                            ? catalogSelectionKey(weeklyBriefModelId, weeklyBriefModelName)
                            : ""
                        }
                        disabled={!weeklyBriefEnabled}
                        onChange={(e) => {
                          const value = e.target.value;
                          if (!value) {
                            patchSnapshot({
                              weeklyBriefModelId: null,
                              weeklyBriefModelName: null,
                            });
                            return;
                          }
                          const parsed = parseCatalogSelectionKey(value);
                          if (!parsed) return;
                          patchSnapshot({
                            weeklyBriefModelId: parsed.sourceId,
                            weeklyBriefModelName: parsed.modelName,
                          });
                        }}
                      >
                        <option value="">Select a model…</option>
                        {enabledCatalog.map((option) => (
                          <option key={option.key} value={option.key}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="research-field">
                    <label className="research-field-label" htmlFor="weekly-brief-reasoning">
                      Reasoning
                    </label>
                    <ReasoningSelect
                      id="weekly-brief-reasoning"
                      value={weeklyBriefReasoning}
                      disabled={!weeklyBriefEnabled}
                      onChange={(next) => patchSnapshot({ weeklyBriefReasoning: next })}
                    />
                  </div>
                </div>

                <div
                  className={`research-schedule-panel-layout${
                    weeklyBriefEnabled && briefPreview ? " research-schedule-panel-layout--split" : ""
                  }`}
                >
                  {renderScheduleFields({
                    idPrefix: "weekly-brief",
                    marketId: weeklyBriefMarketId,
                    offsetHours: weeklyBriefMarketOffsetHours,
                    enabled: weeklyBriefEnabled,
                    onMarketChange: (value) => patchSnapshot({ weeklyBriefMarketId: value }),
                    onOffsetChange: (value) =>
                      patchSnapshot({ weeklyBriefMarketOffsetHours: value }),
                    offsetOptionsLabel: offsetLabel,
                  })}

                  {weeklyBriefEnabled && briefPreview && (
                    <div className="research-schedule-preview">
                      <span className="research-schedule-preview-kicker">Next run (week open)</span>
                      <p className="research-schedule-preview-time">
                        ~{briefPreview.runTimeUtc} · {briefPreview.runDate}
                      </p>
                      <p className="research-schedule-preview-detail">
                        {briefPreview.offsetLabel} · {briefPreview.marketLabel} · opens{" "}
                        {briefPreview.openTimeLocal} {briefPreview.timezone}
                      </p>
                    </div>
                  )}
                </div>

                {briefPromptPreview && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm research-prompt-view-btn"
                    onClick={() => setPromptModal("brief")}
                  >
                    View prompt
                  </button>
                )}
              </div>
            </section>

            <section className="settings-card research-card research-schedule-card">
              <div className="research-schedule-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">Weekly debrief</h3>
                  <p className="settings-muted">
                    End-of-week retrospective fed by daily reports and the weekly brief.
                  </p>
                </div>
                <div className="research-schedule-enable">
                  <span className="research-schedule-enable-label">Enable</span>
                  <ToggleSwitch
                    label="Enable weekly debrief"
                    checked={weeklyDebriefEnabled}
                    onChange={(next) => patchSnapshot({ weeklyDebriefEnabled: next })}
                  />
                </div>
              </div>

              <div
                className={`research-schedule-panel${
                  weeklyDebriefEnabled ? "" : " research-schedule-panel--disabled"
                }`}
              >
                <div className="reports-weekly-model-row">
                  <div className="research-field">
                    <label className="research-field-label" htmlFor="weekly-debrief-model">
                      Model
                    </label>
                    <div className="research-select-wrap">
                      <select
                        id="weekly-debrief-model"
                        className="research-select"
                        value={
                          weeklyDebriefModelId && weeklyDebriefModelName
                            ? catalogSelectionKey(weeklyDebriefModelId, weeklyDebriefModelName)
                            : ""
                        }
                        disabled={!weeklyDebriefEnabled}
                        onChange={(e) => {
                          const value = e.target.value;
                          if (!value) {
                            patchSnapshot({
                              weeklyDebriefModelId: null,
                              weeklyDebriefModelName: null,
                            });
                            return;
                          }
                          const parsed = parseCatalogSelectionKey(value);
                          if (!parsed) return;
                          patchSnapshot({
                            weeklyDebriefModelId: parsed.sourceId,
                            weeklyDebriefModelName: parsed.modelName,
                          });
                        }}
                      >
                        <option value="">Select a model…</option>
                        {enabledCatalog.map((option) => (
                          <option key={option.key} value={option.key}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="research-field">
                    <label className="research-field-label" htmlFor="weekly-debrief-reasoning">
                      Reasoning
                    </label>
                    <ReasoningSelect
                      id="weekly-debrief-reasoning"
                      value={weeklyDebriefReasoning}
                      disabled={!weeklyDebriefEnabled}
                      onChange={(next) => patchSnapshot({ weeklyDebriefReasoning: next })}
                    />
                  </div>
                </div>

                <div
                  className={`research-schedule-panel-layout${
                    weeklyDebriefEnabled && debriefPreview
                      ? " research-schedule-panel-layout--split"
                      : ""
                  }`}
                >
                  <div className="research-schedule-fields">
                    <div className="research-field research-schedule-field">
                      <label className="research-field-label" htmlFor="weekly-debrief-market">
                        Market
                      </label>
                      <div className="research-select-wrap">
                        <select
                          id="weekly-debrief-market"
                          className="research-select"
                          value={weeklyDebriefMarketId}
                          disabled={!weeklyDebriefEnabled}
                          onChange={(e) =>
                            patchSnapshot({ weeklyDebriefMarketId: e.target.value })
                          }
                        >
                          {scheduleMarkets.map((market) => (
                            <option key={market.id} value={market.id}>
                              {market.label} · closes{" "}
                              {market.close_time_local ?? market.open_time_local}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="research-field research-schedule-field">
                      <label className="research-field-label" htmlFor="weekly-debrief-offset">
                        Run time
                      </label>
                      <div className="research-select-wrap">
                        <select
                          id="weekly-debrief-offset"
                          className="research-select"
                          value={weeklyDebriefMarketOffsetHours}
                          disabled={!weeklyDebriefEnabled}
                          onChange={(e) =>
                            patchSnapshot({
                              weeklyDebriefMarketOffsetHours: Number(e.target.value),
                            })
                          }
                        >
                          {MARKET_OFFSET_OPTIONS.map((hours) => (
                            <option key={hours} value={hours}>
                              {closeOffsetLabel(hours)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>

                  {weeklyDebriefEnabled && debriefPreview && (
                    <div className="research-schedule-preview">
                      <span className="research-schedule-preview-kicker">Week ending (Friday)</span>
                      <p className="research-schedule-preview-time">
                        ~{debriefPreview.runTimeUtc} · {debriefPreview.runDate}
                      </p>
                      <p className="research-schedule-preview-detail">
                        {debriefPreview.offsetLabel} · {debriefPreview.marketLabel} · closes{" "}
                        {debriefPreview.closeTimeLocal} {debriefPreview.timezone}
                      </p>
                    </div>
                  )}
                </div>

                {debriefPromptPreview && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm research-prompt-view-btn"
                    onClick={() => setPromptModal("debrief")}
                  >
                    View prompt
                  </button>
                )}
              </div>
            </section>
          </div>
        )}
      </div>

      {promptModal === "brief" && briefPromptPreview && (
        <PromptPreviewModal
          title="Weekly brief prompt"
          preview={briefPromptPreview}
          onClose={() => setPromptModal(null)}
        />
      )}
      {promptModal === "debrief" && debriefPromptPreview && (
        <PromptPreviewModal
          title="Weekly debrief prompt"
          preview={debriefPromptPreview}
          onClose={() => setPromptModal(null)}
        />
      )}
    </div>
  );
}
