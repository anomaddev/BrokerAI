import { FormEvent, useEffect, useRef, useState } from "react";
import { api, type MfaEnrollResponse } from "../api/client";
import { mfaQrImageSrc } from "../lib/mfaQrCode";

type MfaEnrollPanelProps = {
  /** When set, skip the password field and enroll immediately with this password. */
  password?: string;
  onEnabled: () => void;
  onCancel?: () => void;
  variant?: "onboarding" | "settings";
};

type Phase = "password" | "scan";

/** Optional TOTP enrollment used by setup and Account settings. */
export default function MfaEnrollPanel({
  password: initialPassword,
  onEnabled,
  onCancel,
  variant = "settings",
}: MfaEnrollPanelProps) {
  const [phase, setPhase] = useState<Phase>(initialPassword ? "scan" : "password");
  const [password, setPassword] = useState(initialPassword ?? "");
  const [enroll, setEnroll] = useState<MfaEnrollResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const autoStarted = useRef(false);

  async function startEnroll(pw: string) {
    setError("");
    setLoading(true);
    try {
      const result = await api.mfaEnroll({ password: pw });
      setEnroll(result);
      setPassword(pw);
      setPhase("scan");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start 2FA setup");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!initialPassword || autoStarted.current) return;
    autoStarted.current = true;
    void startEnroll(initialPassword);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- enroll once with setup password
  }, [initialPassword]);

  async function onPasswordSubmit(e: FormEvent) {
    e.preventDefault();
    await startEnroll(password);
  }

  async function onVerifySubmit(e: FormEvent) {
    e.preventDefault();
    if (!enroll) return;
    setError("");
    setLoading(true);
    try {
      await api.mfaVerify({ enroll_token: enroll.enroll_token, code: code.trim() });
      onEnabled();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid authenticator code");
    } finally {
      setLoading(false);
    }
  }

  const shellClass =
    variant === "onboarding" ? "onboarding-welcome onboarding-welcome--form" : "mfa-enroll-panel";
  const qrSrc = mfaQrImageSrc(enroll?.qr_code);

  if (phase === "password") {
    return (
      <form className={shellClass} onSubmit={(e) => void onPasswordSubmit(e)}>
        <div className={variant === "onboarding" ? "onboarding-welcome-main" : undefined}>
          <div className="onboarding-welcome-copy">
            <h1>Enable authenticator</h1>
            <p>Confirm your password to generate a QR code for your authenticator app.</p>
          </div>
          {error ? <div className="error">{error}</div> : null}
          <div className="field">
            <label htmlFor="mfa-enroll-password">Current password</label>
            <input
              id="mfa-enroll-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              autoFocus
            />
          </div>
        </div>
        <div className="onboarding-welcome-actions">
          {onCancel ? (
            <button
              type="button"
              className="btn btn-secondary onboarding-welcome-cta"
              onClick={onCancel}
              disabled={loading}
            >
              Cancel
            </button>
          ) : null}
          <button className="btn onboarding-welcome-cta" type="submit" disabled={loading || !password}>
            {loading ? "Starting…" : "Continue"}
          </button>
        </div>
      </form>
    );
  }

  if (!enroll) {
    return (
      <div className={shellClass}>
        {error ? <div className="error">{error}</div> : null}
        {loading ? <p className="settings-muted">Preparing authenticator…</p> : null}
        {!loading && onCancel ? (
          <div className="onboarding-welcome-actions">
            <button type="button" className="btn btn-secondary onboarding-welcome-cta" onClick={onCancel}>
              Skip for now
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <form className={shellClass} onSubmit={(e) => void onVerifySubmit(e)}>
      <div className={variant === "onboarding" ? "onboarding-welcome-main" : "mfa-enroll-body"}>
        <div className="onboarding-welcome-copy">
          <h1>Scan QR code</h1>
          <p>Add BrokerAI in your authenticator app, then enter the 6-digit code to confirm.</p>
        </div>
        {error ? <div className="error">{error}</div> : null}
        {qrSrc ? (
          <div className="mfa-qr-wrap">
            <img className="mfa-qr" src={qrSrc} alt="Authenticator QR code" />
          </div>
        ) : null}
        <div className="mfa-secret-block">
          <button
            type="button"
            className="mfa-secret-toggle"
            onClick={() => setShowSecret((v) => !v)}
          >
            {showSecret ? "Hide setup key" : "Can't scan? Show setup key"}
          </button>
          {showSecret && enroll.secret ? <code className="mfa-secret">{enroll.secret}</code> : null}
        </div>
        <div className="field">
          <label htmlFor="mfa-enroll-code">Authentication code</label>
          <input
            id="mfa-enroll-code"
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
      </div>
      <div className="onboarding-welcome-actions">
        {onCancel ? (
          <button
            type="button"
            className="btn btn-secondary onboarding-welcome-cta"
            onClick={onCancel}
            disabled={loading}
          >
            Skip for now
          </button>
        ) : null}
        <button
          className="btn onboarding-welcome-cta"
          type="submit"
          disabled={loading || code.trim().length < 6}
        >
          {loading ? "Enabling…" : "Enable 2FA"}
        </button>
      </div>
    </form>
  );
}
