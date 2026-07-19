import { TrendingUp } from "lucide-react";

export default function OnboardingLogo() {
  return (
    <div className="onboarding-welcome-logo">
      <span className="onboarding-welcome-mark" aria-hidden>
        <TrendingUp size={28} strokeWidth={2.25} />
      </span>
      <span className="onboarding-welcome-brand">BrokerAI</span>
    </div>
  );
}
