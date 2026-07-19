import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type OnboardingStatus, type OnboardingStepId } from "../../api/client";
import {
  ONBOARDING_STEPS,
  readPreviewStepFromSearch,
  stepIndex,
} from "../../lib/onboardingSteps";
import type { ExchangeId } from "../../lib/exchanges";
import AdminStep, { type SignupDraft } from "./AdminStep";
import ContinueSignInStep from "./ContinueSignInStep";
import DataSourcesStep from "./DataSourcesStep";
import ExchangeStep from "./ExchangeStep";
import InstrumentsStep from "./InstrumentsStep";
import MfaStep from "./MfaStep";
import ModelsStep from "./ModelsStep";
import OnboardingBackdrop from "./OnboardingBackdrop";
import OnboardingSlide from "./OnboardingSlide";
import ProfilePhotoStep from "./ProfilePhotoStep";
import FinishStep from "./FinishStep";
import WelcomeStep from "./WelcomeStep";

type IntroPage = "welcome" | "admin" | "photo" | "mfa";

function OnboardingFrame({ children }: { children: ReactNode }) {
  return (
    <div className="onboarding-overlay">
      <OnboardingBackdrop />
      <div className="onboarding-overlay-scrim" aria-hidden="true" />
      <div className="onboarding-dialog">{children}</div>
    </div>
  );
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const location = useLocation();
  const previewStep = readPreviewStepFromSearch(location.search);

  const [mode, setMode] = useState<"loading" | "builtin" | "oidc">("loading");
  const [mfaAvailable, setMfaAvailable] = useState(false);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [step, setStep] = useState<OnboardingStepId>("admin");
  const [introPage, setIntroPage] = useState<IntroPage>("welcome");
  const [signupDraft, setSignupDraft] = useState<SignupDraft | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [error, setError] = useState("");

  async function bootstrap() {
    const config = await api.authConfig();
    setMode(config.mode);
    setMfaAvailable(Boolean(config.mfa_available));

    let signedIn = false;
    try {
      await api.me();
      signedIn = true;
    } catch {
      signedIn = false;
    }

    // Builtin DEV preview jump: auto-login seeded preview user.
    if (
      !signedIn &&
      config.mode === "builtin" &&
      import.meta.env.DEV &&
      previewStep &&
      previewStep !== "admin"
    ) {
      try {
        const loginResult = await api.login({
          username: "preview",
          password: "BrokerAI!2026Preview",
        });
        signedIn = loginResult.status === "ok";
      } catch {
        // Visual preview can still render without a session.
      }
    }

    setSessionReady(signedIn);

    const onboarding = await api.onboardingStatus();
    setStatus(onboarding);

    if (previewStep) {
      setIntroPage(previewStep === "admin" ? "admin" : "welcome");
      setStep(previewStep);
      return;
    }

    if (!onboarding.auth_complete) {
      setIntroPage("welcome");
      setSignupDraft(null);
      setStep("admin");
      return;
    }

    setIntroPage("welcome");
    setSignupDraft(null);

    // Profile exists but cookie/session was lost — keep wizard chrome, prompt re-auth.
    if (!signedIn) {
      const resume =
        onboarding.current_step === "admin" ? "exchange" : onboarding.current_step;
      setStep(resume);
      return;
    }

    const next =
      onboarding.current_step === "admin" ? "exchange" : onboarding.current_step;
    setStep(next);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await bootstrap();
      } catch {
        if (!cancelled) {
          setMode("builtin");
          setSessionReady(false);
          setStatus({
            auth_complete: false,
            onboarding_complete: false,
            current_step: "admin",
            selected_exchange_id: null,
            enabled_pairs: null,
            strategy_id: null,
            strategy_name: null,
          });
          setIntroPage("welcome");
          setSignupDraft(null);
          setStep("admin");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run when preview query changes
  }, [previewStep]);

  async function refreshStatus() {
    const onboarding = await api.onboardingStatus();
    setStatus(onboarding);
    return onboarding;
  }

  async function goToStep(
    next: OnboardingStepId,
    patch?: Parameters<typeof api.updateOnboardingProgress>[0],
  ) {
    if (previewStep) {
      setStep(next);
      if (patch && status?.auth_complete) {
        try {
          const updated = await api.updateOnboardingProgress({ current_step: next, ...patch });
          setStatus(updated);
        } catch {
          // Preview may run without a session for visual checks.
        }
      }
      return;
    }
    if (next === "admin") {
      setStep("admin");
      return;
    }
    const updated = await api.updateOnboardingProgress({ current_step: next, ...patch });
    setStatus(updated);
    setStep(updated.current_step);
  }

  if (mode === "loading" || !status) {
    return (
      <OnboardingFrame>
        <div className="onboarding-shell onboarding-shell--loading">Loading…</div>
      </OnboardingFrame>
    );
  }

  const needsResumeSignIn = status.auth_complete && !sessionReady;
  const inIntro =
    (!status.auth_complete &&
      !needsResumeSignIn &&
      (introPage === "welcome" || introPage === "admin" || introPage === "photo")) ||
    (status.auth_complete &&
      sessionReady &&
      !needsResumeSignIn &&
      introPage === "mfa" &&
      mfaAvailable);
  const inExchangeOverlay =
    status.auth_complete &&
    sessionReady &&
    !needsResumeSignIn &&
    introPage !== "mfa" &&
    step === "exchange";
  const pastMfa = introPage !== "mfa";
  const inInstrumentsOverlay =
    status.auth_complete && sessionReady && !needsResumeSignIn && pastMfa && step === "instruments";
  const inDataSourcesOverlay =
    status.auth_complete && sessionReady && !needsResumeSignIn && pastMfa && step === "data_sources";
  const inModelsOverlay =
    status.auth_complete && sessionReady && !needsResumeSignIn && pastMfa && step === "models";
  const inFinishOverlay =
    status.auth_complete && sessionReady && !needsResumeSignIn && pastMfa && step === "finish";

  if (inIntro) {
    async function continueAfterAdmin() {
      setError("");
      try {
        setSessionReady(true);
        const next = await refreshStatus();
        setStep(
          previewStep && stepIndex(previewStep) > 0 ? previewStep : next.current_step,
        );
        if (mfaAvailable && !previewStep) {
          setIntroPage("mfa");
        } else {
          setSignupDraft(null);
          setIntroPage("welcome");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to continue");
      }
    }

    function finishMfaIntro() {
      setSignupDraft(null);
      setIntroPage("welcome");
    }

    const introShellClass =
      introPage === "welcome"
        ? "onboarding-shell--welcome"
        : introPage === "photo"
          ? "onboarding-shell--photo"
          : "onboarding-shell--form";

    return (
      <OnboardingFrame>
        <div className={`onboarding-shell ${introShellClass}`}>
          {import.meta.env.DEV && previewStep === "admin" && (
            <p className="onboarding-preview-banner onboarding-preview-banner--welcome">
              Design preview: admin
            </p>
          )}
          <OnboardingSlide pageKey={introPage}>
            {introPage === "welcome" ? (
              <WelcomeStep onGetStarted={() => setIntroPage("admin")} />
            ) : introPage === "mfa" && signupDraft ? (
              <MfaStep
                password={signupDraft.password}
                onSkip={finishMfaIntro}
                onEnabled={finishMfaIntro}
              />
            ) : mode === "oidc" ? (
              <div className="onboarding-welcome">
                <div className="onboarding-welcome-copy">
                  <h1>Sign in to continue</h1>
                  <p>
                    Sign in with SSO to create your local BrokerAI profile, then continue with
                    exchange setup.
                  </p>
                </div>
                <a className="btn onboarding-welcome-cta" href="/api/auth/oidc/login">
                  Continue with SSO
                </a>
              </div>
            ) : introPage === "photo" && signupDraft ? (
              <ProfilePhotoStep
                draft={signupDraft}
                onBack={() => setIntroPage("admin")}
                onComplete={() => void continueAfterAdmin()}
              />
            ) : (
              <AdminStep
                initial={signupDraft}
                onContinue={(draft) => {
                  setSignupDraft(draft);
                  setIntroPage("photo");
                }}
              />
            )}
          </OnboardingSlide>
        </div>
      </OnboardingFrame>
    );
  }

  if (inExchangeOverlay) {
    return (
      <OnboardingFrame>
        <div className="onboarding-shell onboarding-shell--exchange">
          {import.meta.env.DEV && previewStep === "exchange" && (
            <p className="onboarding-preview-banner onboarding-preview-banner--welcome">
              Design preview: exchange
            </p>
          )}
          {error && <div className="error onboarding-exchange-shell-error">{error}</div>}
          <OnboardingSlide pageKey="exchange">
            <ExchangeStep
              selectedExchangeId={status.selected_exchange_id ?? null}
              onBack={() => {
                setError("");
                if (status.enabled_pairs == null) return;
                void goToStep("instruments").catch((err) => {
                  setError(err instanceof Error ? err.message : "Failed to go back");
                });
              }}
              onContinue={async (exchangeId: ExchangeId) => {
                setError("");
                try {
                  await goToStep("instruments", { selected_exchange_id: exchangeId });
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to save exchange");
                }
              }}
              onSkip={async () => {
                setError("");
                try {
                  await goToStep("data_sources", { clear_selected_exchange: true });
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to continue");
                }
              }}
            />
          </OnboardingSlide>
        </div>
      </OnboardingFrame>
    );
  }

  if (inInstrumentsOverlay) {
    return (
      <OnboardingFrame>
        <div className="onboarding-shell onboarding-shell--instruments">
          {import.meta.env.DEV && previewStep === "instruments" && (
            <p className="onboarding-preview-banner onboarding-preview-banner--welcome">
              Design preview: instruments
            </p>
          )}
          {error && <div className="error onboarding-exchange-shell-error">{error}</div>}
          <OnboardingSlide pageKey="instruments">
            <InstrumentsStep
              exchangeId={status.selected_exchange_id ?? null}
              initialPairs={status.enabled_pairs ?? null}
              onBack={() => {
                setError("");
                void goToStep("exchange").catch((err) => {
                  setError(err instanceof Error ? err.message : "Failed to go back");
                });
              }}
              onSaved={async (pairs) => {
                setError("");
                try {
                  await goToStep("data_sources", { enabled_pairs: pairs });
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to continue");
                }
              }}
            />
          </OnboardingSlide>
        </div>
      </OnboardingFrame>
    );
  }

  if (inDataSourcesOverlay) {
    return (
      <OnboardingFrame>
        <div className="onboarding-shell onboarding-shell--exchange">
          {import.meta.env.DEV && previewStep === "data_sources" && (
            <p className="onboarding-preview-banner onboarding-preview-banner--welcome">
              Design preview: data sources
            </p>
          )}
          {error && <div className="error onboarding-exchange-shell-error">{error}</div>}
          <OnboardingSlide pageKey="data_sources">
            <DataSourcesStep
              onBack={() => {
                setError("");
                const previous = status.selected_exchange_id ? "instruments" : "exchange";
                void goToStep(previous).catch((err) => {
                  setError(err instanceof Error ? err.message : "Failed to go back");
                });
              }}
              onContinue={async () => {
                setError("");
                try {
                  await goToStep("models");
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to continue");
                }
              }}
              onSkip={async () => {
                setError("");
                try {
                  await goToStep("models");
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to continue");
                }
              }}
            />
          </OnboardingSlide>
        </div>
      </OnboardingFrame>
    );
  }

  if (inModelsOverlay) {
    return (
      <OnboardingFrame>
        <div className="onboarding-shell onboarding-shell--exchange">
          {import.meta.env.DEV && previewStep === "models" && (
            <p className="onboarding-preview-banner onboarding-preview-banner--welcome">
              Design preview: models
            </p>
          )}
          {error && <div className="error onboarding-exchange-shell-error">{error}</div>}
          <OnboardingSlide pageKey="models">
            <ModelsStep
              onBack={() => {
                setError("");
                void goToStep("data_sources").catch((err) => {
                  setError(err instanceof Error ? err.message : "Failed to go back");
                });
              }}
              onContinue={async () => {
                setError("");
                try {
                  await goToStep("finish");
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to continue");
                }
              }}
              onSkip={async () => {
                setError("");
                try {
                  await goToStep("finish");
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to continue");
                }
              }}
            />
          </OnboardingSlide>
        </div>
      </OnboardingFrame>
    );
  }

  if (inFinishOverlay) {
    return (
      <OnboardingFrame>
        <div className="onboarding-shell onboarding-shell--finish">
          {import.meta.env.DEV && previewStep === "finish" && (
            <p className="onboarding-preview-banner onboarding-preview-banner--welcome">
              Design preview: finish
            </p>
          )}
          {error && <div className="error onboarding-exchange-shell-error">{error}</div>}
          <OnboardingSlide pageKey="finish">
            <FinishStep
              onDone={() => {
                navigate("/");
                window.location.reload();
              }}
            />
          </OnboardingSlide>
        </div>
      </OnboardingFrame>
    );
  }

  const activeIndex = stepIndex(step);
  const stepLabels = ONBOARDING_STEPS.map((entry) =>
    entry.id === "admin" && mode === "oidc"
      ? { ...entry, label: "Sign in" }
      : entry,
  );

  const currentLabel = stepLabels[activeIndex]?.label ?? "Setup";
  const wizardPageKey = needsResumeSignIn ? "resume" : step;

  return (
    <OnboardingFrame>
      <div className="onboarding-shell">
        <header className="onboarding-header">
          <div className="onboarding-header-meta">
            <span className="onboarding-page-count">
              {activeIndex + 1} / {stepLabels.length}
            </span>
            <span className="onboarding-page-label">{currentLabel}</span>
          </div>
          <h1>{currentLabel}</h1>
          <p>Complete setup to configure your exchange, instruments, data sources, and models.</p>
          {previewStep && import.meta.env.DEV && (
            <p className="onboarding-preview-banner">
              Design preview: <code>{previewStep}</code>
            </p>
          )}
        </header>

        <div className="onboarding-pager">
          <OnboardingSlide pageKey={wizardPageKey}>
            {error && <div className="error">{error}</div>}

            {needsResumeSignIn && (
              <ContinueSignInStep
                mode={mode}
                onSignedIn={async () => {
                  setError("");
                  try {
                    await bootstrap();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Failed to continue");
                  }
                }}
              />
            )}

          </OnboardingSlide>
        </div>

        <nav className="onboarding-segmented" aria-label="Setup progress">
          {stepLabels.map((entry, index) => {
            const state =
              index < activeIndex ? "done" : index === activeIndex ? "current" : "upcoming";
            return (
              <div
                key={entry.id}
                className={`onboarding-segment is-${state}`}
                title={entry.label}
                aria-current={state === "current" ? "step" : undefined}
              >
                <span className="onboarding-segment-label">{entry.label}</span>
              </div>
            );
          })}
        </nav>
      </div>
    </OnboardingFrame>
  );
}
