import OnboardingLogo from "./OnboardingLogo";

type WelcomeStepProps = {
  onGetStarted: () => void;
};

export default function WelcomeStep({ onGetStarted }: WelcomeStepProps) {
  return (
    <div className="onboarding-welcome">
      <OnboardingLogo />

      <div className="onboarding-welcome-copy">
        <h1>Your trading desk, automated</h1>
        <p>
          BrokerAI runs a coordinated bot loop for forex — candle analysis, strategy signals,
          and broker execution — from one self-hosted dashboard.
        </p>
      </div>

      <button type="button" className="btn onboarding-welcome-cta" onClick={onGetStarted}>
        Get started
      </button>
    </div>
  );
}
