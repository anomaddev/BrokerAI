import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CONFIG_RESTORED } from "../lib/configBackup";
import {
  EMPTY_MARKET_BAR_ASSET_CONTEXT,
  hasConfiguredMetalsSymbols,
  type MarketBarAssetContext,
} from "../lib/marketBarAssets";
import {
  FOREX_TRADING_SESSIONS_UPDATED,
  normalizeForexTradingSessions,
} from "../lib/forexTradingSessions";

export function useMarketBarAssets(): MarketBarAssetContext {
  const [context, setContext] = useState<MarketBarAssetContext>(EMPTY_MARKET_BAR_ASSET_CONTEXT);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [forexSettings, metalsSettings] = await Promise.all([
          api.getForexPairs(),
          api.getAssetSettings("metals"),
        ]);
        if (cancelled) return;

        setContext({
          forexEnabled: Boolean(forexSettings.enabled),
          hasForexPairs: forexSettings.enabled_pairs.length > 0,
          enabledSessions: normalizeForexTradingSessions(forexSettings.enabled_sessions),
          metalsEnabled: Boolean(metalsSettings.enabled),
          hasMetalsSymbols: hasConfiguredMetalsSymbols(metalsSettings.enabled_symbols),
        });
      } catch {
        if (!cancelled) {
          setContext(EMPTY_MARKET_BAR_ASSET_CONTEXT);
        }
      }
    }

    void load();
    window.addEventListener(FOREX_TRADING_SESSIONS_UPDATED, load);
    window.addEventListener(CONFIG_RESTORED, load);

    return () => {
      cancelled = true;
      window.removeEventListener(FOREX_TRADING_SESSIONS_UPDATED, load);
      window.removeEventListener(CONFIG_RESTORED, load);
    };
  }, []);

  return context;
}
