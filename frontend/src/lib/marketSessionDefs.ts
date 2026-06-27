export type SessionDef = {
  id: string;
  name: string;
  hours: string;
  startHour: number;
  startMinute: number;
  endHour: number;
  endMinute: number;
};

/** Static UTC session windows — keep in sync with backend `market_sessions.py`. */
export const MARKET_SESSION_DEFS: SessionDef[] = [
  {
    id: "asia",
    name: "Asia",
    hours: "00:00–09:00 UTC",
    startHour: 0,
    startMinute: 0,
    endHour: 9,
    endMinute: 0,
  },
  {
    id: "london",
    name: "London",
    hours: "07:00–16:00 UTC",
    startHour: 7,
    startMinute: 0,
    endHour: 16,
    endMinute: 0,
  },
  {
    id: "ny",
    name: "NY",
    hours: "13:00–22:00 UTC",
    startHour: 13,
    startMinute: 0,
    endHour: 22,
    endMinute: 0,
  },
];

export const SESSION_BY_ID = Object.fromEntries(
  MARKET_SESSION_DEFS.map((session) => [session.id, session]),
) as Record<string, SessionDef>;
