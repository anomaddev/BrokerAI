import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { api } from "../api/client";

let client: SupabaseClient | null = null;
let initPromise: Promise<SupabaseClient | null> | null = null;

/** Lazily create a browser Supabase client from publishable auth config. */
export async function getSupabaseBrowserClient(): Promise<SupabaseClient | null> {
  if (client) return client;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    try {
      const config = await api.authConfig();
      if (!config.supabase_configured || !config.supabase_url || !config.supabase_anon_key) {
        return null;
      }
      client = createClient(config.supabase_url, config.supabase_anon_key, {
        auth: {
          persistSession: false,
          autoRefreshToken: false,
        },
      });
      return client;
    } catch {
      return null;
    }
  })();
  return initPromise;
}

export async function fetchReportMarkdownFromSignedUrl(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download report (${response.status})`);
  }
  return response.text();
}
