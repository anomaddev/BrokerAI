import type { ComponentType } from "react";
import type { OandaConnection } from "../api/client";
import {
  EXCHANGES,
  exchangesSortedByAssetClass,
  type Exchange,
  type ExchangeId,
} from "./exchanges";
import OandaConnectionForm from "../pages/setup/OandaConnectionForm";
import ForexInstrumentsPanel from "../pages/setup/ForexInstrumentsPanel";

export type ExchangeConnectionStepProps = {
  connection: OandaConnection;
  onSaved: (connection: OandaConnection) => void;
  disabled?: boolean;
};

export type ExchangeInstrumentsStepProps = {
  enabledPairs: string[];
  pairOrder: string[];
  catalog: string[];
  onEnabledPairsChange: (pairs: string[]) => void;
  onPairOrderChange: (order: string[]) => void;
  disabled?: boolean;
};

export type ExchangeOnboardingModule = {
  id: ExchangeId;
  exchange: Exchange;
  ConnectionStep: ComponentType<ExchangeConnectionStepProps>;
  InstrumentsStep: ComponentType<ExchangeInstrumentsStepProps>;
};

const MODULES: Partial<Record<ExchangeId, ExchangeOnboardingModule>> = {
  oanda: {
    id: "oanda",
    exchange: EXCHANGES.find((e) => e.id === "oanda")!,
    ConnectionStep: OandaConnectionForm,
    InstrumentsStep: ForexInstrumentsPanel,
  },
};

/** Available modules that can complete onboarding today. */
export function availableOnboardingModules(): ExchangeOnboardingModule[] {
  return exchangesSortedByAssetClass(EXCHANGES.filter((exchange) => exchange.available))
    .map((exchange) => MODULES[exchange.id])
    .filter((module): module is ExchangeOnboardingModule => Boolean(module));
}

export function getOnboardingModule(id: ExchangeId | string | null | undefined) {
  if (!id) return undefined;
  return MODULES[id as ExchangeId];
}

/** Full catalog for the picker (available + coming soon), sorted by asset type. */
export function onboardingExchangeCatalog(): Exchange[] {
  return exchangesSortedByAssetClass();
}
