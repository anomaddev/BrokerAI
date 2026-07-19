import { FormEvent, useState } from "react";
import { api } from "../api/client";

type MfaChallengeFormProps = {
  mfaToken: string;
  onVerified: () => void;
  onCancel?: () => void;
  submitLabel?: string;
};

/** Second step after password when TOTP MFA is enrolled. */
export default function MfaChallengeForm({
  mfaToken,
  onVerified,
  onCancel,
  submitLabel = "Verify",
}: MfaChallengeFormProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await api.loginMfa({ mfa_token: mfaToken, code: code.trim() });
      if (result.status !== "ok") {
        throw new Error("Verification failed");
      }
      onVerified();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid authenticator code");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="mfa-challenge-form" onSubmit={(e) => void onSubmit(e)}>
      <div className="onboarding-welcome-copy">
        <h1>Authenticator code</h1>
        <p>Enter the 6-digit code from your authenticator app.</p>
      </div>
      {error ? <div className="error">{error}</div> : null}
      <div className="field">
        <label htmlFor="mfa-challenge-code">Authentication code</label>
        <input
          id="mfa-challenge-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9 ]*"
          maxLength={8}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
          autoFocus
          placeholder="123456"
        />
      </div>
      <div className="onboarding-welcome-actions">
        {onCancel ? (
          <button
            type="button"
            className="btn btn-secondary onboarding-welcome-cta"
            onClick={onCancel}
            disabled={loading}
          >
            Back
          </button>
        ) : null}
        <button className="btn onboarding-welcome-cta" type="submit" disabled={loading || code.trim().length < 6}>
          {loading ? "Verifying…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
