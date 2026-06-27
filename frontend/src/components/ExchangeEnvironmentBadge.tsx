import type { OandaEnvironment } from "../api/client";

type ExchangeEnvironmentBadgeProps = {
  environment: OandaEnvironment;
};

export default function ExchangeEnvironmentBadge({ environment }: ExchangeEnvironmentBadgeProps) {
  const isLive = environment === "live";
  return (
    <span className={`exchange-env-badge exchange-env-badge--${environment}`}>
      {isLive ? "Live" : "Practice"}
    </span>
  );
}
