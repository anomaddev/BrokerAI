import { FormEvent, useMemo, useState } from "react";
import OnboardingLogo from "./OnboardingLogo";

const MIN_PASSWORD = 8;
const MAX_PASSWORD = 32;

export type SignupDraft = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  confirm_password: string;
};

type StrengthLevel = "weak" | "fair" | "strong";

type PasswordChecks = {
  length: boolean;
  lower: boolean;
  upper: boolean;
  number: boolean;
  special: boolean;
};

function passwordChecks(pw: string): PasswordChecks {
  return {
    length: pw.length >= MIN_PASSWORD && pw.length <= MAX_PASSWORD,
    lower: /[a-z]/.test(pw),
    upper: /[A-Z]/.test(pw),
    number: /[0-9]/.test(pw),
    special: /[^A-Za-z0-9]/.test(pw),
  };
}

function passwordStrength(pw: string): { label: string; level: StrengthLevel; score: number } {
  const checks = passwordChecks(pw);
  const score = Object.values(checks).filter(Boolean).length;
  if (score <= 2) return { label: "Weak", level: "weak", score };
  if (score <= 4) return { label: "Fair", level: "fair", score };
  return { label: "Strong", level: "strong", score };
}

function PasswordStrengthMeter({ password }: { password: string }) {
  const { label, level, score } = passwordStrength(password);
  const checks = passwordChecks(password);

  return (
    <div className="onboarding-password-meta" aria-live="polite">
      <div className="password-strength">
        <div className="password-strength-bar" aria-hidden>
          {[1, 2, 3, 4, 5].map((segment) => (
            <span
              key={segment}
              className={`password-strength-segment${segment <= score ? ` active ${level}` : ""}`}
            />
          ))}
        </div>
        <span className={`password-strength-label ${level}`}>Strength: {label}</span>
      </div>
      <ul className="onboarding-password-rules">
        <li className={checks.length ? "is-met" : undefined}>8–32 characters</li>
        <li className={checks.lower ? "is-met" : undefined}>One lowercase letter</li>
        <li className={checks.upper ? "is-met" : undefined}>One uppercase letter</li>
        <li className={checks.number ? "is-met" : undefined}>One number</li>
        <li className={checks.special ? "is-met" : undefined}>One special character</li>
      </ul>
    </div>
  );
}

type AdminStepProps = {
  initial?: SignupDraft | null;
  onContinue: (draft: SignupDraft) => void;
};

export default function AdminStep({ initial, onContinue }: AdminStepProps) {
  const [firstName, setFirstName] = useState(initial?.first_name ?? "");
  const [lastName, setLastName] = useState(initial?.last_name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [password, setPassword] = useState(initial?.password ?? "");
  const [confirm, setConfirm] = useState(initial?.confirm_password ?? "");
  const [error, setError] = useState("");

  const checks = useMemo(() => passwordChecks(password), [password]);
  const passwordValid = Object.values(checks).every(Boolean);
  const canSubmit =
    firstName.trim().length > 0 &&
    email.trim().length > 0 &&
    passwordValid &&
    confirm === password;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!passwordValid) {
      setError("Password does not meet the requirements");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    onContinue({
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      email: email.trim(),
      password,
      confirm_password: confirm,
    });
  }

  return (
    <form className="onboarding-welcome onboarding-welcome--form" onSubmit={onSubmit}>
      <div className="onboarding-welcome-main">
        <OnboardingLogo />

        <div className="onboarding-welcome-copy">
          <h1>Create your admin profile</h1>
          <p>Add your details to sign in and manage this BrokerAI instance.</p>
        </div>

        {error && <div className="error">{error}</div>}

        <div className="onboarding-form-fields">
          <div className="onboarding-name-grid">
            <div className="field">
              <label htmlFor="onboarding-first-name">First name</label>
              <input
                id="onboarding-first-name"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
                autoComplete="given-name"
                maxLength={64}
                placeholder="Jordan"
              />
            </div>
            <div className="field">
              <label htmlFor="onboarding-last-name">Last name</label>
              <input
                id="onboarding-last-name"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name"
                maxLength={64}
                placeholder="Belfort"
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="onboarding-email">Email address</label>
            <input
              id="onboarding-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="jordan@strattonoakmont.com"
            />
          </div>
          <div className="onboarding-password-block">
            <div className="onboarding-password-grid">
              <div className="field">
                <label htmlFor="onboarding-password">Password</label>
                <input
                  id="onboarding-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={MIN_PASSWORD}
                  maxLength={MAX_PASSWORD}
                  autoComplete="new-password"
                  placeholder="SellMeThisPen1!"
                />
              </div>
              <div className="field">
                <label htmlFor="onboarding-confirm">Confirm password</label>
                <input
                  id="onboarding-confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={MIN_PASSWORD}
                  maxLength={MAX_PASSWORD}
                  autoComplete="new-password"
                  placeholder="SellMeThisPen1!"
                />
              </div>
            </div>
            <PasswordStrengthMeter password={password} />
          </div>
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        <button className="btn onboarding-welcome-cta" type="submit" disabled={!canSubmit}>
          Continue
        </button>
      </div>
    </form>
  );
}
