export type SessionDef = {
  id: string;
  name: string;
  timezone: string;
  hours: string;
  startHour: number;
  startMinute: number;
  endHour: number;
  endMinute: number;
  coverage?: string;
};

/** Liquidity session windows — keep in sync with backend `market_sessions.py`. */
export const MARKET_SESSION_DEFS: SessionDef[] = [
  {
    id: "sydney",
    name: "Sydney",
    timezone: "America/New_York",
    hours: "5:00 PM–2:00 AM ET",
    startHour: 17,
    startMinute: 0,
    endHour: 2,
    endMinute: 0,
  },
  {
    id: "asia",
    name: "Asia",
    timezone: "UTC",
    hours: "12:00 AM–9:00 AM UTC",
    startHour: 0,
    startMinute: 0,
    endHour: 9,
    endMinute: 0,
    coverage: "Tokyo · Singapore · Hong Kong · China",
  },
  {
    id: "london",
    name: "London",
    timezone: "America/New_York",
    hours: "3:00 AM–12:00 PM ET",
    startHour: 3,
    startMinute: 0,
    endHour: 12,
    endMinute: 0,
  },
  {
    id: "ny",
    name: "NY",
    timezone: "America/New_York",
    hours: "8:00 AM–5:00 PM ET",
    startHour: 8,
    startMinute: 0,
    endHour: 17,
    endMinute: 0,
  },
];

export const SESSION_BY_ID = Object.fromEntries(
  MARKET_SESSION_DEFS.map((session) => [session.id, session]),
) as Record<string, SessionDef>;

export const SESSION_OPTIONS = MARKET_SESSION_DEFS.map((session) => session.name);

export const ASIA_SESSION_INFO = {
  title: "Combined Asia-Pacific window",
  body:
    "Asia covers regular exchange hours for Tokyo (TSE), Singapore (SGX), Hong Kong (HKEX), and China (SSE/SZSE). The session runs 12:00 AM–9:00 AM UTC — from the earliest open (Tokyo) through the latest close (Singapore).",
};
