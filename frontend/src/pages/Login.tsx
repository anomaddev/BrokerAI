import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import MfaChallengeForm from "../components/MfaChallengeForm";
import OnboardingBackdrop from "./setup/OnboardingBackdrop";
import OnboardingLogo from "./setup/OnboardingLogo";

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"loading" | "builtin" | "oidc">("loading");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const onboarding = await api.onboardingStatus();
        if (cancelled) return;
        if (!onboarding.onboarding_complete) {
          navigate("/setup", { replace: true });
          return;
        }
        const config = await api.authConfig();
        if (cancelled) return;
        if (config.mode === "oidc") {
          window.location.href = "/api/auth/oidc/login";
          return;
        }
        setMode("builtin");
      } catch {
        if (!cancelled) setMode("builtin");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  async function finishSignedIn() {
    const onboarding = await api.onboardingStatus();
    navigate(onboarding.onboarding_complete ? "/" : "/setup");
    window.location.reload();
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await api.login({ username: email.trim(), password });
      if (result.status === "mfa_required") {
        setMfaToken(result.mfa_token);
        return;
      }
      await finishSignedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  if (mode === "loading" || mode === "oidc") {
    return (
      <div className="onboarding-overlay">
        <OnboardingBackdrop />
        <div className="onboarding-overlay-scrim" aria-hidden="true" />
        <div className="onboarding-dialog">
          <div className="onboarding-shell onboarding-shell--loading">Redirecting to sign in…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="onboarding-overlay">
      <OnboardingBackdrop />
      <div className="onboarding-overlay-scrim" aria-hidden="true" />
      <div className="onboarding-dialog">
        <div className="onboarding-shell onboarding-shell--form">
          {mfaToken ? (
            <div className="onboarding-welcome onboarding-welcome--form">
              <div className="onboarding-welcome-main">
                <OnboardingLogo />
                <MfaChallengeForm
                  mfaToken={mfaToken}
                  submitLabel="Sign in"
                  onCancel={() => {
                    setMfaToken(null);
                    setError("");
                  }}
                  onVerified={() => void finishSignedIn()}
                />
              </div>
            </div>
          ) : (
            <form className="onboarding-welcome onboarding-welcome--form" onSubmit={onSubmit}>
              <div className="onboarding-welcome-main">
                <OnboardingLogo />

                <div className="onboarding-welcome-copy">
                  <h1>Sign in</h1>
                  <p>Log in to your BrokerAI dashboard.</p>
                </div>

                {error && <div className="error">{error}</div>}

                <div className="onboarding-form-fields">
                  <div className="field">
                    <label htmlFor="login-email">Email address</label>
                    <input
                      id="login-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      autoComplete="email"
                      autoFocus
                      placeholder="jordan@strattonoakmont.com"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="login-password">Password</label>
                    <input
                      id="login-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      autoComplete="current-password"
                    />
                  </div>
                </div>
              </div>

              <button className="btn onboarding-welcome-cta" type="submit" disabled={loading}>
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
