import { useCallback, useEffect, useState } from "react";
import {
  api,
  RESEARCH_REPORTS_UNREAD_UPDATED,
  type ResearchReportsUnreadCount,
} from "../api/client";
import { getSupabaseBrowserClient } from "../lib/supabaseClient";

const EMPTY: ResearchReportsUnreadCount = {
  unread_count: 0,
  daily: 0,
  weekly: 0,
};

const POLL_MS = 60_000;

export function useResearchReportsUnreadCount() {
  const [counts, setCounts] = useState<ResearchReportsUnreadCount>(EMPTY);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getResearchReportsUnreadCount();
      setCounts(next);
    } catch {
      /* keep last known counts */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (cancelled) return;
      await refresh();
    }

    void load();
    const interval = window.setInterval(() => void load(), POLL_MS);
    const onFocus = () => void load();
    const onUpdated = () => void load();
    window.addEventListener("focus", onFocus);
    window.addEventListener(RESEARCH_REPORTS_UNREAD_UPDATED, onUpdated);

    let channel: { unsubscribe: () => void } | null = null;
    void getSupabaseBrowserClient().then((supabase) => {
      if (!supabase || cancelled) return;
      const sub = supabase
        .channel("research-report-reads")
        .on(
          "postgres_changes",
          { event: "*", schema: "brokerai", table: "research_report_reads" },
          () => {
            void load();
          },
        )
        .subscribe();
      channel = {
        unsubscribe: () => {
          void supabase.removeChannel(sub);
        },
      };
    });

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(RESEARCH_REPORTS_UNREAD_UPDATED, onUpdated);
      channel?.unsubscribe();
    };
  }, [refresh]);

  return { ...counts, refresh };
}
