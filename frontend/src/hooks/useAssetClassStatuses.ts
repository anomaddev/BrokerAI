import { useEffect, useState } from "react";
import type { AssetClass } from "../api/client";
import {
  ASSET_CLASS_STATUSES_UPDATED,
  assetClassStatusMap,
  loadAssetClassStatuses,
} from "../lib/assetClassStatus";
import { CONFIG_RESTORED } from "../lib/configBackup";

export function useAssetClassStatuses(): Partial<Record<AssetClass, boolean>> {
  const [statuses, setStatuses] = useState<Partial<Record<AssetClass, boolean>>>({});

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const rows = await loadAssetClassStatuses();
        if (!cancelled) setStatuses(assetClassStatusMap(rows));
      } catch {
        if (!cancelled) setStatuses({});
      }
    }

    void load();
    window.addEventListener(ASSET_CLASS_STATUSES_UPDATED, load);
    window.addEventListener(CONFIG_RESTORED, load);

    return () => {
      cancelled = true;
      window.removeEventListener(ASSET_CLASS_STATUSES_UPDATED, load);
      window.removeEventListener(CONFIG_RESTORED, load);
    };
  }, []);

  return statuses;
}
