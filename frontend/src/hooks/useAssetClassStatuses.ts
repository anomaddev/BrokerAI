import { useEffect, useState } from "react";
import type { AssetClass } from "../api/client";
import { assetClassStatusMap, loadAssetClassStatuses } from "../lib/assetClassStatus";

export function useAssetClassStatuses(): Partial<Record<AssetClass, boolean>> {
  const [statuses, setStatuses] = useState<Partial<Record<AssetClass, boolean>>>({});

  useEffect(() => {
    let cancelled = false;

    loadAssetClassStatuses()
      .then((rows) => {
        if (!cancelled) setStatuses(assetClassStatusMap(rows));
      })
      .catch(() => {
        if (!cancelled) setStatuses({});
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return statuses;
}
