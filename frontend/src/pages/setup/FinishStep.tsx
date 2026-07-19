import { useEffect, useState } from "react";
import { api } from "../../api/client";
import OnboardingLogo from "./OnboardingLogo";

type FinishStepProps = {
  onDone: () => void;
};

type Phase = "verifying" | "ready" | "finishing" | "error";

export default function FinishStep({ onDone }: FinishStepProps) {
  const [phase, setPhase] = useState<Phase>("verifying");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPhase("verifying");
      setError("");
      try {
        await api.verifyOnboarding();
        if (!cancelled) setPhase("ready");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to confirm setup data");
          setPhase("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleFinish() {
    setPhase("finishing");
    setError("");
    try {
      await api.completeOnboarding();
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete onboarding");
      setPhase("ready");
    }
  }

  if (phase === "verifying") {
    return (
      <div className="onboarding-welcome onboarding-welcome--finish">
        <div className="onboarding-welcome-main">
          <OnboardingLogo />
          <div className="onboarding-welcome-copy">
            <h1>Saving setup</h1>
            <p>Confirming your profile and onboarding data are stored…</p>
          </div>
          <div className="onboarding-finish-loading" role="status" aria-live="polite">
            <span className="onboarding-finish-spinner" aria-hidden />
            <span>Writing to database</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="onboarding-welcome onboarding-welcome--finish">
      <div className="onboarding-welcome-main">
        {error && <div className="error">{error}</div>}
        <OnboardingLogo />
        <div className="onboarding-welcome-copy">
          <h1>Setup complete</h1>
          <p>
            Connected assets and data sources start disabled. Enable at least one asset class under
            Settings → Broker, then create and enable a strategy under Research → Strategies before
            the bot will trade.
          </p>
          <p>
            If you skipped an exchange, data source, or model, you can add them anytime in Settings →
            Connections or Settings → Models.
          </p>
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        {phase === "error" ? (
          <button
            type="button"
            className="btn onboarding-welcome-cta"
            onClick={() => {
              setPhase("verifying");
              setError("");
              void api
                .verifyOnboarding()
                .then(() => setPhase("ready"))
                .catch((err) => {
                  setError(err instanceof Error ? err.message : "Failed to confirm setup data");
                  setPhase("error");
                });
            }}
          >
            Retry
          </button>
        ) : (
          <button
            type="button"
            className="btn onboarding-welcome-cta"
            onClick={() => void handleFinish()}
            disabled={phase === "finishing"}
          >
            {phase === "finishing" ? "Finishing…" : "Finish Setup"}
          </button>
        )}
      </div>
    </div>
  );
}
