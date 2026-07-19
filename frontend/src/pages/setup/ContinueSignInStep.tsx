import { FormEvent, useState } from "react";
import { api } from "../../api/client";
import MfaChallengeForm from "../../components/MfaChallengeForm";

type ContinueSignInStepProps = {
  mode: "builtin" | "oidc";
  onSignedIn: () => void;
};

/** Shown when onboarding is incomplete but the browser session was lost. */
export default function ContinueSignInStep({ mode, onSignedIn }: ContinueSignInStepProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
      onSignedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  if (mode === "oidc") {
    return (
      <div className="onboarding-step-body">
        <p className="onboarding-step-lead">
          Sign in again to continue setup. Your progress is saved.
        </p>
        <div className="onboarding-step-actions">
          <a className="btn" href="/api/auth/oidc/login">
            Continue with SSO
          </a>
        </div>
      </div>
    );
  }

  if (mfaToken) {
    return (
      <div className="onboarding-step-body">
        <MfaChallengeForm
          mfaToken={mfaToken}
          submitLabel="Continue setup"
          onCancel={() => setMfaToken(null)}
          onVerified={onSignedIn}
        />
      </div>
    );
  }

  return (
    <form className="onboarding-step-body" onSubmit={onSubmit}>
      <p className="onboarding-step-lead">
        Sign in again to continue setup. Your progress is saved.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="field">
        <label htmlFor="onboarding-resume-email">Email address</label>
        <input
          id="onboarding-resume-email"
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
        <label htmlFor="onboarding-resume-password">Password</label>
        <input
          id="onboarding-resume-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
        />
      </div>
      <div className="onboarding-step-actions">
        <button className="btn" type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Continue setup"}
        </button>
      </div>
    </form>
  );
}
