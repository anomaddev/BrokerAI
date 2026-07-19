import type { OnboardingStepId } from "../api/client";

export const ONBOARDING_STEPS: { id: OnboardingStepId; label: string }[] = [
  { id: "admin", label: "Admin" },
  { id: "exchange", label: "Exchange" },
  { id: "instruments", label: "Instruments" },
  { id: "data_sources", label: "Data sources" },
  { id: "models", label: "Models" },
  { id: "finish", label: "Finish" },
];

export const DEFAULT_ONBOARDING_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY"];

export function stepIndex(step: OnboardingStepId): number {
  return ONBOARDING_STEPS.findIndex((entry) => entry.id === step);
}

export function parsePreviewStep(raw: string | null): OnboardingStepId | null {
  if (!raw) return null;
  // Legacy preview links from before strategy was removed.
  if (raw === "strategy") return "data_sources";
  const match = ONBOARDING_STEPS.find((entry) => entry.id === raw);
  return match?.id ?? null;
}

/** DEV-only: honor ?previewStep= when running Vite. */
export function readPreviewStepFromSearch(search: string): OnboardingStepId | null {
  if (!import.meta.env.DEV) return null;
  const params = new URLSearchParams(search);
  return parsePreviewStep(params.get("previewStep"));
}
