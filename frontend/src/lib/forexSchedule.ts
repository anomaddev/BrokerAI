/** OANDA forex/metals schedule — keep in sync with `market_calendar.py`. */

const FOREX_SCHEDULE_ZONE = "America/New_York";

const FOREX_OPEN = { hour: 17, minute: 5 };
const FOREX_CLOSE = { hour: 16, minute: 59 };
const DAILY_BREAK_START = { hour: 16, minute: 59 };
const DAILY_BREAK_END = { hour: 17, minute: 5 };

const WEEKDAY_TO_PYTHON: Record<string, number> = {
  Mon: 0,
  Tue: 1,
  Wed: 2,
  Thu: 3,
  Fri: 4,
  Sat: 5,
  Sun: 6,
};

function minutesSince(hour: number, minute: number): number {
  return hour * 60 + minute;
}

function etWallClock(when: Date): { weekday: number; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: FOREX_SCHEDULE_ZONE,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(when);

  const weekdayStr = parts.find((part) => part.type === "weekday")?.value ?? "Mon";
  const hour = Number(parts.find((part) => part.type === "hour")?.value);
  const minute = Number(parts.find((part) => part.type === "minute")?.value);

  return {
    weekday: WEEKDAY_TO_PYTHON[weekdayStr] ?? 0,
    minutes: minutesSince(hour, minute),
  };
}

export function isInForexDailyBreak(when: Date): boolean {
  const { minutes } = etWallClock(when);
  const start = minutesSince(DAILY_BREAK_START.hour, DAILY_BREAK_START.minute);
  const end = minutesSince(DAILY_BREAK_END.hour, DAILY_BREAK_END.minute);
  return start <= minutes && minutes < end;
}

/** Daily break pill applies Mon–Thu; Fri/Sat/Sun use weekly close/open instead. */
export function isForexDailyBreakSession(when: Date): boolean {
  if (!isInForexDailyBreak(when)) return false;
  const { weekday } = etWallClock(when);
  return weekday >= 0 && weekday <= 3;
}

export function isForexOpen(when: Date): boolean {
  const { weekday, minutes } = etWallClock(when);
  const openAt = minutesSince(FOREX_OPEN.hour, FOREX_OPEN.minute);
  const closeAt = minutesSince(FOREX_CLOSE.hour, FOREX_CLOSE.minute);

  if (weekday === 5) return false;
  if (weekday === 6 && minutes < openAt) return false;
  if (weekday === 4 && minutes >= closeAt) return false;
  if (isInForexDailyBreak(when)) return false;
  return true;
}
