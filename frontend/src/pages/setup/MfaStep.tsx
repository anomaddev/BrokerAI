import { useState } from "react";
import MfaEnrollPanel from "../../components/MfaEnrollPanel";

type MfaStepProps = {
  password: string;
  onSkip: () => void;
  onEnabled: () => void;
};

/**
 * Optional post-admin 2FA offer during setup.
 * Skippable — users can enroll later from Account settings.
 */
export default function MfaStep({ password, onSkip, onEnabled }: MfaStepProps) {
  const [mode, setMode] = useState<"offer" | "enroll">("offer");

  if (mode === "enroll") {
    return (
      <MfaEnrollPanel
        password={password}
        variant="onboarding"
        onEnabled={onEnabled}
        onCancel={onSkip}
      />
    );
  }

  return (
    <div className="onboarding-welcome onboarding-welcome--form">
      <div className="onboarding-welcome-main">
        <div className="onboarding-welcome-copy">
          <h1>Protect your account</h1>
          <p>
            Add an authenticator app for two-factor sign-in. Optional — you can turn this on later
            in Settings → Account.
          </p>
        </div>
      </div>
      <div className="onboarding-welcome-actions">
        <button type="button" className="btn btn-secondary onboarding-welcome-cta" onClick={onSkip}>
          Skip for now
        </button>
        <button
          type="button"
          className="btn onboarding-welcome-cta"
          onClick={() => setMode("enroll")}
        >
          Set up 2FA
        </button>
      </div>
    </div>
  );
}
